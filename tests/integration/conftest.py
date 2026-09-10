"""Fixtures for database-backed integration tests.

These tests need a live PostgreSQL (with pgvector) and Redis. They are
self-contained: each test indexes its own uniquely-named document instead of
relying on `scripts/seed_demo.py` having been run, and removes it afterwards so
repeated local runs stay deterministic.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Iterator

import pytest
from fastapi.testclient import TestClient
from pgvector.psycopg import register_vector_async
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import settings
from app.main import app


@pytest.fixture(scope="session")
def client() -> Iterator[TestClient]:
    # TestClient runs the ASGI app in its own event loop; app.db.session
    # installs a psycopg-compatible loop policy at import time.
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def corpus_document(client: TestClient) -> Iterator[dict]:
    """Upload a unique markdown document and wait until ingestion is ready."""
    marker = uuid.uuid4().hex[:12]
    body = f"""# Orbit Handbook {marker}

## Telemetry retention
Project Orbit retains raw telemetry for exactly {marker} days in the standard tier.

## Escalation ladder
Orbit escalation for severity-one incidents targets a {marker}-minute acknowledgement window.
""".encode()

    response = client.post(
        "/v1/documents",
        files={"file": (f"orbit-{marker}.md", body, "text/markdown")},
    )
    assert response.status_code == 202, response.text
    document = response.json()

    detail = client.get(f"/v1/documents/{document['id']}")
    assert detail.status_code == 200
    assert detail.json()["status"] == "ready", detail.text

    yield {**document, "marker": marker}

    client.delete(f"/v1/documents/{document['id']}")


@pytest.fixture
async def session() -> AsyncIterator[AsyncSession]:
    """A session on its own NullPool engine.

    pytest-asyncio creates a fresh event loop per test, and the application's
    pooled engine would hand a connection bound to a previous loop to the next
    test. NullPool keeps each test's connection inside its own loop.
    """
    engine = create_async_engine(settings.database_url, poolclass=NullPool)

    @event.listens_for(engine.sync_engine, "connect")
    def _register_pgvector(dbapi_connection, _record) -> None:
        dbapi_connection.run_async(register_vector_async)

    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with factory() as db_session:
        yield db_session
    await engine.dispose()


@pytest.fixture
async def ingested_document(session: AsyncSession) -> AsyncIterator[dict]:
    """Index one uniquely-marked document on the test's own session.

    Tool tests must not depend on `scripts/seed_demo.py` having been run: a fresh
    clone would otherwise fail them.
    """
    from app.db.models import Document, DocumentStatus
    from app.ingestion.service import IngestionService

    marker = uuid.uuid4().hex[:12]
    path = settings.upload_dir / f"tools-{marker}.md"
    path.write_text(
        f"# Tool Fixture {marker}\n\n"
        f"## Ledger retention\n"
        f"The {marker} ledger keeps reconciliation records for {marker} days.\n",
        encoding="utf-8",
    )
    document = Document(
        id=uuid.uuid4(),
        filename=f"tools-{marker}.md",
        stored_path=str(path.resolve()),
        mime_type="text/markdown",
        sha256=uuid.uuid4().hex + uuid.uuid4().hex,
        status=DocumentStatus.queued,
        metadata_={"test": True},
    )
    session.add(document)
    await session.commit()
    await IngestionService(session).ingest(document.id)
    try:
        yield {"id": str(document.id), "marker": marker, "filename": document.filename}
    finally:
        await session.delete(document)
        await session.commit()
        path.unlink(missing_ok=True)
