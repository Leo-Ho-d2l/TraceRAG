import asyncio
import uuid

from celery import Celery

from app.core.config import settings
from app.db.session import SessionLocal, engine
from app.ingestion.service import IngestionService

celery_app = Celery("tracerag", broker=settings.redis_url, backend=settings.redis_url)
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_track_started=True,
)


@celery_app.task(name="tracerag.ingest_document", autoretry_for=(Exception,), retry_backoff=True, max_retries=2)
def ingest_document_task(document_id: str) -> int:
    return asyncio.run(_ingest(uuid.UUID(document_id)))


async def _ingest(document_id: uuid.UUID) -> int:
    try:
        async with SessionLocal() as session:
            return await IngestionService(session).ingest(document_id)
    finally:
        # Celery invokes this coroutine through asyncio.run; dispose pooled async
        # connections before the next task creates a new event loop.
        await engine.dispose()
