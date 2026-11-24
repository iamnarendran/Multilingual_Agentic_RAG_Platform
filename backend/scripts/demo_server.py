"""Run the whole app offline: no API keys, no model downloads.

    cd backend && python -m scripts.demo_server        # API on http://localhost:8000

For UI development and demos. Everything is real (auth, uploads, OCR, chunking, hybrid search,
the agent graph, streaming) except two stand-ins:
  * a toy bag-of-words embedder instead of multilingual-e5, and
  * a scripted "LLM" whose answers simply quote the retrieved passages, labelled as demo mode.
Data is kept in memory and lost on exit.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import math
import re
import tempfile
from pathlib import Path

import uvicorn

from app.agents.llm import Usage
from app.config import Settings
from app.db import create_engine, create_sessionmaker
from app.main import create_app
from app.rag.sparse import tokenize
from app.rag.vector_store import VectorStore
from app.services import Services

DIM = 256


class ToyEmbedder:
    """Hashing bag-of-words vectors: texts that share words end up close together."""

    model_name = "demo-bag-of-words"
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


_SOURCE = re.compile(r"^\[(\d+)\] \((.*?)\)\n(.*?)(?=\n\n\[\d+\] \(|\Z)", re.S | re.M)


class ScriptedLLM:
    """Plays every agent with simple rules, with small delays so streaming is visible."""

    async def complete(self, messages, *, model, temperature=0.2, max_tokens=800, json_mode=False, purpose=""):
        await asyncio.sleep(0.35)
        user = next(m["content"] for m in reversed(messages) if m["role"] == "user")
        if purpose == "router":
            latest = user.split("Latest message:", 1)[-1].strip()
            chitchat = bool(re.match(r"^(hi|hello|hey|thanks|thank you|namaste|नमस्ते|வணக்கம்)\b", latest, re.I))
            qtype = "SUMMARIZATION" if re.search(r"summar|सारांश", latest, re.I) else "SIMPLE_QA"
            reply = {
                "intent": "chitchat" if chitchat else "documents",
                "query_type": qtype,
                "standalone_question": latest,
            }
            return json.dumps(reply, ensure_ascii=False), Usage(120, 30)
        if purpose == "planner":
            question = user.split("\n", 1)[0].split(": ", 1)[-1]
            keywords = " ".join(t for t in tokenize(question) if len(t) > 3)[:80]
            return json.dumps({"queries": [question, keywords or question]}, ensure_ascii=False), Usage(150, 40)
        if purpose == "grader":
            n = len(re.findall(r"^\[\d+\]", user, re.M))
            return json.dumps({"relevant": list(range(1, min(n, 4) + 1)), "sufficient": n > 0}), Usage(600, 20)
        if purpose == "validator":
            return json.dumps({"grounded": True, "score": 1.0, "issues": []}), Usage(700, 20)
        return "{}", Usage()

    async def stream(self, messages, *, model, temperature=0.3, max_tokens=2000, purpose="", usage=None):
        system = messages[0]["content"]
        sources = _SOURCE.findall(system)
        if sources:
            lines = ["*Demo mode: no language model is connected, so this just quotes the best passages.*", ""]
            for index, location, text in sources:
                flat = " ".join(text.split())
                end = re.search(r"(?<=[.!?।॥])\s", flat[40:])  # first sentence end after 40 chars
                sentence = (flat[: 40 + end.start()] if end else flat[:200])[:240]
                lines.append(f"- **{location}**: {sentence} [{index}]")
            text = "\n".join(lines)
        elif "friendly multilingual assistant" in system:
            text = (
                "Hello! This is the offline demo. Upload a document and ask about it; I'll quote the passages I find."
            )
        else:
            text = "I couldn't find anything about that in your documents. Try uploading one, or ask about what they cover."
        for token in re.findall(r"\S+\s*", text):
            await asyncio.sleep(0.025)
            yield token
        if usage is not None:
            usage.add(Usage(900, len(text) // 4))


def main() -> None:
    data_dir = Path(tempfile.mkdtemp(prefix="rag-demo-"))
    settings = Settings(
        environment="development",
        data_dir=data_dir,
        qdrant_url=":memory:",
        embedding_dim=DIM,
        llm_api_key="demo",
        cors_origins="http://localhost:3000",
        _env_file=None,
    )
    engine = create_engine(settings.resolved_database_url)
    services = Services(
        settings=settings,
        engine=engine,
        sessionmaker=create_sessionmaker(engine),
        embedder=ToyEmbedder(),
        vector_store=VectorStore.from_settings(settings),
        llm=ScriptedLLM(),
    )
    print(f"Demo API on http://localhost:8000 (data in {data_dir}, discarded on exit)")
    uvicorn.run(create_app(services=services), host="127.0.0.1", port=8000, log_level="warning")


if __name__ == "__main__":
    main()
