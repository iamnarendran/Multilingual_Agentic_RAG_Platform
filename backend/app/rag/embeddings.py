"""Dense multilingual embeddings.

Two providers behind one interface:
- ``fastembed``: runs intfloat/multilingual-e5-large locally on CPU via ONNX (free, no torch).
- ``openai``: any OpenAI-compatible /embeddings endpoint.

E5 models expect "query: " / "passage: " prefixes, which we add here.
"""

from __future__ import annotations

import asyncio
import logging
import threading
from typing import Protocol

from app.config import Settings

logger = logging.getLogger(__name__)


class EmbeddingModelError(RuntimeError):
    """The embedding model could not be loaded (message is safe to show to users)."""


class Embedder(Protocol):
    dim: int
    model_name: str

    async def embed_documents(self, texts: list[str]) -> list[list[float]]: ...

    async def embed_queries(self, texts: list[str]) -> list[list[float]]: ...


def _prefix(model_name: str, kind: str, texts: list[str]) -> list[str]:
    if "e5" in model_name.lower():
        return [f"{kind}: {t}" for t in texts]
    return texts


class FastEmbedEmbedder:
    def __init__(self, model_name: str, dim: int, batch_size: int = 16, cache_dir: str | None = None):
        self.model_name = model_name
        self.dim = dim
        self.batch_size = batch_size
        self.cache_dir = cache_dir
        self._model = None
        self._lock = threading.Lock()

    def _load(self):
        with self._lock:
            if self._model is None:
                from fastembed import TextEmbedding

                logger.info("Loading embedding model %s (first run downloads it)...", self.model_name)
                try:
                    self._model = TextEmbedding(self.model_name, cache_dir=self.cache_dir)
                except Exception as exc:
                    raise EmbeddingModelError(
                        f"Couldn't load the embedding model {self.model_name}. The first upload downloads it "
                        "(about 2 GB) from huggingface.co, so the server needs internet access, or set "
                        "EMBEDDING_PROVIDER=openai to use an embeddings API instead."
                    ) from exc
                logger.info("Embedding model ready")
        return self._model

    def _embed(self, texts: list[str]) -> list[list[float]]:
        model = self._load()
        return [vec.tolist() for vec in model.embed(texts, batch_size=self.batch_size)]

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return await asyncio.to_thread(self._embed, _prefix(self.model_name, "passage", texts))

    async def embed_queries(self, texts: list[str]) -> list[list[float]]:
        return await asyncio.to_thread(self._embed, _prefix(self.model_name, "query", texts))


class OpenAICompatibleEmbedder:
    def __init__(self, model_name: str, dim: int, api_key: str, base_url: str, batch_size: int = 64):
        from openai import AsyncOpenAI

        self.model_name = model_name
        self.dim = dim
        self.batch_size = batch_size
        self._client = AsyncOpenAI(api_key=api_key or "missing", base_url=base_url)

    async def _embed(self, texts: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for i in range(0, len(texts), self.batch_size):
            resp = await self._client.embeddings.create(model=self.model_name, input=texts[i : i + self.batch_size])
            vectors.extend(item.embedding for item in sorted(resp.data, key=lambda d: d.index))
        return vectors

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return await self._embed(_prefix(self.model_name, "passage", texts))

    async def embed_queries(self, texts: list[str]) -> list[list[float]]:
        return await self._embed(_prefix(self.model_name, "query", texts))


def create_embedder(settings: Settings) -> Embedder:
    if settings.embedding_provider == "openai":
        return OpenAICompatibleEmbedder(
            settings.embedding_model,
            settings.embedding_dim,
            api_key=settings.embedding_api_key or settings.llm_api_key,
            base_url=settings.embedding_base_url or settings.llm_base_url,
        )
    if settings.embedding_provider == "fastembed":
        return FastEmbedEmbedder(
            settings.embedding_model,
            settings.embedding_dim,
            batch_size=settings.embedding_batch_size,
            cache_dir=str(settings.model_cache_dir) if settings.model_cache_dir else None,
        )
    raise ValueError(f"Unknown EMBEDDING_PROVIDER: {settings.embedding_provider}")
