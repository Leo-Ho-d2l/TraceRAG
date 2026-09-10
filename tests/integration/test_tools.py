"""Tool execution contract: argument validation, error surfacing, evidence bookkeeping."""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.tools import AgentTools, TOOL_SCHEMAS


def test_tool_schemas_are_openai_function_schemas() -> None:
    assert len(TOOL_SCHEMAS) == 3
    names = set()
    for schema in TOOL_SCHEMAS:
        assert schema["type"] == "function"
        function = schema["function"]
        assert function["name"]
        assert function["description"]
        assert function["parameters"]["type"] == "object"
        names.add(function["name"])
    assert names == {"search_documents", "read_document_section", "get_document_metadata"}


async def test_invalid_arguments_are_reported_not_raised(session: AsyncSession) -> None:
    tools = AgentTools(session)
    result, evidence, trace = await tools.execute(
        "search_documents", {"query": "orbit", "top_k": 999}, []
    )
    assert trace["ok"] is False
    assert result["error"] == "invalid tool arguments"
    assert result["details"], "validation errors must be surfaced to the model"
    assert evidence == [], "a failed tool call must not add evidence"


async def test_malformed_uuid_is_rejected(session: AsyncSession) -> None:
    tools = AgentTools(session)
    result, _, trace = await tools.execute(
        "read_document_section", {"document_id": "not-a-uuid", "section_title": "x"}, []
    )
    assert trace["ok"] is False
    assert result["error"] == "invalid tool arguments"


async def test_unknown_tool_is_rejected(session: AsyncSession) -> None:
    tools = AgentTools(session)
    result, _, trace = await tools.execute("delete_everything", {}, [])
    assert trace["ok"] is False
    assert "unknown tool" in result["error"]


async def test_metadata_for_missing_document_reports_error(session: AsyncSession) -> None:
    tools = AgentTools(session)
    result, _, trace = await tools.execute(
        "get_document_metadata", {"document_id": str(uuid.uuid4())}, []
    )
    # A lookup miss is a valid tool result, not a crash.
    assert trace["ok"] is True
    assert result["error"] == "document not found"


async def test_evidence_labels_are_sequential_and_deduplicated(
    session: AsyncSession, ingested_document: dict
) -> None:
    tools = AgentTools(session)
    evidence: list[dict] = []
    query = f"{ingested_document['marker']} ledger reconciliation records"

    first, _, _ = await tools.execute("search_documents", {"query": query, "top_k": 5}, evidence)
    assert first["evidence"], "expected the fixture document to match"
    assert [item["label"] for item in evidence] == [f"S{i}" for i in range(1, len(evidence) + 1)]

    before = len(evidence)
    # Same query again: every chunk is already present, so nothing is added.
    second, _, _ = await tools.execute("search_documents", {"query": query, "top_k": 5}, evidence)
    assert second["evidence"] == []
    assert len(evidence) == before


async def test_evidence_for_model_hides_internal_ids(
    session: AsyncSession, ingested_document: dict
) -> None:
    tools = AgentTools(session)
    evidence: list[dict] = []
    result, _, _ = await tools.execute(
        "search_documents", {"query": f"{ingested_document['marker']} ledger retention", "top_k": 5}, evidence
    )
    assert result["evidence"]
    for item in result["evidence"]:
        assert set(item) == {"source", "filename", "section", "page", "content"}
        assert item["source"].startswith("[S")


async def test_read_document_section_returns_ordered_chunks(
    session: AsyncSession, ingested_document: dict
) -> None:
    tools = AgentTools(session)
    result, evidence, trace = await tools.execute(
        "read_document_section",
        {"document_id": ingested_document["id"], "section_title": "Ledger retention"},
        [],
    )
    assert trace["ok"] is True
    assert result["evidence"], "section lookup returned nothing"
    assert all(item["section"] == "Ledger retention" for item in result["evidence"])
    assert evidence


async def test_read_document_section_rejects_unknown_section(
    session: AsyncSession, ingested_document: dict
) -> None:
    tools = AgentTools(session)
    result, _, trace = await tools.execute(
        "read_document_section",
        {"document_id": ingested_document["id"], "section_title": "No such section"},
        [],
    )
    # A miss is a valid empty result, not an error.
    assert trace["ok"] is True
    assert result["evidence"] == []
