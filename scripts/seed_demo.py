from __future__ import annotations

import hashlib
import mimetypes
import uuid
from pathlib import Path

from sqlalchemy import select

from app.core.config import settings
from app.db.models import Document, DocumentStatus
from app.db.session import SessionLocal
from app.ingestion.service import IngestionService

from app.core.event_loop import run_async

CORPUS_DIR = Path("sample_data/acmecloud")


async def main() -> None:
    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    async with SessionLocal() as session:
        for source in sorted(CORPUS_DIR.glob("*.md")):
            data = source.read_bytes()
            digest = hashlib.sha256(data).hexdigest()
            existing = await session.scalar(select(Document).where(Document.sha256 == digest))
            if existing:
                print(f"skip {source.name}: already indexed ({existing.id})")
                continue
            destination = settings.upload_dir / f"{uuid.uuid4().hex}{source.suffix}"
            destination.write_bytes(data)
            document = Document(
                id=uuid.uuid4(),
                filename=source.name,
                stored_path=str(destination.resolve()),
                mime_type=mimetypes.guess_type(source.name)[0] or "text/markdown",
                sha256=digest,
                status=DocumentStatus.queued,
                metadata_={"demo": True, "size_bytes": len(data)},
            )
            session.add(document)
            await session.commit()
            await IngestionService(session).ingest(document.id)
            print(f"indexed {source.name} ({document.id})")


if __name__ == "__main__":
    run_async(main())
