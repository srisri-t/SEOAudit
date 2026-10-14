from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.engine.extractor import (
    CanonicalData,
    DescriptionData,
    ExtractedMetadata,
    RobotsDirectiveData,
    TitleData,
)
from app.engine.fetcher import FetchResult
from app.main import app

client = TestClient(app)


def mock_successful_fetch(target_url: str, **kwargs):
    return FetchResult(
        initial_url=target_url,
        final_url=target_url,
        status_code=200,
        status_text="OK",
        headers={"content-type": "text/html; charset=utf-8"},
        body="<html><head><title>Holy Space</title><meta name='description' content='Christian music streaming platform with over 3,000 song tracks.'></head><body></body></html>",
        raw_bytes_count=200,
        content_type="text/html; charset=utf-8",
        fetch_duration_ms=120,
        redirect_count=0,
        is_html=True,
    )


def test_audit_url_success_mocked():
    """Verify POST /api/audits/url returns 200 with structured audit findings."""
    with patch("app.engine.runner.safe_fetch_url", new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = mock_successful_fetch("https://www.holyspace.live")

        response = client.post("/api/audits/url", json={"url": "https://www.holyspace.live"})
        assert response.status_code == 200

        data = response.json()
        assert data["url"] == "https://www.holyspace.live"
        assert data["final_url"] == "https://www.holyspace.live"
        assert data["status_code"] == 200
        assert data["title"] == "Holy Space"
        assert "Christian music streaming" in data["meta_description"]
        assert data["summary"]["total_checks"] == 8
        assert len(data["findings"]) == 8

        # Check that individual findings have expected schema fields
        for f in data["findings"]:
            assert "rule_id" in f
            assert "title" in f
            assert "status" in f
            assert f["status"] in ("pass", "warning", "issue", "error")
            assert "explanation" in f


def test_audit_url_prohibited_loopback_rejected():
    """Verify loopback IP 127.0.0.1 is rejected with HTTP 400 Bad Request."""
    response = client.post("/api/audits/url", json={"url": "http://127.0.0.1:8000/secret"})
    assert response.status_code == 400
    assert "Security check failed" in response.json()["detail"]


def test_audit_url_prohibited_localhost_rejected():
    """Verify localhost hostname is rejected with HTTP 400."""
    response = client.post("/api/audits/url", json={"url": "http://localhost/admin"})
    assert response.status_code == 400
    assert "Security check failed" in response.json()["detail"]


def test_audit_url_prohibited_metadata_ip_rejected():
    """Verify cloud metadata IP 169.254.169.254 is rejected with HTTP 400."""
    response = client.post("/api/audits/url", json={"url": "http://169.254.169.254/latest/meta-data/"})
    assert response.status_code == 400
    assert "Security check failed" in response.json()["detail"]


def test_audit_url_unsupported_scheme_rejected():
    """Verify non-HTTP schemes are rejected with HTTP 400."""
    response = client.post("/api/audits/url", json={"url": "ftp://files.example.com/data.csv"})
    assert response.status_code == 400
    assert "Unsupported URL scheme" in response.json()["detail"]


def test_audit_url_embedded_credentials_rejected():
    """Verify URLs with embedded credentials are rejected with HTTP 400."""
    response = client.post("/api/audits/url", json={"url": "https://admin:pass123@example.com"})
    assert response.status_code == 400
    assert "embedded credentials" in response.json()["detail"]


def test_audit_url_empty_payload_rejected():
    """Verify empty URL yields 400 Bad Request."""
    response = client.post("/api/audits/url", json={"url": ""})
    assert response.status_code == 400


def test_health_endpoint_regression():
    """Verify existing health endpoint continues to return 200 OK."""
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["app"] == "Universal SEO Platform"
