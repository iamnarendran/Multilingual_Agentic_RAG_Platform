from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, HTTPException, UploadFile, status
from sqlalchemy import select

from app.api.deps import CurrentUser, DbDep, ServicesDep
from app.db import Document
from app.rag.ingestion import ingest_document
from app.schemas import DocumentOut

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/documents", tags=["documents"])

_READ_CHUNK = 1024 * 1024


def _safe_name(filename: str) -> str:
    name = Path(filename).name.strip() or "document"
    return name[:200]


@router.post("", response_model=DocumentOut, status_code=status.HTTP_202_ACCEPTED)
async def upload_document(
    file: UploadFile,
    background: BackgroundTasks,
    user: CurrentUser,
    session: DbDep,
    services: ServicesDep,
) -> Document:
    settings = services.settings
    filename = _safe_name(file.filename or "")
    ext = Path(filename).suffix.lower().lstrip(".")
    if ext not in settings.allowed_extension_set:
        allowed = ", ".join(sorted(settings.allowed_extension_set))
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, f"Unsupported file type. Allowed: {allowed}.")

    limit = settings.max_upload_mb * 1024 * 1024
    data = bytearray()
    while chunk := await file.read(_READ_CHUNK):
        data.extend(chunk)
        if len(data) > limit:
            raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, f"File is larger than {settings.max_upload_mb} MB.")
    if not data:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "The file is empty.")

    doc = Document(
        user_id=user.id,
        filename=filename,
        content_type=file.content_type,
        size_bytes=len(data),
        storage_path="",
        status="processing",
    )
    session.add(doc)
    await session.flush()  # assigns doc.id

    user_dir = settings.upload_dir / user.id
    path = user_dir / f"{doc.id}.{ext}"

    def _write() -> None:
        user_dir.mkdir(parents=True, exist_ok=True)
        path.write_bytes(bytes(data))

    await asyncio.to_thread(_write)
    doc.storage_path = str(path)
    await session.commit()

    background.add_task(ingest_document, services, doc.id)
    return doc


@router.get("", response_model=list[DocumentOut])
async def list_documents(user: CurrentUser, session: DbDep) -> list[Document]:
    result = await session.scalars(
        select(Document).where(Document.user_id == user.id).order_by(Document.created_at.desc())
    )
    return list(result)


async def _get_owned(session: DbDep, user_id: str, document_id: str) -> Document:
    doc = await session.get(Document, document_id)
    if doc is None or doc.user_id != user_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found.")
    return doc


@router.get("/{document_id}", response_model=DocumentOut)
async def get_document(document_id: str, user: CurrentUser, session: DbDep) -> Document:
    return await _get_owned(session, user.id, document_id)


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(document_id: str, user: CurrentUser, session: DbDep, services: ServicesDep) -> None:
    doc = await _get_owned(session, user.id, document_id)
    await services.vector_store.delete_document(user_id=user.id, document_id=doc.id)
    if doc.storage_path:
        await asyncio.to_thread(Path(doc.storage_path).unlink, missing_ok=True)
    await session.delete(doc)
    await session.commit()
