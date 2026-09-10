from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.models import Chunk, Document, DocumentStatus
from app.ingestion.chunker import chunk_sections
from app.ingestion.parser import parse_document
from app.observability.tracing import span
from app.retrieval.embeddings import get_embedder
from app.services.cache import RetrievalCache

logger = logging.getLogger(__name__)


class IngestionService:
    def __init__(self, session: AsyncSession, cache: RetrievalCache | None = None) -> None:
        self.session = session
        self.cache = cache or RetrievalCache()
        self.embedder = get_embedder()

    async def ingest(self, document_id: uuid.UUID) -> int:
        document = await self.session.scalar(select(Document).where(Document.id == document_id))
        if document is None:
            raise ValueError(f"document {document_id} not found")

        document.status = DocumentStatus.processing
        document.error_message = None
        await self.session.commit()

        try:
            with span("ingestion.document", document_id=str(document_id), filename=document.filename):
                sections = await asyncio.to_thread(parse_document, Path(document.stored_path))
                chunks = chunk_sections(
                    sections,
                    target_chars=settings.chunk_target_chars,
                    overlap_chars=settings.chunk_overlap_chars,
                )
                if not chunks:
                    raise ValueError("document produced zero chunks")

                texts = [chunk.content for chunk in chunks]
                embeddings = await asyncio.to_thread(self.embedder.embed_documents, texts)
                if any(len(vector) != settings.embedding_dim for vector in embeddings):
                    raise ValueError("embedding dimension mismatch")

                await self.session.execute(delete(Chunk).where(Chunk.document_id == document_id))
                self.session.add_all(
                    [
                        Chunk(
                            id=uuid.uuid4(),
                            document_id=document_id,
                            ordinal=chunk.ordinal,
                            section_title=chunk.section_title,
                            page_number=chunk.page_number,
                            content=chunk.content,
                            token_count=chunk.token_count,
                            embedding=embedding,
                            metadata_={"source": document.filename},
                        )
                        for chunk, embedding in zip(chunks, embeddings, strict=True)
                    ]
                )
                document.status = DocumentStatus.ready
                document.completed_at = datetime.now(timezone.utc)
                document.metadata_ = {
                    **(document.metadata_ or {}),
                    "sections": len(sections),
                    "chunks": len(chunks),
                    "embedding_model": settings.embedding_model,
                }
                await self.session.commit()
                await self.cache.bump_corpus_version()
                logger.info(
                    "document ingested",
                    extra={"document_id": str(document_id)},
                )
                return len(chunks)
        except Exception as exc:
            await self.session.rollback()
            document = await self.session.scalar(select(Document).where(Document.id == document_id))
            if document is not None:
                document.status = DocumentStatus.failed
                document.error_message = str(exc)[:4000]
                await self.session.commit()
            logger.exception("document ingestion failed", extra={"document_id": str(document_id)})
            raise
