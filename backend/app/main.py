"""FastAPI application factory.

Run with:  uvicorn --factory app.main:create_app --reload
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import update

from app.agents.graph import build_graph
from app.agents.llm import OpenAICompatibleLLM
from app.api import auth, chat, conversations, documents, health
from app.config import Settings, get_settings
from app.db import Document, create_engine, create_sessionmaker, init_db
from app.rag.embeddings import create_embedder
from app.rag.vector_store import VectorStore
from app.services import Services

logger = logging.getLogger("app")


def build_services(settings: Settings) -> Services:
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    engine = create_engine(settings.resolved_database_url)
    return Services(
        settings=settings,
        engine=engine,
        sessionmaker=create_sessionmaker(engine),
        embedder=create_embedder(settings),
        vector_store=VectorStore.from_settings(settings),
        llm=OpenAICompatibleLLM(settings),
    )


def create_app(settings: Settings | None = None, services: Services | None = None) -> FastAPI:
    settings = settings or (services.settings if services else get_settings())
    logging.basicConfig(
        level=settings.log_level.upper(),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        svc = services or build_services(settings)
        svc.settings.data_dir.mkdir(parents=True, exist_ok=True)
        await init_db(svc.engine)
        await svc.vector_store.ensure_collection()
        svc.graph = build_graph(svc)
        # Jobs interrupted by a restart will never finish; tell the user to re-upload.
        async with svc.sessionmaker() as session:
            await session.execute(
                update(Document)
                .where(Document.status == "processing")
                .values(status="failed", error="Processing was interrupted by a server restart. Please upload again.")
            )
            await session.commit()
        app.state.services = svc
        if not settings.llm_configured:
            logger.warning("LLM_API_KEY is not set: chat will return a configuration error until it is.")
        logger.info("%s v%s ready", settings.app_name, settings.app_version)
        yield
        await svc.vector_store.close()
        await svc.engine.dispose()

    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description="Multilingual agentic RAG API: upload documents in English and Indian languages, chat with them.",
        lifespan=lifespan,
        docs_url=f"{settings.api_prefix}/docs",
        openapi_url=f"{settings.api_prefix}/openapi.json",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    for module in (health, auth, documents, conversations, chat):
        app.include_router(module.router, prefix=settings.api_prefix)
    return app
