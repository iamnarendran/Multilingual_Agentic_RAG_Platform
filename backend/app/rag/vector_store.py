"""Qdrant vector store with hybrid (dense + BM25 sparse) search fused by Reciprocal Rank Fusion.

Every point carries ``user_id`` and every query is filtered by it, so users can never see each
other's documents.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from typing import Any

from qdrant_client import AsyncQdrantClient, models

from app.config import Settings
from app.rag.chunking import Chunk
from app.rag.sparse import SparseVector

logger = logging.getLogger(__name__)

DENSE = "dense"
SPARSE = "bm25"


@dataclass
class SearchHit:
    id: str
    score: float
    text: str
    document_id: str
    filename: str
    page: int | None
    page_end: int | None
    chunk_index: int
    language: str | None

    def to_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


class VectorStore:
    def __init__(self, client: AsyncQdrantClient, collection: str, dim: int, *, embedded: bool = False):
        self.client = client
        self.collection = collection
        self.dim = dim
        self.embedded = embedded  # in-process Qdrant (dev/tests) rather than a Qdrant server

    @classmethod
    def from_settings(cls, settings: Settings) -> VectorStore:
        embedded = not settings.qdrant_url or settings.qdrant_url == ":memory:"
        if settings.qdrant_url == ":memory:":
            client = AsyncQdrantClient(location=":memory:")
        elif settings.qdrant_url:
            client = AsyncQdrantClient(url=settings.qdrant_url, api_key=settings.qdrant_api_key, timeout=60)
        else:
            path = settings.data_dir / "qdrant"
            path.mkdir(parents=True, exist_ok=True)
            client = AsyncQdrantClient(path=str(path))
        # Include the dimension in the name so switching embedding models never mixes vectors.
        name = f"{settings.qdrant_collection}_{settings.embedding_dim}"
        return cls(client, name, settings.embedding_dim, embedded=embedded)

    async def ensure_collection(self) -> None:
        if await self.client.collection_exists(self.collection):
            return
        logger.info("Creating Qdrant collection %s", self.collection)
        await self.client.create_collection(
            self.collection,
            vectors_config={DENSE: models.VectorParams(size=self.dim, distance=models.Distance.COSINE)},
            sparse_vectors_config={SPARSE: models.SparseVectorParams(modifier=models.Modifier.IDF)},
        )
        if self.embedded:
            return  # payload indexes only exist on a Qdrant server
        await self.client.create_payload_index(
            self.collection, "user_id", models.KeywordIndexParams(type=models.KeywordIndexType.KEYWORD, is_tenant=True)
        )
        await self.client.create_payload_index(self.collection, "document_id", models.PayloadSchemaType.KEYWORD)

    async def upsert_chunks(
        self,
        *,
        user_id: str,
        document_id: str,
        filename: str,
        language: str | None,
        chunks: list[Chunk],
        dense: list[list[float]],
        sparse: list[SparseVector],
        batch_size: int = 64,
    ) -> None:
        points = [
            models.PointStruct(
                id=str(uuid.uuid5(uuid.NAMESPACE_URL, f"{document_id}:{i}")),
                vector={
                    DENSE: dense[i],
                    SPARSE: models.SparseVector(indices=sparse[i].indices, values=sparse[i].values),
                },
                payload={
                    "user_id": user_id,
                    "document_id": document_id,
                    "filename": filename,
                    "language": language,
                    "chunk_index": i,
                    "page": chunk.page,
                    "page_end": chunk.page_end,
                    "text": chunk.text,
                },
            )
            for i, chunk in enumerate(chunks)
        ]
        for start in range(0, len(points), batch_size):
            await self.client.upsert(self.collection, points=points[start : start + batch_size], wait=True)

    def _filter(self, user_id: str, document_ids: list[str] | None = None) -> models.Filter:
        must: list[models.Condition] = [models.FieldCondition(key="user_id", match=models.MatchValue(value=user_id))]
        if document_ids:
            must.append(models.FieldCondition(key="document_id", match=models.MatchAny(any=document_ids)))
        return models.Filter(must=must)

    async def hybrid_search(
        self,
        *,
        user_id: str,
        dense: list[float],
        sparse: SparseVector,
        limit: int = 20,
        document_ids: list[str] | None = None,
    ) -> list[SearchHit]:
        flt = self._filter(user_id, document_ids)
        prefetch = [models.Prefetch(query=dense, using=DENSE, limit=limit, filter=flt)]
        if sparse.indices:
            prefetch.append(
                models.Prefetch(
                    query=models.SparseVector(indices=sparse.indices, values=sparse.values),
                    using=SPARSE,
                    limit=limit,
                    filter=flt,
                )
            )
        result = await self.client.query_points(
            self.collection,
            prefetch=prefetch,
            query=models.FusionQuery(fusion=models.Fusion.RRF),
            query_filter=flt,
            limit=limit,
            with_payload=True,
        )
        hits = []
        for point in result.points:
            p = point.payload or {}
            hits.append(
                SearchHit(
                    id=str(point.id),
                    score=float(point.score),
                    text=p.get("text", ""),
                    document_id=p.get("document_id", ""),
                    filename=p.get("filename", ""),
                    page=p.get("page"),
                    page_end=p.get("page_end"),
                    chunk_index=int(p.get("chunk_index", 0)),
                    language=p.get("language"),
                )
            )
        return hits

    async def delete_document(self, *, user_id: str, document_id: str) -> None:
        await self.client.delete(
            self.collection,
            points_selector=models.FilterSelector(filter=self._filter(user_id, [document_id])),
            wait=True,
        )

    async def count(self, *, user_id: str) -> int:
        res = await self.client.count(self.collection, count_filter=self._filter(user_id), exact=True)
        return res.count

    async def close(self) -> None:
        await self.client.close()
