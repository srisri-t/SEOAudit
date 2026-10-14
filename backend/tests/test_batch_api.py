"""End-to-end API integration tests for batch auditing, export engine, and backward compatibility."""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.api.batch import get_orchestrator, get_repository
from app.db.connection import init_db
from app.db.repository import BatchAuditRepository
from app.engine.batch.orchestrator import BatchOrchestrator
from app.main import app
from app.models.audit import AuditResponse, AuditSummary
from app.models.batch import BatchAuditConfig, PageAuditResult


@pytest.fixture
def client_with_test_db(monkeypatch):
    """Provides a TestClient wired to an isolated temporary SQLite database."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_api.db"
        init_db(db_path)
        test_repo = BatchAuditRepository(db_path)
        test_orch = BatchOrchestrator(test_repo)

        monkeypatch.setattr("app.api.batch._repository", test_repo)
        monkeypatch.setattr("app.api.batch._orchestrator", test_orch)

        with TestClient(app) as test_client:
            yield test_client, test_repo


def test_create_batch_audit_validation_error(client_with_test_db):
    """Verify 400 Bad Request if no URLs or website are provided."""
    client, _ = client_with_test_db
    res = client.post("/api/batch-audits", json={"urls": []})
    assert res.status_code == 422 or res.status_code == 400


def test_create_batch_audit_and_retrieve(client_with_test_db):
    """Verify creating a batch audit triggers run and creates DB record."""
    client, repo = client_with_test_db

    with patch("app.engine.batch.orchestrator.validate_and_normalize_url", return_value=""):
        res = client.post(
            "/api/batch-audits",
            json={
                "urls": ["https://example.com/p1", "https://example.com/p2"],
                "config": {"max_pages": 10, "concurrency": 2},
            },
        )

    assert res.status_code == 201
    data = res.json()
    run_id = data["id"]
    assert data["status"] in ("queued", "running", "completed")
    assert data["total_pages"] == 2

    # Get by ID
    get_res = client.get(f"/api/batch-audits/{run_id}")
    assert get_res.status_code == 200
    assert get_res.json()["id"] == run_id

    # List runs
    list_res = client.get("/api/batch-audits")
    assert list_res.status_code == 200
    list_data = list_res.json()
    assert list_data["total"] >= 1
    assert any(r["id"] == run_id for r in list_data["runs"])


def test_get_pages_and_summary_endpoints(client_with_test_db):
    """Verify retrieving pages and aggregate summary for a completed run."""
    client, repo = client_with_test_db

    repo.create_run(
        run_id="test-run-api-pages",
        target_origin="https://example.com",
        status="completed",
        mode="static",
        config=BatchAuditConfig(),
        total_pages=2,
    )
    repo.insert_page_result(
        PageAuditResult(
            run_id="test-run-api-pages",
            url="https://example.com/page-1",
            status="success",
            status_code=200,
            title="Page 1",
            outgoing_links=["https://example.com/page-2"],
        )
    )
    repo.insert_page_result(
        PageAuditResult(
            run_id="test-run-api-pages",
            url="https://example.com/page-2",
            status="failed",
            status_code=500,
            error_message="Internal Server Error",
        )
    )

    # Get pages
    pages_res = client.get("/api/batch-audits/test-run-api-pages/pages")
    assert pages_res.status_code == 200
    pages_data = pages_res.json()
    assert pages_data["total"] == 2
    assert len(pages_data["pages"]) == 2

    # Filter pages by status
    success_res = client.get("/api/batch-audits/test-run-api-pages/pages?status=success")
    assert success_res.status_code == 200
    assert success_res.json()["total"] == 1
    assert success_res.json()["pages"][0]["status"] == "success"

    # Get summary
    sum_res = client.get("/api/batch-audits/test-run-api-pages/summary")
    assert sum_res.status_code == 200
    sum_data = sum_res.json()
    assert sum_data["total_pages_audited"] == 2
    assert sum_data["successful_pages"] == 1
    assert sum_data["failed_pages"] == 1


def test_cancel_endpoint(client_with_test_db):
    """Verify POST /api/batch-audits/{run_id}/cancel updates run status."""
    client, repo = client_with_test_db

    repo.create_run(
        run_id="run-to-cancel",
        target_origin="https://example.com",
        status="running",
        mode="static",
        config=BatchAuditConfig(),
        total_pages=5,
    )

    cancel_res = client.post("/api/batch-audits/run-to-cancel/cancel")
    assert cancel_res.status_code == 200
    assert cancel_res.json()["status"] == "cancelled"


def test_export_endpoints(client_with_test_db):
    """Verify exporting report as JSON, CSV, and Markdown."""
    client, repo = client_with_test_db

    repo.create_run(
        run_id="export-run-test",
        target_origin="https://example.com",
        status="completed",
        mode="static",
        config=BatchAuditConfig(),
        total_pages=1,
    )
    repo.insert_page_result(
        PageAuditResult(
            run_id="export-run-test",
            url="https://example.com/home",
            status="success",
            status_code=200,
            title="=SUM(A1:A5)",  # Potential formula injection
        )
    )

    # JSON export
    json_res = client.get("/api/batch-audits/export-run-test/export?format=json")
    assert json_res.status_code == 200
    assert "application/json" in json_res.headers["content-type"]
    assert "seo_audit_export-run-test.json" in json_res.headers["content-disposition"]
    assert "export-run-test" in json_res.text

    # CSV export
    csv_res = client.get("/api/batch-audits/export-run-test/export?format=csv")
    assert csv_res.status_code == 200
    assert "text/csv" in csv_res.headers["content-type"]
    assert "seo_audit_export-run-test.csv" in csv_res.headers["content-disposition"]
    # Formula should be sanitized
    assert "'=SUM(A1:A5)" in csv_res.text

    # Markdown export
    md_res = client.get("/api/batch-audits/export-run-test/export?format=markdown")
    assert md_res.status_code == 200
    assert "text/markdown" in md_res.headers["content-type"]
    assert "seo_audit_export-run-test.md" in md_res.headers["content-disposition"]
    assert "# Universal SEO Automation Platform" in md_res.text


def test_backward_compatibility_single_audit_and_sitemap(client_with_test_db):
    """Verify Milestone 1-4 existing API endpoints remain 100% functional and compatible."""
    client, _ = client_with_test_db

    # 1. Health endpoint (M1)
    health_res = client.get("/api/health")
    assert health_res.status_code == 200
    assert health_res.json()["status"] == "ok"

    # 2. Single URL Audit endpoint (M2-M4)
    with patch("app.api.audit.run_single_url_audit") as mock_audit:
        mock_audit.return_value = AuditResponse(
            url="https://example.com",
            final_url="https://example.com",
            status_code=200,
            status_text="OK",
            content_type="text/html",
            fetch_duration_ms=65,
            redirect_count=0,
            title="Single Audit Page",
            summary=AuditSummary(
                total_checks=8, passed=8, warnings=0, issues=0, errors=0
            ),
            findings=[],
        )
        audit_res = client.post("/api/audits/url", json={"url": "https://example.com"})
        assert audit_res.status_code == 200
        assert audit_res.json()["title"] == "Single Audit Page"
        assert audit_res.json()["summary"]["total_checks"] == 8

    # 3. Sitemaps discovery endpoint (M3)
    with patch("app.api.sitemaps.discover_sitemaps") as mock_disc:
        from app.models.sitemap import SitemapDiscoverResponse

        mock_disc.return_value = SitemapDiscoverResponse(
            website_url="https://example.com",
            sitemap_status="Sitemap found",
            discovered_sitemaps=["https://example.com/sitemap.xml"],
            discovered_url_count=2,
            urls=["https://example.com/1", "https://example.com/2"],
        )
        with patch("app.api.sitemaps.validate_and_normalize_url", return_value=""):
            sitemap_res = client.post(
                "/api/sitemaps/discover",
                json={"website_url": "https://example.com"},
            )
            assert sitemap_res.status_code == 200
            assert sitemap_res.json()["discovered_url_count"] == 2
