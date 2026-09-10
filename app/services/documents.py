from __future__ import annotations

import hashlib
import uuid
from pathlib import Path

from fastapi import UploadFile
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.models import Document, DocumentStatus
from app.ingestion.parser import SUPPORTED_EXTENSIONS


class UploadTooLargeError(ValueError):
    pass


class UnsupportedUploadError(ValueError):
    pass


async def save_upload(session: AsyncSession, upload: UploadFile) -> tuple[Document, bool]:
    suffix = Path(upload.filename or "upload").suffix.lower()
    if suffix not in SUPPORTED_EXTENSIONS:
        raise UnsupportedUploadError(f"supported extensions: {sorted(SUPPORTED_EXTENSIONS)}")

    temp_path = settings.upload_dir / f".{uuid.uuid4().hex}.part"
    digest = hashlib.sha256()
    size = 0
    max_bytes = settings.max_upload_mb * 1024 * 1024
    with temp_path.open("wb") as output:
        while chunk := await upload.read(1024 * 1024):
            size += len(chunk)
            if size > max_bytes:
                output.close()
                temp_path.unlink(missing_ok=True)
                raise UploadTooLargeError(f"file exceeds {settings.max_upload_mb} MB")
            digest.update(chunk)
            output.write(chunk)

    sha256 = digest.hexdigest()
    existing = await session.scalar(select(Document).where(Document.sha256 == sha256))
    if existing is not None:
        temp_path.unlink(missing_ok=True)
        return existing, False

    final_path = settings.upload_dir / f"{uuid.uuid4().hex}{suffix}"
    temp_path.replace(final_path)
    document = Document(
        id=uuid.uuid4(),
        filename=Path(upload.filename or final_path.name).name,
        stored_path=str(final_path.resolve()),
        mime_type=upload.content_type or "application/octet-stream",
        sha256=sha256,
        status=DocumentStatus.queued,
        metadata_={"size_bytes": size},
    )
    session.add(document)
    await session.commit()
    await session.refresh(document)
    return document, True


async def list_documents(session: AsyncSession, limit: int = 100) -> tuple[list[Document], int]:
    items = list((await session.scalars(select(Document).order_by(Document.created_at.desc()).limit(limit))).all())
    total = int(await session.scalar(select(func.count()).select_from(Document)) or 0)
    return items, total
