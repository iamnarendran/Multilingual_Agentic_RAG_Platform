"""Hybrid vector store and the LangGraph agent pipeline (with a scripted LLM)."""

from __future__ import annotations

import pytest

from app.agents.graph import build_graph, run_agents
from app.agents.llm import LLMError
from app.rag.chunking import Chunk
from app.rag.sparse import encode_document, encode_query
from app.services import Services
from tests.conftest import FakeEmbedder, ScriptedLLM

TEXTS = {
    "u1": [
        "Marcus Aurelius was a Roman emperor and a Stoic philosopher.",
        "The Meditations were written during military campaigns.",
        "राजधानी नई दिल्ली भारत का प्रशासनिक केंद्र है।",
    ],
    "u2": ["Secret notes of the second user about emperor penguins."],
}


async def _index(services: Services) -> None:
    store = services.vector_store
    await store.ensure_collection()
    for user, texts in TEXTS.items():
        chunks = [Chunk(text=t, page=i + 1, page_end=i + 1) for i, t in enumerate(texts)]
        await store.upsert_chunks(
            user_id=user,
            document_id=f"doc-{user}",
            filename=f"{user}.pdf",
            language="en",
            chunks=chunks,
            dense=await services.embedder.embed_documents(texts),
            sparse=[encode_document(t) for t in texts],
        )


async def _search(services: Services, user: str, query: str, **kw):
    dense = (await FakeEmbedder().embed_queries([query]))[0]
    return await services.vector_store.hybrid_search(user_id=user, dense=dense, sparse=encode_query(query), **kw)


async def test_hybrid_search_ranks_keyword_matches_and_isolates_users(services: Services):
    await _index(services)
    hits = await _search(services, "u1", "Stoic emperor")
    assert hits[0].text.startswith("Marcus Aurelius")
    assert hits[0].page == 1 and hits[0].filename == "u1.pdf"
    assert all(h.document_id == "doc-u1" for h in hits)  # never another user's data

    hindi = await _search(services, "u1", "नई दिल्ली राजधानी")
    assert "दिल्ली" in hindi[0].text

    assert await _search(services, "u1", "emperor", document_ids=["doc-u2"]) == []
    assert await services.vector_store.count(user_id="u1") == 3

    await services.vector_store.delete_document(user_id="u1", document_id="doc-u1")
    assert await services.vector_store.count(user_id="u1") == 0
    assert await services.vector_store.count(user_id="u2") == 1


async def _run(services: Services, question: str, *, has_documents: bool = True, history=None):
    graph = build_graph(services)
    state = {
        "question": question,
        "history": history or [],
        "user_id": "u1",
        "document_ids": None,
        "corpus_languages": ["en", "hi"],
        "has_documents": has_documents,
    }
    events = [e async for e in run_agents(graph, state)]
    return events, events[-1]["state"]


def _done_agents(events) -> list[str]:
    return [e["agent"] for e in events if e["type"] == "step" and e["status"] == "done"]


async def test_document_question_runs_full_pipeline(services: Services, llm: ScriptedLLM):
    await _index(services)
    events, final = await _run(services, "Who was Marcus Aurelius?")

    assert _done_agents(events) == ["language", "router", "planner", "retriever", "grader", "generator", "validator"]
    sources = next(e["sources"] for e in events if e["type"] == "sources")
    assert sources[0]["index"] == 1 and "Marcus Aurelius" in sources[0]["text"]
    assert all(s["document_id"] == "doc-u1" for s in sources)
    tokens = "".join(e["text"] for e in events if e["type"] == "token")
    assert tokens.strip() == llm.answer
    assert final["answer"] == llm.answer
    assert final["validation"] == {"grounded": True, "score": 0.9, "issues": []}
    # The generator got numbered sources and was told to answer in English
    gen = next(c for c in llm.calls if c["purpose"] == "generator")
    assert "[1] (u1.pdf, p. 1)" in gen["messages"][0]["content"]
    assert "Write the answer in English" in gen["messages"][0]["content"]


async def test_chitchat_skips_retrieval(services: Services, llm: ScriptedLLM):
    events, final = await _run(services, "hello there!")
    assert _done_agents(events) == ["language", "router", "generator"]
    assert not any(e["type"] == "sources" for e in events)
    assert llm.purposes() == ["router", "generator"]


async def test_corrective_retry_replans_when_nothing_is_relevant(services: Services, llm: ScriptedLLM):
    await _index(services)
    llm.grader_relevant = []  # grader rejects every passage
    events, final = await _run(services, "What did the emperor eat for breakfast?")

    assert llm.purposes() == ["router", "planner", "grader", "planner", "grader", "generator"]
    replan = [c for c in llm.calls if c["purpose"] == "planner"][1]
    assert "found nothing relevant" in replan["messages"][1]["content"]
    assert final["sources"] == []
    gen = next(c for c in llm.calls if c["purpose"] == "generator")
    assert "found nothing relevant" in gen["messages"][0]["content"]
    assert "validator" not in _done_agents(events)


async def test_no_documents_uploaded(services: Services, llm: ScriptedLLM):
    await services.vector_store.ensure_collection()
    events, final = await _run(services, "Summarize my report", has_documents=False)
    assert "No documents uploaded yet" in [e.get("summary") for e in events if e["type"] == "step"]
    gen = next(c for c in llm.calls if c["purpose"] == "generator")
    assert "has not uploaded any documents" in gen["messages"][0]["content"]
    assert llm.purposes().count("planner") == 1  # no pointless retry without documents


async def test_unparsable_router_reply_falls_back_safely(services: Services, llm: ScriptedLLM):
    await _index(services)
    llm.router_reply = "Sorry, I can't produce JSON today."
    events, final = await _run(services, "Who was Marcus Aurelius?")
    assert final["intent"] == "documents" and final["query_type"] == "SIMPLE_QA"
    assert final["answer"]


async def test_history_is_sent_to_router_and_generator(services: Services, llm: ScriptedLLM):
    await _index(services)
    history = [
        {"role": "user", "content": "Tell me about Marcus Aurelius"},
        {"role": "assistant", "content": "He was an emperor [1]."},
    ]
    llm.router_reply = (
        '{"intent": "documents", "query_type": "SIMPLE_QA", "standalone_question": "What did Marcus Aurelius write?"}'
    )
    events, final = await _run(services, "What did he write?", history=history)
    router = next(c for c in llm.calls if c["purpose"] == "router")
    assert "USER: Tell me about Marcus Aurelius" in router["messages"][1]["content"]
    router_step = next(e for e in events if e["type"] == "step" and e["agent"] == "router" and e["status"] == "done")
    assert router_step["data"]["rewritten"] is True
    assert final["standalone_question"] == "What did Marcus Aurelius write?"
    gen = next(c for c in llm.calls if c["purpose"] == "generator")
    assert [m["role"] for m in gen["messages"]] == ["system", "user", "assistant", "user"]


async def test_llm_failure_propagates_as_llm_error(services: Services, llm: ScriptedLLM):
    llm.fail_with = LLMError("The LLM provider rejected the API key. Check LLM_API_KEY.")
    with pytest.raises(LLMError, match="API key"):
        await _run(services, "Who was Marcus Aurelius?")
