from fastapi.testclient import TestClient

from o2c_agent_service.main import app


def test_health_reports_up() -> None:
    response = TestClient(app).get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "UP"
