from __future__ import annotations

import asyncio
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any

from sqlalchemy import cast, func, select
from sqlalchemy.dialects.postgresql import TSVECTOR
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.models import Chunk, Document, DocumentStatus
from app.observability.tracing import span
from app.retrieval.embeddings import get_embedder
from app.retrieval.reranker import get_reranker
from app.retrieval.fusion import reciprocal_rank_fusion
from app.services.cache import RetrievalCache


@dataclass(slots=True)
class RetrievalHit:
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    filename: str
    section_title: str | None
    page_number: int | None
    content: str
    score: float
    dense_score: float | None = None
    sparse_score: float | None = None
    rrf_score: float | None = None
    rerank_score: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_cache(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["chunk_id"] = str(self.chunk_id)
        payload["document_id"] = str(self.document_id)
        return payload

    @classmethod
    def from_cache(cls, payload: dict[str, Any]) -> RetrievalHit:
        return cls(
            **{
                **payload,
                "chunk_id": uuid.UUID(payload["chunk_id"]),
                "document_id": uuid.UUID(payload["document_id"]),
            }
        )




def _lexical_tsquery(query: str):
    """Build a stopword-filtered OR tsquery for the lexical branch.

    ``plainto_tsquery`` conjoins every token, so a natural-language question
    only matches a chunk that contains *all* of its words. Because the stored
    ``search_vector`` uses the ``simple`` configuration -- which removes no
    stopwords -- questions such as "What is the Enterprise audit log retention
    period?" required 'what', 'is' and 'the' to appear in the chunk as well and
    matched 1 of 30 benchmark cases.

    This builds a disjunction of the question's content words instead, so
    ``ts_rank_cd`` can rank chunks matching more of them higher. Stopwords are
    decided by PostgreSQL's own ``english`` configuration (an empty tsvector),
    and lexemes are escaped with ``quote_literal`` so user text cannot alter the
    tsquery syntax.
    """
    lexeme = func.unnest(func.to_tsvector("simple", query)).table_valued("lexeme")
    or_body = (
        select(func.string_agg(func.quote_literal(lexeme.c.lexeme), " | "))
        .where(func.to_tsvector("english", lexeme.c.lexeme) != cast("", TSVECTOR))
    ).scalar_subquery()
    return func.to_tsquery("simple", or_body)


class HybridRetriever:
    def __init__(self, session: AsyncSession, cache: RetrievalCache | None = None) -> None:
        self.session = session
        self.cache = cache or RetrievalCache()
        self.embedder = get_embedder()
        self.reranker = get_reranker()

    async def retrieve(
        self,
        query: str,
        top_k: int | None = None,
        document_ids: list[uuid.UUID] | None = None,
        rerank: bool = True,
        strategy: str = "hybrid",
        use_cache: bool = True,
    ) -> tuple[list[RetrievalHit], bool]:
        top_k = top_k or settings.default_top_k
        if strategy not in {"dense", "sparse", "hybrid"}:
            raise ValueError("strategy must be dense, sparse, or hybrid")
        cache_payload = {
            "top_k": top_k,
            "strategy": strategy,
            "document_ids": sorted(str(v) for v in document_ids) if document_ids else None,
            "rerank": rerank,
            "dense_k": settings.dense_k,
            "sparse_k": settings.sparse_k,
        }
        if use_cache:
            cached = await self.cache.get(query, cache_payload)
            if cached is not None:
                return [RetrievalHit.from_cache(item) for item in cached], True

        with span("retrieval.query", query_length=len(query), top_k=top_k, strategy=strategy):
            if strategy == "dense":
                query_embedding = await asyncio.to_thread(self.embedder.embed_query, query)
                candidates = await self._dense(query_embedding, document_ids)
                for item in candidates:
                    item.score = item.dense_score or 0.0
            elif strategy == "sparse":
                candidates = await self._sparse(query, document_ids)
                for item in candidates:
                    item.score = item.sparse_score or 0.0
            else:
                query_embedding = await asyncio.to_thread(self.embedder.embed_query, query)
                # Dense and sparse share one AsyncSession, and SQLAlchemy forbids
                # concurrent operations on a session. Gathering them raised
                # InvalidRequestError("This session is provisioning a new
                # connection; concurrent operations are not permitted"), which
                # broke every hybrid request. Run them in sequence; each is a
                # single indexed query, so the cost is one extra round trip.
                dense_hits = await self._dense(query_embedding, document_ids)
                sparse_hits = await self._sparse(query, document_ids)
                candidates = self._fuse(dense_hits, sparse_hits)
            candidates = candidates[: max(top_k, settings.rerank_candidates)]
            if rerank and candidates and settings.rerank_backend != "none":
                documents = [item.content for item in candidates]
                scores = await asyncio.to_thread(self.reranker.score, query, documents)
                for item, score in zip(candidates, scores, strict=True):
                    item.rerank_score = float(score)
                    item.score = float(score)
                candidates.sort(key=lambda item: item.score, reverse=True)
            results = candidates[:top_k]

        if use_cache:
            await self.cache.set(query, cache_payload, [item.to_cache() for item in results])
        return results, False

    async def _dense(
        self, query_embedding: list[float], document_ids: list[uuid.UUID] | None
    ) -> list[RetrievalHit]:
        distance = Chunk.embedding.cosine_distance(query_embedding)
        stmt = (
            select(Chunk, Document.filename, (1.0 - distance).label("dense_score"))
            .join(Document, Document.id == Chunk.document_id)
            .where(Document.status == DocumentStatus.ready)
            .order_by(distance)
            .limit(settings.dense_k)
        )
        if document_ids:
            stmt = stmt.where(Chunk.document_id.in_(document_ids))
        rows = (await self.session.execute(stmt)).all()
        return [self._row_to_hit(chunk, filename, dense_score=float(score)) for chunk, filename, score in rows]

    async def _sparse(
        self, query: str, document_ids: list[uuid.UUID] | None
    ) -> list[RetrievalHit]:
        tsquery = _lexical_tsquery(query)
        rank = func.ts_rank_cd(Chunk.search_vector, tsquery)
        stmt = (
            select(Chunk, Document.filename, rank.label("sparse_score"))
            .join(Document, Document.id == Chunk.document_id)
            .where(Document.status == DocumentStatus.ready)
            .where(Chunk.search_vector.op("@@")(tsquery))
            .order_by(rank.desc())
            .limit(settings.sparse_k)
        )
        if document_ids:
            stmt = stmt.where(Chunk.document_id.in_(document_ids))
        rows = (await self.session.execute(stmt)).all()
        return [self._row_to_hit(chunk, filename, sparse_score=float(score)) for chunk, filename, score in rows]

    def _fuse(
        self, dense_hits: list[RetrievalHit], sparse_hits: list[RetrievalHit]
    ) -> list[RetrievalHit]:
        dense_ids = [hit.chunk_id for hit in dense_hits]
        sparse_ids = [hit.chunk_id for hit in sparse_hits]
        scores = reciprocal_rank_fusion([dense_ids, sparse_ids], settings.rrf_k)
        by_id: dict[uuid.UUID, RetrievalHit] = {}
        for hit in dense_hits + sparse_hits:
            existing = by_id.get(hit.chunk_id)
            if existing is None:
                by_id[hit.chunk_id] = hit
            else:
                if hit.dense_score is not None:
                    existing.dense_score = hit.dense_score
                if hit.sparse_score is not None:
                    existing.sparse_score = hit.sparse_score
        for chunk_id, hit in by_id.items():
            hit.rrf_score = scores.get(chunk_id, 0.0)
            hit.score = hit.rrf_score
        return sorted(by_id.values(), key=lambda item: item.score, reverse=True)

    @staticmethod
    def _row_to_hit(
        chunk: Chunk,
        filename: str,
        dense_score: float | None = None,
        sparse_score: float | None = None,
    ) -> RetrievalHit:
        return RetrievalHit(
            chunk_id=chunk.id,
            document_id=chunk.document_id,
            filename=filename,
            section_title=chunk.section_title,
            page_number=chunk.page_number,
            content=chunk.content,
            score=0.0,
            dense_score=dense_score,
            sparse_score=sparse_score,
            metadata=chunk.metadata_ or {},
        )
