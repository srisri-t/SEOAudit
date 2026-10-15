"""End-to-End User Workflow Validation for Universal SEO Automation Platform (M1-M5).

Validates the full primary user journey:
Start Application -> Dashboard -> Enter Website URL -> Run SEO Audit ->
Observe Progress -> Review SEO Findings -> Review History -> Export Reports.
"""

from __future__ import annotations

import asyncio
import csv
import io
import json
import socket
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from fastapi.testclient import TestClient

from app.api.batch import get_orchestrator, get_repository
from app.db.connection import get_db, init_db, reconcile_stale_runs
from app.db.repository import BatchAuditRepository
from app.engine.batch.analyzer import calculate_aggregate_summary
from app.engine.batch.exporter import (
    export_batch_csv,
    export_batch_json,
    export_batch_markdown,
)
from app.engine.batch.orchestrator import BatchOrchestrator
from app.engine.fetcher import FetchResult
from app.main import app
from app.models.audit import AuditResponse, AuditSummary, Finding
from app.models.batch import (
    BatchAuditConfig,
    BatchAuditCreateRequest,
    PageAuditResult,
)


def mock_public_dns(*args, **kwargs):
    """Mock DNS resolution to return a safe public IP (example.com)."""
    return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 80))]


@pytest.fixture
def workflow_client(monkeypatch):
    """Provides a TestClient connected to an isolated test SQLite database."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "workflow_test.db"
        init_db(db_path)
        repo = BatchAuditRepository(db_path)
        orch = BatchOrchestrator(repo)

        monkeypatch.setattr("app.api.batch._repository", repo)
        monkeypatch.setattr("app.api.batch._orchestrator", orch)

        with TestClient(app) as client:
            yield client, repo, orch, db_path


# ==============================================================================
# PHASE 2: Application Startup & Health Endpoint
# ==============================================================================

def test_phase2_startup_and_health(workflow_client):
    """Verify application starts and responds to root and health check endpoints."""
    client, _, _, _ = workflow_client

    # 1. Root service info
    root_res = client.get("/")
    assert root_res.status_code == 200
    root_data = root_res.json()
    assert "Universal SEO Automation Platform API" in root_data["message"]
    assert root_data["health_url"] == "/api/health"

    # 2. Health check
    health_res = client.get("/api/health")
    assert health_res.status_code == 200
    health_data = health_res.json()
    assert health_data["status"] == "ok"
    assert health_data["app"] == "Universal SEO Platform"
    assert health_data["version"] == "0.1.0"
    assert "timestamp" in health_data


# ==============================================================================
# PHASE 3: Single-URL Audit Workflow
# ==============================================================================

def test_phase3_single_url_audit_workflow(workflow_client):
    """Verify the single-URL technical SEO audit execution and rule evaluations."""
    client, _, _, _ = workflow_client

    # 1. Validation: Empty URL rejected
    empty_res = client.post("/api/audits/url", json={"url": "   "})
    assert empty_res.status_code == 400
    assert "cannot be empty" in empty_res.json()["detail"]

    # 2. Validation: SSRF Loopback rejected
    loopback_res = client.post("/api/audits/url", json={"url": "http://127.0.0.1:8000/secret"})
    assert loopback_res.status_code == 400
    assert "Security check failed" in loopback_res.json()["detail"]

    # 3. Successful single-URL audit with mock responses
    mock_html = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <title>Holy Space - Christian Music Platform</title>
        <meta name="description" content="Stream over 3,000 uplifting Christian songs and hymns anytime, anywhere.">
        <link rel="canonical" href="https://www.holyspace.live/">
        <meta name="robots" content="index, follow">
    </head>
    <body>
        <h1>Welcome to Holy Space</h1>
        <a href="https://www.holyspace.live/about">About Us</a>
    </body>
    </html>
    """

    mock_fetch_result = FetchResult(
        initial_url="https://www.holyspace.live/",
        final_url="https://www.holyspace.live/",
        status_code=200,
        status_text="OK",
        headers={"content-type": "text/html; charset=utf-8"},
        body=mock_html,
        raw_bytes_count=len(mock_html.encode("utf-8")),
        content_type="text/html; charset=utf-8",
        fetch_duration_ms=80,
        redirect_count=0,
        is_html=True,
    )

    with patch("socket.getaddrinfo", side_effect=mock_public_dns):
        with patch("app.engine.runner.safe_fetch_url", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = mock_fetch_result

            res = client.post(
                "/api/audits/url",
                json={"url": "https://www.holyspace.live/", "include_browser": False},
            )
            assert res.status_code == 200
            data = res.json()
            assert data["url"] == "https://www.holyspace.live/"
            assert data["status_code"] == 200
            assert data["title"] == "Holy Space - Christian Music Platform"
            assert "Stream over 3,000" in data["meta_description"]
            assert data["summary"]["total_checks"] == 8
            assert data["summary"]["passed"] >= 6
            assert data["browser_audit"] is None  # Browser audit disabled by default
            assert len(data["outgoing_links"]) == 1
            assert data["outgoing_links"][0] == "https://www.holyspace.live/about"


# ==============================================================================
# PHASE 4: Sitemap Discovery Workflow
# ==============================================================================

def test_phase4_sitemap_discovery_workflow(workflow_client):
    """Verify sitemap discovery via robots.txt, standard fallbacks, and URL extraction."""
    client, _, _, _ = workflow_client

    robots_content = "User-agent: *\nAllow: /\nSitemap: https://example.com/sitemap.xml\n"
    sitemap_xml = """<?xml version="1.0" encoding="UTF-8"?>
    <urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
        <url><loc>https://example.com/</loc></url>
        <url><loc>https://example.com/about</loc></url>
        <url><loc>https://example.com/contact</loc></url>
    </urlset>
    """

    async def mock_fetch(target_url, **kwargs):
        if "robots.txt" in target_url:
            return FetchResult(
                initial_url=target_url,
                final_url=target_url,
                status_code=200,
                status_text="OK",
                headers={"content-type": "text/plain"},
                body=robots_content,
                raw_bytes_count=len(robots_content.encode("utf-8")),
                content_type="text/plain",
                fetch_duration_ms=20,
                redirect_count=0,
            )
        elif "sitemap.xml" in target_url:
            return FetchResult(
                initial_url=target_url,
                final_url=target_url,
                status_code=200,
                status_text="OK",
                headers={"content-type": "application/xml"},
                body=sitemap_xml,
                raw_bytes_count=len(sitemap_xml.encode("utf-8")),
                content_type="application/xml",
                fetch_duration_ms=45,
                redirect_count=0,
            )
        return FetchResult(
            initial_url=target_url,
            final_url=target_url,
            status_code=404,
            status_text="Not Found",
            headers={},
            body="",
            raw_bytes_count=0,
            content_type="text/plain",
            fetch_duration_ms=10,
            redirect_count=0,
        )

    with patch("socket.getaddrinfo", side_effect=mock_public_dns):
        with patch("app.engine.sitemap.discovery.safe_fetch_url", side_effect=mock_fetch):
            res = client.post(
                "/api/sitemaps/discover",
                json={"website_url": "https://example.com/", "max_urls": 100},
            )
            assert res.status_code == 200
            data = res.json()
            assert data["sitemap_status"] == "Sitemap found"
            assert data["discovered_url_count"] == 3
            assert "https://example.com/about" in data["urls"]


# ==============================================================================
# PHASE 5: Batch Auditing & Persistence
# ==============================================================================

def test_phase5_batch_auditing_and_persistence(workflow_client):
    """Verify batch audit lifecycle, bounded limits, page result queries, and cancellation."""
    client, repo, orch, db_path = workflow_client

    # 1. Create Batch Run
    res = client.post(
        "/api/batch-audits",
        json={
            "urls": [
                "https://example.com/p1",
                "https://example.com/p2",
                "https://example.com/p1",  # duplicate URL
                "https://example.com/p3",
            ],
            "config": {
                "max_pages": 10,
                "concurrency": 2,
                "include_browser": False,
            },
        },
    )
    assert res.status_code == 201
    run_data = res.json()
    run_id = run_data["id"]
    assert run_data["total_pages"] == 3  # deduplicated
    assert run_data["status"] in ("queued", "running", "completed")

    # 2. Populate realistic mock batch results
    repo.update_run_status(run_id=run_id, status="running", started_at="2026-10-14T20:00:00Z")

    repo.insert_page_result(
        PageAuditResult(
            run_id=run_id,
            url="https://example.com/p1",
            final_url="https://example.com/p1",
            status="success",
            status_code=200,
            title="Shared Company Title",
            meta_description="Shared description across pages",
            outgoing_links=["https://example.com/p2", "https://example.com/broken-target"],
        )
    )
    repo.insert_page_result(
        PageAuditResult(
            run_id=run_id,
            url="https://example.com/p2",
            final_url="https://example.com/p2",
            status="success",
            status_code=200,
            title="Shared Company Title",  # duplicate title
            meta_description="Shared description across pages",  # duplicate description
            outgoing_links=["https://example.com/p1"],
        )
    )
    repo.insert_page_result(
        PageAuditResult(
            run_id=run_id,
            url="https://example.com/p3",
            final_url="https://example.com/p3",
            status="failed",
            status_code=500,
            error_message="Server Fault 500",
            outgoing_links=[],
        )
    )

    # 3. Retrieve Page Results with Status Filter
    pages_all = client.get(f"/api/batch-audits/{run_id}/pages")
    assert pages_all.status_code == 200
    assert pages_all.json()["total"] == 3

    pages_failed = client.get(f"/api/batch-audits/{run_id}/pages?status=failed")
    assert pages_failed.status_code == 200
    assert pages_failed.json()["total"] == 1
    assert pages_failed.json()["pages"][0]["url"] == "https://example.com/p3"

    # 4. Retrieve Aggregate Summary (duplicate titles, status distribution, broken link check)
    summary_res = client.get(f"/api/batch-audits/{run_id}/summary")
    assert summary_res.status_code == 200
    summary_data = summary_res.json()

    assert summary_data["total_pages_audited"] == 3
    assert summary_data["successful_pages"] == 2
    assert summary_data["failed_pages"] == 1
    # Duplicate titles detected
    assert len(summary_data["duplicate_titles"]) == 1
    assert summary_data["duplicate_titles"][0]["title"] == "Shared Company Title"
    assert summary_data["duplicate_titles"][0]["count"] == 2

    # 5. Cancellation
    repo.create_run(
        run_id="run-to-be-cancelled",
        target_origin="https://example.com",
        status="running",
        mode="static",
        config=BatchAuditConfig(),
        total_pages=5,
    )
    cancel_res = client.post("/api/batch-audits/run-to-be-cancelled/cancel")
    assert cancel_res.status_code == 200
    assert cancel_res.json()["status"] == "cancelled"

    # 6. Server Restart / Stale Run Reconciliation
    repo.create_run(
        run_id="stale-orphaned-run",
        target_origin="https://example.com",
        status="running",
        mode="static",
        config=BatchAuditConfig(),
        total_pages=5,
    )
    repo.update_run_progress(run_id="stale-orphaned-run", completed_pages=1, failed_pages=0, skipped_pages=0)

    # Simulate restart reconciliation
    reconcile_stale_runs(db_path)
    reconciled = repo.get_run("stale-orphaned-run")
    assert reconciled.status == "partial"
    assert "Process terminated" in reconciled.error_message


# ==============================================================================
# PHASE 6: Report Exports (JSON, CSV with Formula Defense, Markdown)
# ==============================================================================

def test_phase6_report_exports(workflow_client):
    """Verify JSON, CSV, and Markdown exports, parsing content and checking formula defense."""
    client, repo, _, _ = workflow_client

    run_id = "run-export-verify"
    repo.create_run(
        run_id=run_id,
        target_origin="https://example.com",
        status="completed",
        mode="static",
        config=BatchAuditConfig(),
        total_pages=2,
    )
    repo.insert_page_result(
        PageAuditResult(
            run_id=run_id,
            url="https://example.com/safe",
            status="success",
            status_code=200,
            title="Safe Title",
            meta_description="Normal description",
        )
    )
    repo.insert_page_result(
        PageAuditResult(
            run_id=run_id,
            url="https://example.com/malicious",
            status="success",
            status_code=200,
            title="=SUM(A1:A10)",  # Formula injection
            meta_description="+12345",  # Formula injection
        )
    )

    # 1. JSON Export verification (parse and validate structure)
    json_res = client.get(f"/api/batch-audits/{run_id}/export?format=json")
    assert json_res.status_code == 200
    assert "application/json" in json_res.headers["content-type"]
    parsed_json = json.loads(json_res.text)
    assert parsed_json["run"]["id"] == run_id
    assert len(parsed_json["pages"]) == 2

    # 2. CSV Export verification (parse and check formula injection mitigation)
    csv_res = client.get(f"/api/batch-audits/{run_id}/export?format=csv")
    assert csv_res.status_code == 200
    assert "text/csv" in csv_res.headers["content-type"]
    reader = list(csv.reader(io.StringIO(csv_res.text)))
    assert reader[0][0] == "run_id"
    # Safe cell
    assert reader[1][7] == "Safe Title"
    # Malicious cells neutralized with leading single quote
    assert reader[2][7] == "'=SUM(A1:A10)"
    assert reader[2][8] == "'+12345"

    # 3. Markdown Export verification
    md_res = client.get(f"/api/batch-audits/{run_id}/export?format=markdown")
    assert md_res.status_code == 200
    assert "text/markdown" in md_res.headers["content-type"]
    assert "# Universal SEO Automation Platform" in md_res.text
    assert "## Executive Summary" in md_res.text
    assert "Safe Title" in md_res.text
