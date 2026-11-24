"""Background ingestion: file -> text (OCR if needed) -> chunks -> embeddings -> Qdrant."""

from __future__ import annotations

import asyncio
import logging
import time
from pathlib import Path

from sqlalchemy import select

from app.db import Document
from app.rag.chunking import chunk_pages
from app.rag.embeddings import EmbeddingModelError
from app.rag.extraction import ExtractionError, OcrConfig, extract_document
from app.rag.language import detect_language
from app.rag.sparse import encode_document
from app.services import Services

logger = logging.getLogger(__name__)


async def ingest_document(services: Services, document_id: str) -> None:
    settings = services.settings
    async with services.ingestion_semaphore, services.sessionmaker() as session:
        doc = await session.get(Document, document_id)
        if doc is None:
            return
        started = time.perf_counter()
        try:
            data = await asyncio.to_thread(Path(doc.storage_path).read_bytes)
            ocr = OcrConfig(enabled=settings.ocr_enabled, languages=settings.ocr_languages, dpi=settings.ocr_dpi)
            extracted = await asyncio.to_thread(extract_document, doc.filename, data, ocr)

            chunks = chunk_pages(extracted.pages, settings.chunk_size, settings.chunk_overlap)
            if not chunks:
                raise ExtractionError("No readable text found in this file.")

            language = detect_language(extracted.text[:5000])
            texts = [c.text for c in chunks]
            dense = await services.embedder.embed_documents(texts)
            sparse = [encode_document(t) for t in texts]

            await services.vector_store.upsert_chunks(
                user_id=doc.user_id,
                document_id=doc.id,
                filename=doc.filename,
                language=language.code,
                chunks=chunks,
                dense=dense,
                sparse=sparse,
            )

            # The user may have deleted the document while we were processing it.
            still_exists = await session.scalar(select(Document.id).where(Document.id == doc.id))
            if not still_exists:
                await services.vector_store.delete_document(user_id=doc.user_id, document_id=doc.id)
                logger.info("Document %s was deleted during ingestion; discarded its chunks", doc.id)
                return

            doc.status = "ready"
            doc.error = None
            doc.language = language.code
            doc.page_count = extracted.page_count
            doc.chunk_count = len(chunks)
            doc.ocr_pages = extracted.ocr_pages
            doc.warnings = extracted.warnings or None
            logger.info(
                "Ingested %s: %d chunks, %d OCR pages, lang=%s in %.1fs",
                doc.filename,
                len(chunks),
                extracted.ocr_pages,
                language.code,
                time.perf_counter() - started,
            )
        except (ExtractionError, EmbeddingModelError) as exc:
            doc.status, doc.error = "failed", str(exc)
            logger.warning("Ingestion failed for %s: %s", doc.filename, exc)
        except Exception as exc:  # noqa: BLE001 - surface any failure to the user, keep the server alive
            logger.exception("Ingestion crashed for %s", doc.filename)
            doc.status, doc.error = "failed", f"Processing error: {exc}"
            try:  # don't leave half-indexed chunks behind
                await services.vector_store.delete_document(user_id=doc.user_id, document_id=doc.id)
            except Exception:  # noqa: BLE001
                logger.exception("Cleanup after failed ingestion also failed")
        await session.commit()
