from fastapi.testclient import TestClient

from app.main import app


def test_upload_search_and_grounded_chat():
    client = TestClient(app)
    body = b"# Retention Policy\n\nProject Atlas retains diagnostic snapshots for exactly 777 days."
    upload = client.post(
        "/v1/documents",
        files={"file": ("atlas-policy.md", body, "text/markdown")},
    )
    assert upload.status_code == 202, upload.text
    document = upload.json()

    status = client.get(f"/v1/documents/{document['id']}")
    assert status.status_code == 200
    assert status.json()["status"] == "ready"

    search = client.post(
        "/v1/search",
        json={
            "query": "How many days are Atlas diagnostic snapshots retained?",
            "top_k": 5,
            "strategy": "hybrid",
            "rerank": False,
        },
    )
    assert search.status_code == 200, search.text
    hits = search.json()["hits"]
    assert hits
    assert hits[0]["filename"] == "atlas-policy.md"
    assert "777 days" in hits[0]["content"]

    chat = client.post(
        "/v1/chat",
        json={
            "question": "How many days are Atlas diagnostic snapshots retained?",
            "mode": "retrieve",
            "top_k": 5,
        },
    )
    assert chat.status_code == 200, chat.text
    response = chat.json()
    assert response["route"] == "retrieve"
    assert response["citations"]
    assert response["citations"][0]["filename"] == "atlas-policy.md"
