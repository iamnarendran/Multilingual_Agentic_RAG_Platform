"""Long-lived services shared across requests (created once at startup)."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from app.config import Settings
from app.rag.embeddings import Embedder
from app.rag.vector_store import VectorStore

if TYPE_CHECKING:
    from app.agents.llm import LLMClient


@dataclass
class Services:
    settings: Settings
    engine: AsyncEngine
    sessionmaker: async_sessionmaker
    embedder: Embedder
    vector_store: VectorStore
    llm: LLMClient
    graph: Any = None  # compiled LangGraph, set at startup
    # Limit concurrent ingestion jobs (OCR + embedding are CPU heavy)
    ingestion_semaphore: asyncio.Semaphore = field(default_factory=lambda: asyncio.Semaphore(2))
