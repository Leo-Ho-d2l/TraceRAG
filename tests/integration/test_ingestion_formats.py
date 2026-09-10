"""Ingestion across the supported input formats.

sample_data/ ships Markdown only, so the PDF, HTML and plain-text branches of the
parser are covered here with generated fixtures: upload -> ingest -> retrievable
-> citable, plus cleanup.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator

import pymupdf
import pytest
from fastapi.testclient import TestClient


def _wait_ready(client: TestClient, document_id: str) -> dict:
    detail = client.get(f"/v1/documents/{document_id}")
    assert detail.status_code == 200
    body = detail.json()
    assert body["status"] in {"ready", "failed"}, body
    return body


def _upload(client: TestClient, filename: str, payload: bytes, content_type: str) -> dict:
    response = client.post("/v1/documents", files={"file": (filename, payload, content_type)})
    assert response.status_code == 202, response.text
    return response.json()


def _build_pdf(marker: str) -> bytes:
    document = pymupdf.open()
    page = document.new_page()
    page.insert_text((72, 96), "Nimbus Platform Operations Manual", fontsize=16)
    page.insert_text((72, 140), "Section: Snapshot retention", fontsize=12)
    page.insert_text(
        (72, 170), f"Project Nimbus keeps nightly snapshots for exactly {marker} days.", fontsize=11
    )
    data = document.tobytes()
    document.close()
    return data


@pytest.fixture
def uploaded(client: TestClient) -> Iterator[dict]:
    created: list[str] = []

    def _create(filename: str, payload: bytes, content_type: str) -> dict:
        document = _upload(client, filename, payload, content_type)
        created.append(document["id"])
        return document

    yield _create

    for document_id in created:
        client.delete(f"/v1/documents/{document_id}")


def test_pdf_ingestion_preserves_pages_and_is_citable(client: TestClient, uploaded) -> None:
    marker = uuid.uuid4().hex[:10]
    document = uploaded(f"nimbus-{marker}.pdf", _build_pdf(marker), "application/pdf")

    detail = _wait_ready(client, document["id"])
    assert detail["status"] == "ready", detail
    assert detail["mime_type"] == "application/pdf"

    search = client.post(
        "/v1/search",
        json={"query": f"Nimbus snapshot retention {marker} days", "top_k": 5, "rerank": False},
    ).json()
    top = search["hits"][0]
    assert top["filename"] == f"nimbus-{marker}.pdf"
    assert top["page_number"] == 1, "PDF page numbers must survive chunking"
    assert marker in top["content"]

    chat = client.post(
        "/v1/chat",
        json={"question": f"How long does Project Nimbus keep nightly snapshots? ({marker})", "mode": "retrieve"},
    ).json()
    assert chat["citations"]
    assert chat["citations"][0]["filename"] == f"nimbus-{marker}.pdf"
    assert chat["citations"][0]["page_number"] == 1


def test_plain_text_ingestion(client: TestClient, uploaded) -> None:
    marker = uuid.uuid4().hex[:10]
    body = f"Harbor runbook {marker}\n\nRetention for harbor audit records is {marker} days.\n".encode()
    document = uploaded(f"harbor-{marker}.txt", body, "text/plain")

    assert _wait_ready(client, document["id"])["status"] == "ready"
    search = client.post("/v1/search", json={"query": f"harbor audit records {marker}", "top_k": 5}).json()
    assert any(hit["filename"] == f"harbor-{marker}.txt" for hit in search["hits"])


def test_html_ingestion_splits_on_headings(client: TestClient, uploaded) -> None:
    marker = uuid.uuid4().hex[:10]
    body = (
        f"<html><body><h1>Beacon {marker}</h1>"
        f"<p>Beacon telemetry is retained for {marker} days.</p>"
        f"<h2>Escalation</h2><p>Beacon escalation target is {marker} minutes.</p>"
        f"<script>var ignored = '{marker}';</script>"
        f"</body></html>"
    ).encode()
    document = uploaded(f"beacon-{marker}.html", body, "text/html")

    assert _wait_ready(client, document["id"])["status"] == "ready"
    search = client.post("/v1/search", json={"query": f"Beacon telemetry retention {marker}", "top_k": 5}).json()
    hits = [hit for hit in search["hits"] if hit["filename"] == f"beacon-{marker}.html"]
    assert hits, "HTML document was not indexed"
    assert any(hit["section_title"] == f"Beacon {marker}" for hit in hits)
    assert all("var ignored" not in hit["content"] for hit in hits), "script contents must not be indexed"


def test_empty_document_is_marked_failed(client: TestClient, uploaded) -> None:
    """A file that produces no chunks must fail loudly, not silently succeed."""
    document = uploaded("empty.md", b"", "text/markdown")
    detail = _wait_ready(client, document["id"])
    assert detail["status"] == "failed"
    assert detail["error_message"], "a failed ingestion must preserve its reason"
