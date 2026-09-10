import uuid
from typing import Any, Literal

from pydantic import BaseModel, Field


class SearchRequest(BaseModel):
    query: str = Field(min_length=2, max_length=2000)
    top_k: int = Field(default=6, ge=1, le=20)
    document_ids: list[uuid.UUID] | None = None
    rerank: bool = True
    strategy: Literal["dense", "sparse", "hybrid"] = "hybrid"


class SearchHitOut(BaseModel):
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
    metadata: dict[str, Any] = Field(default_factory=dict)


class SearchResponse(BaseModel):
    query: str
    hits: list[SearchHitOut]
    cached: bool = False
