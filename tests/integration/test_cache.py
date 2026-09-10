"""Retrieval cache behaviour: cold/warm, corpus-version invalidation, failure."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.services.cache import RetrievalCache, _shared_redis

PAYLOAD = {"query": "orbit telemetry retention", "top_k": 5, "strategy": "hybrid", "rerank": False}


def test_cold_request_then_warm_request(client: TestClient, corpus_document: dict) -> None:
    query = f"orbit telemetry retention {corpus_document['marker']}"
    body = {"query": query, "top_k": 5, "strategy": "hybrid", "rerank": False}

    cold = client.post("/v1/search", json=body)
    assert cold.status_code == 200, cold.text
    assert cold.json()["cached"] is False

    warm = client.post("/v1/search", json=body)
    assert warm.status_code == 200, warm.text
    assert warm.json()["cached"] is True
    # A cache hit must return the same ranking, not merely the same shape.
    assert [h["chunk_id"] for h in warm.json()["hits"]] == [h["chunk_id"] for h in cold.json()["hits"]]


def test_ingesting_a_document_invalidates_cached_rankings(client: TestClient, corpus_document: dict) -> None:
    query = f"orbit telemetry retention {corpus_document['marker']}"
    body = {"query": query, "top_k": 5, "strategy": "hybrid", "rerank": False}

    assert client.post("/v1/search", json=body).json()["cached"] is False
    assert client.post("/v1/search", json=body).json()["cached"] is True

    # A second upload bumps the corpus version, so the previous entry is stale.
    marker = corpus_document["marker"]
    extra = client.post(
        "/v1/documents",
        files={
            "file": (
                f"orbit-extra-{marker}.md",
                f"# Extra {marker}\n\n## Note\nOrbit telemetry retention note {marker}.\n".encode(),
                "text/markdown",
            )
        },
    )
    assert extra.status_code == 202, extra.text

    after = client.post("/v1/search", json=body)
    assert after.status_code == 200, after.text
    assert after.json()["cached"] is False, "cache survived a corpus version bump"

    client.delete(f"/v1/documents/{extra.json()['id']}")


def test_deleting_a_document_invalidates_cached_rankings(client: TestClient, corpus_document: dict) -> None:
    query = f"orbit telemetry retention {corpus_document['marker']}"
    body = {"query": query, "top_k": 5, "strategy": "hybrid", "rerank": False}

    assert client.post("/v1/search", json=body).json()["cached"] is False
    assert client.post("/v1/search", json=body).json()["cached"] is True

    assert client.delete(f"/v1/documents/{corpus_document['id']}").status_code == 204
    assert client.post("/v1/search", json=body).json()["cached"] is False


async def test_cache_degrades_gracefully_without_redis(monkeypatch) -> None:
    """Redis being unreachable must disable caching, not break retrieval."""
    cache = RetrievalCache()

    class BrokenRedis:
        async def get(self, *_args, **_kwargs):
            raise ConnectionError("redis is down")

        async def setex(self, *_args, **_kwargs):
            raise ConnectionError("redis is down")

        async def incr(self, *_args, **_kwargs):
            raise ConnectionError("redis is down")

    cache.redis = BrokenRedis()  # type: ignore[assignment]

    assert await cache.get("q", PAYLOAD) is None
    assert await cache.corpus_version() == 0
    # set/bump must swallow the failure rather than propagate it
    await cache.set("q", PAYLOAD, [{"chunk_id": "x"}])
    await cache.bump_corpus_version()


def test_different_configs_do_not_collide_in_cache(client: TestClient, corpus_document: dict) -> None:
    query = f"orbit telemetry retention {corpus_document['marker']}"
    hybrid = {"query": query, "top_k": 5, "strategy": "hybrid", "rerank": False}
    sparse = {"query": query, "top_k": 5, "strategy": "sparse", "rerank": False}

    assert client.post("/v1/search", json=hybrid).json()["cached"] is False
    # A different strategy must not be served the hybrid entry.
    assert client.post("/v1/search", json=sparse).json()["cached"] is False
    assert client.post("/v1/search", json=hybrid).json()["cached"] is True


@pytest.fixture(autouse=True)
def _redis_available() -> None:
    try:
        import redis as redis_lib

        client = redis_lib.Redis.from_url(
            settings.redis_url, socket_connect_timeout=2, socket_timeout=2
        )
        client.ping()
        client.close()
    except Exception:  # pragma: no cover - environment dependent
        pytest.skip("Redis is not reachable")


async def test_shared_client_is_reused_within_an_event_loop() -> None:
    """Regression: a new connection pool was built for every retriever."""
    assert RetrievalCache().redis is RetrievalCache().redis is _shared_redis()
