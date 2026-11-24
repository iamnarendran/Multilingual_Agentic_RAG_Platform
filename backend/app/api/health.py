from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import ServicesDep
from app.rag.extraction import installed_ocr_languages

router = APIRouter(tags=["health"])


@router.get("/health")
async def health(services: ServicesDep) -> dict:
    settings = services.settings
    try:
        vector_ok = await services.vector_store.client.collection_exists(services.vector_store.collection)
    except Exception:  # noqa: BLE001
        vector_ok = False
    return {
        "status": "ok" if vector_ok else "degraded",
        "version": settings.app_version,
        "llm": {
            "configured": settings.llm_configured,
            "base_url": settings.llm_base_url,
            "generator_model": settings.model_for("generator"),
            "fast_model": settings.llm_fast_model,
        },
        "embeddings": {"provider": settings.embedding_provider, "model": settings.embedding_model},
        "vector_store": {"ok": vector_ok, "mode": "embedded" if services.vector_store.embedded else "server"},
        "ocr": {"enabled": settings.ocr_enabled, "languages": sorted(installed_ocr_languages())},
        "limits": {"max_upload_mb": settings.max_upload_mb, "extensions": sorted(settings.allowed_extension_set)},
    }
