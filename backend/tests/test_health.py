from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_endpoint_returns_200():
    """Verify GET /api/health responds with HTTP 200."""
    response = client.get("/api/health")
    assert response.status_code == 200


def test_health_endpoint_returns_valid_json_structure():
    """Verify GET /api/health response contains valid JSON with required fields."""
    response = client.get("/api/health")
    assert response.status_code == 200

    data = response.json()
    assert isinstance(data, dict)
    assert "status" in data
    assert "app" in data
    assert "version" in data
    assert "timestamp" in data


def test_health_endpoint_status_is_ok():
    """Verify GET /api/health reports 'ok' status and correct application name."""
    response = client.get("/api/health")
    assert response.status_code == 200

    data = response.json()
    assert data["status"] == "ok"
    assert data["app"] == "Universal SEO Platform"
    assert data["version"] == "0.1.0"


def test_root_endpoint_returns_200():
    """Verify root / endpoint is accessible and points to health/docs."""
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert "docs_url" in data
    assert "health_url" in data
