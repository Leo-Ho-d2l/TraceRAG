from __future__ import annotations

import logging
import uuid
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, File, HTTPException, UploadFile, status

from app.api.deps import Auth, DBSession
from app.core.config import settings
from app.db.models import Document
from app.db.session import SessionLocal
from app.ingestion.service import IngestionService
from app.schemas.document import DocumentList, DocumentOut
from app.services.documents import (
    UploadTooLargeError,
    UnsupportedUploadError,
    list_documents,
    save_upload,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/documents", tags=["documents"])


async def _ingest_inline(document_id: uuid.UUID) -> None:
    """Run ingestion inside the request's background task.

    ``IngestionService.ingest`` re-raises so that Celery can retry, and it has
    already recorded the failure on the document row by then. Letting that
    exception escape the background task produced an unhandled ASGI exception for
    a document that is correctly marked ``failed`` -- and made any ASGI test
    client raise instead of observing the recorded status.
    """
    try:
        async with SessionLocal() as session:
            await IngestionService(session).ingest(document_id)
    except Exception:
        logger.exception("inline ingestion failed", extra={"document_id": str(document_id)})


def _dispatch_celery(document_id: uuid.UUID) -> None:
    from app.worker import ingest_document_task

    ingest_document_task.delay(str(document_id))


@router.post("", response_model=DocumentOut, status_code=status.HTTP_202_ACCEPTED)
async def upload_document(
    background_tasks: BackgroundTasks,
    session: DBSession,
    _auth: Auth,
    file: UploadFile = File(...),
) -> DocumentOut:
    try:
        document, created = await save_upload(session, file)
    except (UploadTooLargeError, UnsupportedUploadError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if created:
        if settings.ingestion_mode == "celery":
            background_tasks.add_task(_dispatch_celery, document.id)
        else:
            background_tasks.add_task(_ingest_inline, document.id)
    return DocumentOut.model_validate(document)


@router.get("", response_model=DocumentList)
async def get_documents(session: DBSession, _auth: Auth) -> DocumentList:
    items, total = await list_documents(session)
    return DocumentList(items=[DocumentOut.model_validate(item) for item in items], total=total)


@router.get("/{document_id}", response_model=DocumentOut)
async def get_document(document_id: uuid.UUID, session: DBSession, _auth: Auth) -> DocumentOut:
    document = await session.get(Document, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="document not found")
    return DocumentOut.model_validate(document)


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(document_id: uuid.UUID, session: DBSession, _auth: Auth) -> None:
    document = await session.get(Document, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="document not found")
    stored_path = Path(document.stored_path)
    await session.delete(document)
    await session.commit()
    try:
        stored_path.unlink(missing_ok=True)
    except OSError:
        pass
    # Retrieval cache keys are versioned; bumping makes all previous entries stale.
    from app.services.cache import RetrievalCache

    await RetrievalCache().bump_corpus_version()
