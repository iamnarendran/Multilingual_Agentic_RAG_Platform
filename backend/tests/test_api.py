"""End-to-end API tests: auth, document upload/ingestion, streaming chat, conversations."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.agents.llm import LLMError
from tests.conftest import SAMPLE_DOCS, ScriptedLLM, parse_sse, register

DOC = (
    "Marcus Aurelius was a Roman emperor from 161 to 180 AD and a Stoic philosopher.\n\n"
    "He wrote the Meditations, a series of personal writings, during his military campaigns.\n\n"
    "भारत की राजधानी नई दिल्ली है।"
)


def _upload(client: TestClient, headers, name="notes.txt", content: bytes = DOC.encode()):
    return client.post("/api/documents", headers=headers, files={"file": (name, content, "text/plain")})


def _chat(client: TestClient, headers, message: str, **extra):
    resp = client.post("/api/chat", headers=headers, json={"message": message, **extra})
    assert resp.status_code == 200, resp.text
    assert resp.headers["content-type"].startswith("text/event-stream")
    return parse_sse(resp.text)


# --- auth ----------------------------------------------------------------------


def test_register_login_me_flow(client: TestClient):
    headers = register(client, "Asha@Example.com")
    me = client.get("/api/auth/me", headers=headers)
    assert me.status_code == 200 and me.json()["email"] == "asha@example.com"

    login = client.post("/api/auth/login", json={"email": "asha@example.com", "password": "correct horse battery"})
    assert login.status_code == 200 and login.json()["access_token"]

    assert (
        client.post("/api/auth/login", json={"email": "asha@example.com", "password": "wrong-password"}).status_code
        == 401
    )
    dup = client.post(
        "/api/auth/register", json={"email": "ASHA@example.com", "name": "X", "password": "another password"}
    )
    assert dup.status_code == 409


def test_protected_routes_require_a_valid_token(client: TestClient):
    assert client.get("/api/documents").status_code == 401
    assert client.get("/api/documents", headers={"Authorization": "Bearer not-a-jwt"}).status_code == 401
    short = client.post("/api/auth/register", json={"email": "a@b.co", "name": "A", "password": "short"})
    assert short.status_code == 422


def test_health(client: TestClient):
    body = client.get("/api/health").json()
    assert body["status"] == "ok"
    assert body["llm"]["configured"] is True
    assert "pdf" in body["limits"]["extensions"]


# --- documents -----------------------------------------------------------------


def test_upload_is_ingested_and_listed(client: TestClient, services):
    headers = register(client)
    resp = _upload(client, headers)
    assert resp.status_code == 202
    doc_id = resp.json()["id"]

    doc = client.get(f"/api/documents/{doc_id}", headers=headers).json()
    assert doc["status"] == "ready", doc
    assert doc["chunk_count"] >= 1 and doc["language"] == "en"
    assert [d["id"] for d in client.get("/api/documents", headers=headers).json()] == [doc_id]


def test_upload_real_pdf(client: TestClient):
    headers = register(client)
    pdf = (SAMPLE_DOCS / "sample_en.pdf").read_bytes()
    resp = client.post("/api/documents", headers=headers, files={"file": ("meditations.pdf", pdf, "application/pdf")})
    doc = client.get(f"/api/documents/{resp.json()['id']}", headers=headers).json()
    assert doc["status"] == "ready" and doc["page_count"] == 128 and doc["chunk_count"] > 300


def test_upload_validation(client: TestClient, services):
    headers = register(client)
    assert _upload(client, headers, name="virus.exe").status_code == 415
    assert _upload(client, headers, content=b"").status_code == 400
    services.settings.max_upload_mb = 0
    assert _upload(client, headers).status_code == 413


def test_unreadable_upload_is_marked_failed(client: TestClient):
    headers = register(client)
    doc_id = _upload(client, headers, name="broken.pdf", content=b"%PDF-1.4 not really a pdf").json()["id"]
    doc = client.get(f"/api/documents/{doc_id}", headers=headers).json()
    assert doc["status"] == "failed" and doc["error"]


def test_users_cannot_see_or_delete_each_others_documents(client: TestClient):
    asha = register(client, "asha@example.com")
    ravi = register(client, "ravi@example.com", "Ravi")
    doc_id = _upload(client, asha).json()["id"]
    assert client.get(f"/api/documents/{doc_id}", headers=ravi).status_code == 404
    assert client.delete(f"/api/documents/{doc_id}", headers=ravi).status_code == 404
    assert client.get("/api/documents", headers=ravi).json() == []


# --- chat ----------------------------------------------------------------------


def test_chat_streams_agents_sources_tokens_and_persists(client: TestClient, llm: ScriptedLLM):
    headers = register(client)
    _upload(client, headers)
    events = _chat(client, headers, "Who was Marcus Aurelius?")
    kinds = [k for k, _ in events]

    assert kinds[0] == "start" and kinds[-1] == "done"
    for kind in ("meta", "step", "sources", "token", "validation"):
        assert kind in kinds
    assert kinds.index("sources") < kinds.index("token") < kinds.index("validation")
    start = events[0][1]
    assert start["created"] is True and start["title"] == "Who was Marcus Aurelius?"
    done = events[-1][1]
    assert done["status"] == "complete" and done["message_id"]
    assert done["usage"]["prompt_tokens"] > 0

    conv = client.get(f"/api/conversations/{start['conversation_id']}", headers=headers).json()
    user_msg, answer = conv["messages"]
    assert user_msg["role"] == "user" and user_msg["content"] == "Who was Marcus Aurelius?"
    assert answer["role"] == "assistant" and answer["content"] == llm.answer
    assert answer["sources"][0]["filename"] == "notes.txt"
    assert [t["agent"] for t in answer["trace"]][-1] == "validator"
    assert answer["validation"]["grounded"] is True
    assert answer["language"] == "en" and answer["query_type"] == "SIMPLE_QA"


def test_follow_up_uses_conversation_history(client: TestClient, llm: ScriptedLLM):
    headers = register(client)
    _upload(client, headers)
    conv_id = _chat(client, headers, "Who was Marcus Aurelius?")[0][1]["conversation_id"]
    llm.calls.clear()
    events = _chat(client, headers, "What did he write?", conversation_id=conv_id)
    assert events[0][1]["created"] is False
    router = next(c for c in llm.calls if c["purpose"] == "router")
    assert "USER: Who was Marcus Aurelius?" in router["messages"][1]["content"]
    assert "ASSISTANT: Marcus Aurelius was a Roman emperor" in router["messages"][1]["content"]
    assert len(client.get(f"/api/conversations/{conv_id}", headers=headers).json()["messages"]) == 4


def test_chat_in_hindi_reports_language(client: TestClient, llm: ScriptedLLM):
    headers = register(client)
    _upload(client, headers)
    events = _chat(client, headers, "भारत की राजधानी क्या है?")
    meta = [d for k, d in events if k == "meta"]
    assert {"language": "hi", "language_name": "Hindi"} in meta
    gen = next(c for c in llm.calls if c["purpose"] == "generator")
    assert "Write the answer in Hindi" in gen["messages"][0]["content"]


def test_chat_llm_error_is_streamed_and_saved(client: TestClient, llm: ScriptedLLM):
    headers = register(client)
    llm.fail_with = LLMError("The LLM provider rejected the API key. Check LLM_API_KEY.")
    events = _chat(client, headers, "Hello?")
    assert ("error", {"message": "The LLM provider rejected the API key. Check LLM_API_KEY."}) in events
    assert events[-1][1]["status"] == "error"
    conv = client.get(f"/api/conversations/{events[0][1]['conversation_id']}", headers=headers).json()
    assert conv["messages"][-1]["status"] == "error"


def test_chat_without_llm_key_explains_configuration(client: TestClient, services):
    headers = register(client)
    services.settings.llm_api_key = ""
    events = _chat(client, headers, "Hello?")
    errors = [d["message"] for k, d in events if k == "error"]
    assert errors and "LLM_API_KEY" in errors[0]


def test_conversation_management_and_isolation(client: TestClient):
    asha = register(client, "asha@example.com")
    ravi = register(client, "ravi@example.com", "Ravi")
    conv_id = _chat(client, asha, "hello")[0][1]["conversation_id"]

    assert [c["id"] for c in client.get("/api/conversations", headers=asha).json()] == [conv_id]
    assert client.get(f"/api/conversations/{conv_id}", headers=ravi).status_code == 404
    assert client.post("/api/chat", headers=ravi, json={"message": "hi", "conversation_id": conv_id}).status_code == 404

    renamed = client.patch(f"/api/conversations/{conv_id}", headers=asha, json={"title": "Greetings"})
    assert renamed.json()["title"] == "Greetings"
    assert client.delete(f"/api/conversations/{conv_id}", headers=asha).status_code == 204
    assert client.get("/api/conversations", headers=asha).json() == []


def test_deleted_document_is_no_longer_retrieved(client: TestClient, llm: ScriptedLLM):
    headers = register(client)
    doc_id = _upload(client, headers).json()["id"]
    assert client.delete(f"/api/documents/{doc_id}", headers=headers).status_code == 204
    events = _chat(client, headers, "Who was Marcus Aurelius?")
    assert not any(k == "sources" for k, _ in events)


def test_embedding_model_failure_gives_actionable_error(client: TestClient, services):
    from app.rag.embeddings import EmbeddingModelError

    async def broken(texts):
        raise EmbeddingModelError("Couldn't load the embedding model x. Set EMBEDDING_PROVIDER=openai ...")

    services.embedder.embed_documents = broken
    headers = register(client)
    doc_id = _upload(client, headers).json()["id"]
    doc = client.get(f"/api/documents/{doc_id}", headers=headers).json()
    assert doc["status"] == "failed"
    assert doc["error"].startswith("Couldn't load the embedding model")  # no "Processing error:" prefix
