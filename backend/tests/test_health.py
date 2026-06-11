from fastapi.testclient import TestClient

from app.main import app


def test_health_endpoint_reports_service_is_ready():
    response = TestClient(app).get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "sightline-backend",
    }
