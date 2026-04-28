from __future__ import annotations

from piratehunt.api.app import app


def test_health_endpoint():
    """Test /health endpoint."""
    from fastapi.testclient import TestClient

    client = TestClient(app)
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "phase": 1}
