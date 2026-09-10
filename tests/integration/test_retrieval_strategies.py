"""Retrieval correctness across dense, sparse, hybrid and reranked hybrid.

These are deliberately semantic assertions, not status-code checks: they guard
the defects found during debugging (sparse retrieval silently returning nothing,
and RRF not accumulating a chunk that both branches rank).
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.retrieval.hybrid import _lexical_tsquery


async def test_lexical_tsquery_drops_stopwords_and_disjoins(session: AsyncSession) -> None:
    """The rendered tsquery is 'a | b | c' over content words only."""
    statement = select(_lexical_tsquery("What is the Enterprise audit log retention period?"))
    tsquery = str((await session.execute(statement)).scalar())
    # quote_literal wraps each lexeme, hence the surrounding apostrophes.
    terms = [term.strip().strip("'") for term in tsquery.split("|")]
    assert len(terms) > 1, f"expected a disjunction, got {tsquery!r}"
    for stopword in ("what", "is", "the"):
        assert stopword not in terms, f"{stopword!r} should have been dropped: {tsquery!r}"
    assert "audit" in terms
    assert "retention" in terms


async def test_lexical_tsquery_returns_null_for_stopword_only_input(session: AsyncSession) -> None:
    statement = select(_lexical_tsquery("the and of"))
    assert (await session.execute(statement)).scalar() is None


def search(client: TestClient, query: str, **overrides) -> dict:
    payload = {"query": query, "top_k": 5, "strategy": "hybrid", "rerank": False}
    payload.update(overrides)
    response = client.post("/v1/search", json=payload)
    assert response.status_code == 200, response.text
    return response.json()


def test_dense_retrieval_returns_scored_hits(client: TestClient, corpus_document: dict) -> None:
    body = search(client, "Orbit telemetry retention standard tier", strategy="dense", top_k=10)
    assert body["hits"], "dense retrieval returned no hits"
    assert all(hit["dense_score"] is not None for hit in body["hits"])
    # Cosine similarity: higher is better and must be ordered descending.
    scores = [hit["dense_score"] for hit in body["hits"]]
    assert scores == sorted(scores, reverse=True)
    # Dense is semantic, so it need not rank first -- but it must recall the
    # document that actually contains the answer.
    assert f"orbit-{corpus_document['marker']}.md" in {
        hit["filename"] for hit in body["hits"]
    }


def test_sparse_retrieval_returns_hits_for_natural_language(client: TestClient, corpus_document: dict) -> None:
    """Regression: plainto_tsquery ANDed every token, so natural-language
    questions matched nothing and the lexical branch was dead."""
    body = search(
        client,
        "How long does Orbit retain raw telemetry in the standard tier?",
        strategy="sparse",
    )
    assert body["hits"], "sparse retrieval returned no hits for a natural-language question"
    assert all(hit["sparse_score"] is not None for hit in body["hits"])
    assert body["hits"][0]["filename"] == f"orbit-{corpus_document['marker']}.md"


def test_sparse_retrieval_handles_stopword_only_query(client: TestClient) -> None:
    """A query with no content words must return nothing rather than error."""
    body = search(client, "the and of", strategy="sparse")
    assert body["hits"] == []


def test_hybrid_fuses_both_branches(client: TestClient, corpus_document: dict) -> None:
    body = search(client, "Orbit telemetry retention standard tier", strategy="hybrid")
    assert body["hits"]
    # The best chunk is found by both branches, so RRF must give it a strictly
    # larger score than any single-branch contribution (1/(k+1)).
    top = body["hits"][0]
    assert top["rrf_score"] is not None
    assert top["rrf_score"] > 1.0 / 61.0, "RRF did not accumulate across dense and sparse"
    assert top["filename"] == f"orbit-{corpus_document['marker']}.md"


def test_hybrid_lower_rank_scores_lower(client: TestClient, corpus_document: dict) -> None:
    body = search(client, "Orbit escalation severity-one acknowledgement", strategy="hybrid")
    scores = [hit["rrf_score"] for hit in body["hits"]]
    assert scores == sorted(scores, reverse=True)


def test_rerank_populates_scores_and_reorders(client: TestClient, corpus_document: dict) -> None:
    query = "Orbit escalation severity-one acknowledgement window"
    without = search(client, query, strategy="hybrid", rerank=False)
    with_rerank = search(client, query, strategy="hybrid", rerank=True)

    assert with_rerank["hits"]
    assert all(hit["rerank_score"] is not None for hit in with_rerank["hits"])
    rerank_scores = [hit["rerank_score"] for hit in with_rerank["hits"]]
    assert rerank_scores == sorted(rerank_scores, reverse=True)
    # The cross-encoder must still surface the document that actually answers.
    assert with_rerank["hits"][0]["filename"] == f"orbit-{corpus_document['marker']}.md"
    assert without["hits"][0]["rerank_score"] is None


def test_document_ids_filter_is_respected(client: TestClient, corpus_document: dict) -> None:
    body = search(
        client,
        "telemetry retention",
        document_ids=[corpus_document["id"]],
        top_k=10,
    )
    assert body["hits"]
    assert {hit["document_id"] for hit in body["hits"]} == {corpus_document["id"]}


def test_unknown_strategy_is_rejected(client: TestClient) -> None:
    response = client.post("/v1/search", json={"query": "anything", "strategy": "magic"})
    assert response.status_code == 422


@pytest.mark.parametrize("strategy", ["dense", "sparse", "hybrid"])
def test_every_strategy_is_served(client: TestClient, corpus_document: dict, strategy: str) -> None:
    body = search(client, "Orbit telemetry retention", strategy=strategy)
    assert body["hits"]
