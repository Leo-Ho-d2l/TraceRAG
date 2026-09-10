from __future__ import annotations

import time
import uuid
from typing import Any

from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Chunk, Document, DocumentStatus
from app.retrieval.hybrid import HybridRetriever, RetrievalHit


class SearchDocumentsArgs(BaseModel):
    query: str = Field(min_length=2, max_length=2000)
    top_k: int = Field(default=6, ge=1, le=12)


class ReadSectionArgs(BaseModel):
    document_id: uuid.UUID
    section_title: str = Field(min_length=1, max_length=500)
    max_chunks: int = Field(default=6, ge=1, le=12)


class DocumentMetadataArgs(BaseModel):
    document_id: uuid.UUID


TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "search_documents",
            "description": "Hybrid-search the enterprise corpus and return the most relevant evidence chunks.",
            "parameters": SearchDocumentsArgs.model_json_schema(),
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_document_section",
            "description": "Read adjacent chunks from a known document section when broader context is needed.",
            "parameters": ReadSectionArgs.model_json_schema(),
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_document_metadata",
            "description": "Inspect document metadata such as filename, ingestion status and processing metadata.",
            "parameters": DocumentMetadataArgs.model_json_schema(),
        },
    },
]


class AgentTools:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.retriever = HybridRetriever(session)

    async def execute(
        self,
        name: str,
        arguments: dict[str, Any],
        evidence: list[dict[str, Any]],
    ) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any]]:
        started = time.perf_counter()
        ok = True
        try:
            if name == "search_documents":
                parsed = SearchDocumentsArgs.model_validate(arguments)
                hits, _ = await self.retriever.retrieve(parsed.query, top_k=parsed.top_k, rerank=True)
                added = self._merge_evidence(evidence, hits)
                result = {"evidence": [self._evidence_for_model(item) for item in added]}
            elif name == "read_document_section":
                parsed = ReadSectionArgs.model_validate(arguments)
                hits = await self._read_section(parsed)
                added = self._merge_evidence(evidence, hits)
                result = {"evidence": [self._evidence_for_model(item) for item in added]}
            elif name == "get_document_metadata":
                parsed = DocumentMetadataArgs.model_validate(arguments)
                result = await self._metadata(parsed)
            else:
                ok = False
                result = {"error": f"unknown tool: {name}"}
        except ValidationError as exc:
            ok = False
            result = {"error": "invalid tool arguments", "details": exc.errors(include_url=False)}
        except Exception as exc:
            ok = False
            result = {"error": str(exc)}
        trace = {
            "tool": name,
            "arguments": arguments,
            "ok": ok,
            "latency_ms": round((time.perf_counter() - started) * 1000, 2),
        }
        return result, evidence, trace

    async def _read_section(self, args: ReadSectionArgs) -> list[RetrievalHit]:
        stmt = (
            select(Chunk, Document.filename)
            .join(Document, Document.id == Chunk.document_id)
            .where(Document.status == DocumentStatus.ready)
            .where(Chunk.document_id == args.document_id)
            .where(Chunk.section_title == args.section_title)
            .order_by(Chunk.ordinal)
            .limit(args.max_chunks)
        )
        rows = (await self.session.execute(stmt)).all()
        return [
            RetrievalHit(
                chunk_id=chunk.id,
                document_id=chunk.document_id,
                filename=filename,
                section_title=chunk.section_title,
                page_number=chunk.page_number,
                content=chunk.content,
                score=1.0,
                metadata=chunk.metadata_ or {},
            )
            for chunk, filename in rows
        ]

    async def _metadata(self, args: DocumentMetadataArgs) -> dict[str, Any]:
        document = await self.session.scalar(select(Document).where(Document.id == args.document_id))
        if document is None:
            return {"error": "document not found"}
        return {
            "document_id": str(document.id),
            "filename": document.filename,
            "status": document.status.value,
            "metadata": document.metadata_,
            "created_at": document.created_at.isoformat(),
        }

    @staticmethod
    def _merge_evidence(
        evidence: list[dict[str, Any]], hits: list[RetrievalHit]
    ) -> list[dict[str, Any]]:
        existing = {item["chunk_id"] for item in evidence}
        added: list[dict[str, Any]] = []
        for hit in hits:
            key = str(hit.chunk_id)
            if key in existing:
                continue
            item = {
                "label": f"S{len(evidence) + 1}",
                "chunk_id": key,
                "document_id": str(hit.document_id),
                "filename": hit.filename,
                "section_title": hit.section_title,
                "page_number": hit.page_number,
                "content": hit.content,
                "score": hit.score,
            }
            evidence.append(item)
            added.append(item)
            existing.add(key)
        return added

    @staticmethod
    def _evidence_for_model(item: dict[str, Any]) -> dict[str, Any]:
        return {
            "source": f"[{item['label']}]",
            "filename": item["filename"],
            "section": item["section_title"],
            "page": item["page_number"],
            "content": item["content"],
        }
