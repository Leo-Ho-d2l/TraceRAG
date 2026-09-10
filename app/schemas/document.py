import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.db.models import DocumentStatus


class DocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    filename: str
    mime_type: str
    sha256: str
    status: DocumentStatus
    error_message: str | None
    created_at: datetime
    completed_at: datetime | None


class DocumentList(BaseModel):
    items: list[DocumentOut]
    total: int
