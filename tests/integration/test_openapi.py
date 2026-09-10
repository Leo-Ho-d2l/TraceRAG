from fastapi.testclient import TestClient

from app.main import app


def test_openapi_exposes_core_routes():
    client = TestClient(app)
    response = client.get("/openapi.json")
    assert response.status_code == 200
    paths = response.json()["paths"]
    assert "/v1/documents" in paths
    assert "/v1/search" in paths
    assert "/v1/chat" in paths
