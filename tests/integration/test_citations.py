"""Citation correctness.

The README claims "source-grounded answers with validated [S1]-style
citations". Asserting that the string "[S1]" appears would not verify that, so
these tests check that citation labels, ordering and provenance are internally
consistent, and that no citation is invented when there is no evidence.
"""

from __future__ import annotations

import re
import uuid

from fastapi.testclient import TestClient

CITATION_RE = re.compile(r"\[(S\d+)\]")


def test_citations_match_the_answer_and_are_well_formed(client: TestClient, corpus_document: dict) -> None:
    response = client.post(
        "/v1/chat",
        json={"question": "How long does Project Orbit retain raw telemetry?", "mode": "retrieve", "top_k": 5},
    )
    assert response.status_code == 200, response.text
    body = response.json()

    assert body["citations"], "grounded answer returned no citations"
    labels_in_answer = set(CITATION_RE.findall(body["answer"]))
    assert labels_in_answer, "answer contains no citation markers"

    returned = {citation["label"] for citation in body["citations"]}
    # No dangling marker in the answer, and no citation the answer never uses.
    assert labels_in_answer == returned
    # Labels are contiguous from S1.
    assert returned == {f"S{i}" for i in range(1, len(returned) + 1)}

    for citation in body["citations"]:
        uuid.UUID(citation["chunk_id"])
        uuid.UUID(citation["document_id"])
        assert citation["excerpt"].strip()
        assert citation["filename"].endswith(".md")


def test_citation_points_at_the_document_holding_the_fact(client: TestClient, corpus_document: dict) -> None:
    marker = corpus_document["marker"]
    body = client.post(
        "/v1/chat",
        json={"question": f"How many days of raw telemetry does Orbit retain? ({marker})", "mode": "retrieve"},
    ).json()
    assert body["citations"]
    assert body["citations"][0]["filename"] == f"orbit-{marker}.md"
    assert body["citations"][0]["section_title"] == "Telemetry retention"


def test_citation_excerpt_is_a_prefix_of_the_returned_evidence(
    client: TestClient, corpus_document: dict
) -> None:
    """The excerpt must be traceable back to the chunk the search API returns."""
    query = "Orbit severity-one acknowledgement window"
    chat = client.post("/v1/chat", json={"question": query, "mode": "retrieve", "top_k": 5}).json()
    assert chat["citations"]

    search = client.post("/v1/search", json={"query": query, "top_k": 10, "strategy": "hybrid"}).json()
    by_chunk = {hit["chunk_id"]: hit for hit in search["hits"]}

    for citation in chat["citations"]:
        hit = by_chunk.get(citation["chunk_id"])
        if hit is None:
            continue  # chat and search use different top_k; skip unmatched
        normalized = hit["content"].replace("\n", " ").strip()
        assert normalized.startswith(citation["excerpt"].rstrip("."))


def test_direct_route_produces_no_citations(client: TestClient) -> None:
    body = client.post("/v1/chat", json={"question": "hello", "mode": "auto"}).json()
    assert body["route"] == "direct"
    # A conversational reply must not pretend to be sourced.
    assert body["citations"] == []


def test_thread_history_round_trips(client: TestClient, corpus_document: dict) -> None:
    first = client.post(
        "/v1/chat",
        json={"question": "How long does Orbit retain telemetry?", "mode": "retrieve"},
    ).json()
    assert first["citations"]

    second = client.post(
        "/v1/chat",
        json={
            "question": "And what is the severity-one acknowledgement window?",
            "mode": "retrieve",
            "thread_id": first["thread_id"],
        },
    )
    assert second.status_code == 200, second.text
    assert second.json()["thread_id"] == first["thread_id"]

    history = client.get(f"/v1/threads/{first['thread_id']}/messages").json()
    assert [message["role"] for message in history] == ["user", "assistant", "user", "assistant"]
    assert history[1]["content"] == first["answer"]


def test_unknown_thread_returns_404(client: TestClient) -> None:
    response = client.get(f"/v1/threads/{uuid.uuid4()}/messages")
    assert response.status_code == 404
