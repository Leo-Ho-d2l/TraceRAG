import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    question: str = Field(min_length=2, max_length=4000)
    thread_id: uuid.UUID | None = None
    mode: Literal["auto", "retrieve", "research"] = "auto"
    top_k: int = Field(default=6, ge=1, le=12)


class CitationOut(BaseModel):
    label: str
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    filename: str
    section_title: str | None = None
    page_number: int | None = None
    excerpt: str


class ToolTraceOut(BaseModel):
    step: int
    tool: str
    arguments: dict
    ok: bool
    latency_ms: float


class ChatResponse(BaseModel):
    thread_id: uuid.UUID
    route: str
    answer: str
    citations: list[CitationOut]
    tool_trace: list[ToolTraceOut] = Field(default_factory=list)
    total_steps: int = 0
    latency_ms: float


class MessageOut(BaseModel):
    id: uuid.UUID
    role: str
    content: str
    created_at: datetime
