"""Test fixtures: everything runs offline with a scripted LLM and a deterministic embedder."""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import AsyncIterator, Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.agents.llm import LLMError, Usage
from app.config import Settings
from app.db import create_engine, create_sessionmaker
from app.main import create_app
from app.rag.sparse import tokenize
from app.rag.vector_store import VectorStore
from app.services import Services

SAMPLE_DOCS = Path(__file__).resolve().parents[2] / "data" / "sample_docs"
DIM = 64


class FakeEmbedder:
    """Bag-of-words hashing embedder: texts sharing words get similar vectors."""

    model_name = "fake-embedder"
    dim = DIM

    def _vec(self, text: str) -> list[float]:
        vec = [0.0] * DIM
        for tok in tokenize(text):
            vec[int(hashlib.md5(tok.encode()).hexdigest(), 16) % DIM] += 1.0
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        return [v / norm for v in vec]

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._vec(t) for t in texts]

    async def embed_queries(self, texts: list[str]) -> list[list[float]]:
        return [self._vec(t) for t in texts]


class ScriptedLLM:
    """Answers each agent's prompt with plausible canned output; records every call."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self.grader_relevant: list[int] | None = None  # None -> all candidates relevant
        self.router_reply: str | None = None
        self.fail_with: Exception | None = None
        self.answer = "Marcus Aurelius was a Roman emperor and Stoic philosopher [1]."

    @staticmethod
    def _last_user(messages: list[dict[str, str]]) -> str:
        return next(m["content"] for m in reversed(messages) if m["role"] == "user")

    async def complete(self, messages, *, model, temperature=0.2, max_tokens=800, json_mode=False, purpose=""):
        self.calls.append({"purpose": purpose, "messages": messages, "model": model})
        if self.fail_with:
            raise self.fail_with
        user = self._last_user(messages)
        if purpose == "router":
            if self.router_reply is not None:
                return self.router_reply, Usage(10, 5)
            latest = user.split("Latest message:", 1)[-1].strip()
            intent = "chitchat" if re.match(r"^(hi|hello|thanks)\b", latest, re.I) else "documents"
            return json.dumps({"intent": intent, "query_type": "SIMPLE_QA", "standalone_question": latest}), Usage(
                10, 5
            )
        if purpose == "planner":
            question = user.split("\n", 1)[0].split(": ", 1)[-1]
            return json.dumps({"queries": [question, "emperor philosopher"]}), Usage(10, 5)
        if purpose == "grader":
            n = len(re.findall(r"^\[\d+\]", user, re.M))
            relevant = list(range(1, n + 1)) if self.grader_relevant is None else self.grader_relevant
            return json.dumps({"relevant": relevant, "sufficient": bool(relevant), "feedback": ""}), Usage(10, 5)
        if purpose == "validator":
            return json.dumps({"grounded": True, "score": 0.9, "issues": []}), Usage(10, 5)
        return "{}", Usage()

    async def stream(
        self, messages, *, model, temperature=0.3, max_tokens=2000, purpose="", usage=None
    ) -> AsyncIterator[str]:
        self.calls.append({"purpose": purpose, "messages": messages, "model": model})
        if self.fail_with:
            raise self.fail_with
        for word in self.answer.split(" "):
            yield word + " "
        if usage is not None:
            usage.add(Usage(20, 10))

    def purposes(self) -> list[str]:
        return [c["purpose"] for c in self.calls]


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        environment="test",
        data_dir=tmp_path,
        database_url=f"sqlite+aiosqlite:///{(tmp_path / 'test.db').as_posix()}",
        qdrant_url=":memory:",
        embedding_dim=DIM,
        llm_api_key="test-key",
        jwt_secret="test-secret-" + "x" * 40,
        chunk_size=400,
        chunk_overlap=60,
        _env_file=None,
    )


@pytest.fixture
def llm() -> ScriptedLLM:
    return ScriptedLLM()


@pytest.fixture
def services(settings: Settings, llm: ScriptedLLM) -> Services:
    engine = create_engine(settings.resolved_database_url)
    return Services(
        settings=settings,
        engine=engine,
        sessionmaker=create_sessionmaker(engine),
        embedder=FakeEmbedder(),
        vector_store=VectorStore.from_settings(settings),
        llm=llm,
    )


@pytest.fixture
def client(services: Services) -> Iterator[TestClient]:
    with TestClient(create_app(services=services)) as c:
        yield c


def register(client: TestClient, email: str = "asha@example.com", name: str = "Asha") -> dict[str, str]:
    resp = client.post("/api/auth/register", json={"email": email, "name": name, "password": "correct horse battery"})
    assert resp.status_code == 201, resp.text
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


def parse_sse(body: str) -> list[tuple[str, dict[str, Any]]]:
    events = []
    for block in body.strip().split("\n\n"):
        lines = dict(line.split(": ", 1) for line in block.split("\n") if ": " in line)
        events.append((lines["event"], json.loads(lines["data"])))
    return events


__all__ = ["LLMError", "SAMPLE_DOCS", "ScriptedLLM", "parse_sse", "register"]
