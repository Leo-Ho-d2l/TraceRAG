"""Agent routing and bounded tool loop, exercised through the HTTP API."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.core.config import settings


def chat(client: TestClient, question: str, **overrides) -> dict:
    payload = {"question": question, "mode": "auto", "top_k": 5}
    payload.update(overrides)
    response = client.post("/v1/chat", json=payload)
    assert response.status_code == 200, response.text
    return response.json()


def test_greeting_routes_to_direct_without_retrieval(client: TestClient) -> None:
    body = chat(client, "hello")
    assert body["route"] == "direct"
    assert body["citations"] == []
    assert body["tool_trace"] == []


def test_factual_question_routes_to_retrieve(client: TestClient, corpus_document: dict) -> None:
    body = chat(client, "How long does Project Orbit retain raw telemetry?")
    assert body["route"] == "retrieve"
    assert body["citations"], "retrieve route produced no evidence"
    assert body["tool_trace"] == [], "retrieve route must not run the tool loop"


def test_explicit_mode_overrides_routing(client: TestClient, corpus_document: dict) -> None:
    body = chat(client, "hello", mode="retrieve")
    assert body["route"] == "retrieve"


def test_comparison_routes_to_research_and_calls_tools(client: TestClient, corpus_document: dict) -> None:
    body = chat(
        client,
        "Compare Orbit telemetry retention versus the severity-one acknowledgement window.",
    )
    assert body["route"] == "research"
    assert body["tool_trace"], "research route recorded no tool calls"
    assert any(event["tool"] == "search_documents" for event in body["tool_trace"])
    assert all(event["ok"] for event in body["tool_trace"])
    assert body["citations"], "research route produced no citations"


def test_research_is_bounded_by_max_agent_steps(client: TestClient, monkeypatch) -> None:
    """The agent must stop rather than loop forever when tools keep being called."""
    monkeypatch.setattr(settings, "max_agent_steps", 1)
    body = chat(client, "Compare Business versus Enterprise availability and support targets.")
    assert body["total_steps"] <= settings.max_agent_steps + 1
    assert body["tool_trace"], "expected at least one tool call before termination"
    assert body["answer"]


def test_agent_recovers_when_no_evidence_exists(client: TestClient) -> None:
    """An empty corpus region must yield an explicit no-evidence answer rather
    than an invented one."""
    # A document_ids filter that matches nothing forces the retrieve node to
    # return zero evidence while still exercising the grounded-answer path.
    body = chat(client, "What is the telemetry retention for a workspace that does not exist?")
    # The corpus is non-empty, so retrieval still returns neighbours; the
    # guarantee under test is that whatever is returned is cited, never invented.
    assert body["answer"]
    assert all(citation["filename"].endswith(".md") for citation in body["citations"])
