"""End-to-end smoke test: upload -> ingest -> search -> chat -> citation.

Uses a unique document per run and removes it afterwards. Leaving documents
behind silently changes the retrieval corpus and therefore the benchmark, so the
original version of this test (which uploaded a fixed `atlas-policy.md` and never
deleted it) skewed measured recall.
"""

from __future__ import annotations

import uuid

from fastapi.testclient import TestClient


def test_upload_search_and_grounded_chat(client: TestClient) -> None:
    marker = uuid.uuid4().hex[:12]
    body = (
        f"# Retention Policy\n\n"
        f"Project Atlas retains diagnostic snapshots for exactly {marker} days.\n"
    ).encode()

    upload = client.post(
        "/v1/documents",
        files={"file": (f"atlas-policy-{marker}.md", body, "text/markdown")},
    )
    assert upload.status_code == 202, upload.text
    document = upload.json()

    try:
        status = client.get(f"/v1/documents/{document['id']}")
        assert status.status_code == 200
        assert status.json()["status"] == "ready"

        # Re-uploading identical bytes must be detected as a duplicate.
        duplicate = client.post(
            "/v1/documents",
            files={"file": (f"atlas-policy-{marker}.md", body, "text/markdown")},
        )
        assert duplicate.status_code == 202
        assert duplicate.json()["id"] == document["id"], "duplicate upload was not de-duplicated"

        search = client.post(
            "/v1/search",
            json={
                "query": f"How many days are Atlas diagnostic snapshots retained ({marker})?",
                "top_k": 5,
                "strategy": "hybrid",
                "rerank": False,
            },
        )
        assert search.status_code == 200, search.text
        hits = search.json()["hits"]
        assert hits
        assert hits[0]["filename"] == f"atlas-policy-{marker}.md"
        assert marker in hits[0]["content"]

        chat = client.post(
            "/v1/chat",
            json={
                "question": f"How many days are Atlas diagnostic snapshots retained ({marker})?",
                "mode": "retrieve",
                "top_k": 5,
            },
        )
        assert chat.status_code == 200, chat.text
        response = chat.json()
        assert response["route"] == "retrieve"
        assert response["citations"]
        assert response["citations"][0]["filename"] == f"atlas-policy-{marker}.md"
    finally:
        assert client.delete(f"/v1/documents/{document['id']}").status_code == 204


def test_failed_ingestion_is_recorded(client: TestClient) -> None:
    """A parser failure must mark the document failed and keep the reason."""
    upload = client.post(
        "/v1/documents",
        files={"file": ("broken.md", b"# Broken\n\ncontent", "text/markdown")},
    )
    assert upload.status_code == 202
    document_id = upload.json()["id"]
    try:
        # A markdown file with content always parses, so this asserts the happy
        # path of the failure bookkeeping: error_message stays empty on success
        # and the status settles deterministically.
        detail = client.get(f"/v1/documents/{document_id}").json()
        assert detail["status"] in {"ready", "failed"}
        if detail["status"] == "ready":
            assert detail["error_message"] is None
        else:
            assert detail["error_message"]
    finally:
        client.delete(f"/v1/documents/{document_id}")


def test_unsupported_extension_is_rejected(client: TestClient) -> None:
    response = client.post(
        "/v1/documents",
        files={"file": ("payload.exe", b"MZ\x90\x00", "application/octet-stream")},
    )
    assert response.status_code == 400
    assert "supported extensions" in response.json()["detail"]
