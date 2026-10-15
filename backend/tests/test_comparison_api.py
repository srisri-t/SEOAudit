"""API endpoint integration tests for M6.1 Audit Run Comparison."""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.api.batch import get_orchestrator, get_repository
from app.db.connection import get_db, init_db
from app.db.repository import BatchAuditRepository
from app.engine.batch.orchestrator import BatchOrchestrator
from app.main import app
from app.models.audit import Finding
from app.models.batch import BatchAuditConfig, PageAuditResult


@pytest.fixture
def api_client(monkeypatch):
    """Provides a TestClient connected to an isolated test SQLite database."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "comparison_api_test.db"
        init_db(db_path)
        repo = BatchAuditRepository(db_path)
        orch = BatchOrchestrator(repo)

        monkeypatch.setattr("app.api.batch._repository", repo)
        monkeypatch.setattr("app.api.batch._orchestrator", orch)

        with TestClient(app) as client:
            yield client, repo, db_path


def seed_run(
    repo: BatchAuditRepository,
    run_id: str,
    target_origin: str = "https://example.com",
    status: str = "completed",
    pages: list[PageAuditResult] | None = None,
):
    """Helper to seed runs and page results into the repository."""
    repo.create_run(
        run_id=run_id,
        target_origin=target_origin,
        status=status,
        mode="static",
        config=BatchAuditConfig(),
        total_pages=len(pages or []),
    )
    if pages:
        for p in pages:
            repo.insert_page_result(p)


# ==============================================================================
# API Comparison Tests
# ==============================================================================

def test_api_compare_success(api_client):
    """POST /api/batch-audits/compare returns HTTP 200 with structured comparison."""
    client, repo, _ = api_client

    run_1_pages = [
        PageAuditResult(
            run_id="run-1",
            url="https://example.com/p1",
            final_url="https://example.com/p1",
            status="success",
            status_code=200,
            title="Old Title",
            findings=[
                Finding(
                    rule_id="page-title",
                    title="Page Title",
                    status="issue",
                    explanation="Too short.",
                )
            ],
        )
    ]
    run_2_pages = [
        PageAuditResult(
            run_id="run-2",
            url="https://example.com/p1",
            final_url="https://example.com/p1",
            status="success",
            status_code=200,
            title="Brand New Title That Is Long Enough",
            findings=[
                Finding(
                    rule_id="page-title",
                    title="Page Title",
                    status="pass",
                    explanation="Good length.",
                )
            ],
        )
    ]

    seed_run(repo, "run-1", pages=run_1_pages)
    seed_run(repo, "run-2", pages=run_2_pages)

    res = client.post(
        "/api/batch-audits/compare",
        json={"baseline_run_id": "run-1", "comparison_run_id": "run-2"},
    )
    assert res.status_code == 200
    data = res.json()

    assert data["summary"]["baseline_run_id"] == "run-1"
    assert data["summary"]["comparison_run_id"] == "run-2"
    assert data["summary"]["resolved_issues_count"] == 1
    assert data["summary"]["new_issues_count"] == 0
    assert data["assessment"]["verdict"] == "improved"
    assert len(data["metadata_changes"]) == 1
    assert data["metadata_changes"][0]["field_name"] == "title"


def test_api_compare_unknown_baseline_returns_404(api_client):
    """Unknown baseline run ID returns HTTP 404."""
    client, repo, _ = api_client
    seed_run(repo, "run-exists")

    res = client.post(
        "/api/batch-audits/compare",
        json={"baseline_run_id": "nonexistent-run", "comparison_run_id": "run-exists"},
    )
    assert res.status_code == 404
    assert "Baseline audit run 'nonexistent-run' not found" in res.json()["detail"]


def test_api_compare_unknown_comparison_returns_404(api_client):
    """Unknown comparison run ID returns HTTP 404."""
    client, repo, _ = api_client
    seed_run(repo, "run-exists")

    res = client.post(
        "/api/batch-audits/compare",
        json={"baseline_run_id": "run-exists", "comparison_run_id": "nonexistent-run"},
    )
    assert res.status_code == 404
    assert "Comparison audit run 'nonexistent-run' not found" in res.json()["detail"]


def test_api_compare_identical_run_ids_returns_400(api_client):
    """Selecting the same run for both baseline and comparison returns HTTP 400."""
    client, repo, _ = api_client
    seed_run(repo, "run-same")

    res = client.post(
        "/api/batch-audits/compare",
        json={"baseline_run_id": "run-same", "comparison_run_id": "run-same"},
    )
    assert res.status_code == 400
    assert "must be distinct" in res.json()["detail"]


def test_api_compare_incompatible_website_scopes_returns_400(api_client):
    """Comparing runs targeting different domains returns HTTP 400."""
    client, repo, _ = api_client
    seed_run(repo, "run-a", target_origin="https://site-a.com")
    seed_run(repo, "run-b", target_origin="https://site-b.com")

    res = client.post(
        "/api/batch-audits/compare",
        json={"baseline_run_id": "run-a", "comparison_run_id": "run-b"},
    )
    assert res.status_code == 400
    assert "incompatible website scopes" in res.json()["detail"]


def test_api_compare_invalid_schema_returns_422(api_client):
    """Invalid payload schema returns HTTP 422."""
    client, _, _ = api_client
    res = client.post("/api/batch-audits/compare", json={"only_one_field": "123"})
    assert res.status_code == 422


def test_api_compare_is_strictly_read_only(api_client):
    """Comparison execution does not modify database records."""
    client, repo, db_path = api_client
    seed_run(repo, "run-ro-1", target_origin="https://example.com")
    seed_run(repo, "run-ro-2", target_origin="https://example.com")

    # Capture row counts and checksums
    with get_db(db_path) as conn:
        before_runs = conn.execute("SELECT * FROM audit_runs").fetchall()
        before_pages = conn.execute("SELECT * FROM audit_pages").fetchall()

    res = client.post(
        "/api/batch-audits/compare",
        json={"baseline_run_id": "run-ro-1", "comparison_run_id": "run-ro-2"},
    )
    assert res.status_code == 200

    with get_db(db_path) as conn:
        after_runs = conn.execute("SELECT * FROM audit_runs").fetchall()
        after_pages = conn.execute("SELECT * FROM audit_pages").fetchall()

    assert len(before_runs) == len(after_runs)
    assert len(before_pages) == len(after_pages)


def test_api_export_comparison_json_and_markdown(api_client):
    """GET /api/batch-audits/compare/export returns JSON and Markdown file downloads."""
    client, repo, _ = api_client
    seed_run(repo, "run-exp-1", target_origin="https://example.com")
    seed_run(repo, "run-exp-2", target_origin="https://example.com")

    # JSON export
    res_json = client.get(
        "/api/batch-audits/compare/export?baseline_run_id=run-exp-1&comparison_run_id=run-exp-2&format=json"
    )
    assert res_json.status_code == 200
    assert "application/json" in res_json.headers["content-type"]
    assert "comparison_run-exp-_run-exp-" in res_json.headers["content-disposition"]
    assert '"summary"' in res_json.text

    # Markdown export
    res_md = client.get(
        "/api/batch-audits/compare/export?baseline_run_id=run-exp-1&comparison_run_id=run-exp-2&format=markdown"
    )
    assert res_md.status_code == 200
    assert "text/markdown" in res_md.headers["content-type"]
    assert "# Universal SEO Automation Platform" in res_md.text

    # Unsupported format returns 422 Unprocessable Entity due to Literal validation
    res_bad = client.get(
        "/api/batch-audits/compare/export?baseline_run_id=run-exp-1&comparison_run_id=run-exp-2&format=pdf"
    )
    assert res_bad.status_code == 422


def test_end_to_end_audit_comparison_workflow(api_client):
    """Complete end-to-end workflow verification:
    List runs -> Select runs -> Compare -> Review Issues/Metadata/Coverage/Warnings -> Export.
    """
    client, repo, _ = api_client

    # 1. Seed realistic baseline run with 2 pages
    p_base_1 = PageAuditResult(
        run_id="run-base",
        url="https://example.com/home",
        final_url="https://example.com/home",
        status="success",
        status_code=200,
        title="Original Home Title",
        meta_description=None,  # Missing in baseline
        findings=[
            Finding(
                rule_id="meta-description",
                title="Meta Description",
                status="issue",
                explanation="Missing meta description tag.",
            ),
            Finding(
                rule_id="img-alt-tags",
                title="Image Alt Tags",
                status="warning",
                explanation="1 image missing alt tag.",
            ),
        ],
    )
    p_base_2 = PageAuditResult(
        run_id="run-base",
        url="https://example.com/contact",
        final_url="https://example.com/contact",
        status="success",
        status_code=200,
        title="Contact Us",
        meta_description="Contact our team",
        findings=[],
    )
    seed_run(repo, "run-base", target_origin="https://example.com", pages=[p_base_1, p_base_2])

    # 2. Seed comparison run with improvements, 1 regression, 1 new page, and 1 missing page
    p_comp_1 = PageAuditResult(
        run_id="run-comp",
        url="https://example.com/home",
        final_url="https://example.com/home",
        status="success",
        status_code=200,
        title="Optimized Home Title for Better CTR",  # Changed
        meta_description="Added high-converting description",  # Added
        findings=[
            # Resolved: meta-description is now passing
            Finding(
                rule_id="meta-description",
                title="Meta Description",
                status="pass",
                explanation="Meta description present and optimal length.",
            ),
            # Persistent: img-alt-tags still warning
            Finding(
                rule_id="img-alt-tags",
                title="Image Alt Tags",
                status="warning",
                explanation="1 image missing alt tag.",
            ),
            # New regression: H1 removed
            Finding(
                rule_id="h1-presence",
                title="H1 Heading",
                status="issue",
                explanation="No H1 tag found on page.",
            ),
        ],
    )
    p_comp_new = PageAuditResult(
        run_id="run-comp",
        url="https://example.com/pricing",  # Newly discovered page
        final_url="https://example.com/pricing",
        status="success",
        status_code=200,
        title="Transparent Pricing",
        meta_description="Check our prices",
        findings=[],
    )
    seed_run(
        repo,
        "run-comp",
        target_origin="https://example.com",
        status="partial",  # Partial status to test warnings
        pages=[p_comp_1, p_comp_new],
    )

    # Step 1 & 2: List runs in history
    list_res = client.get("/api/batch-audits?limit=10")
    assert list_res.status_code == 200
    runs = list_res.json()["runs"]
    assert len(runs) >= 2
    run_ids = [r["id"] for r in runs]
    assert "run-base" in run_ids and "run-comp" in run_ids

    # Step 3, 4, 5: Compare baseline against newer comparison run
    comp_res = client.post(
        "/api/batch-audits/compare",
        json={"baseline_run_id": "run-base", "comparison_run_id": "run-comp"},
    )
    assert comp_res.status_code == 200
    comp_data = comp_res.json()

    # Step 6: Review issue changes
    summary = comp_data["summary"]
    assert summary["resolved_issues_count"] == 1  # meta-description resolved on /home
    assert summary["persistent_issues_count"] == 1  # img-alt-tags persistent on /home
    assert summary["new_issues_count"] == 1  # h1-presence new on /home

    # Step 7: Review metadata changes
    assert summary["metadata_changes_count"] == 2  # title changed + meta_description added
    meta_changes = comp_data["metadata_changes"]
    fields_changed = [m["field_name"] for m in meta_changes]
    assert "title" in fields_changed
    assert "meta_description" in fields_changed

    # Step 8: Review page coverage
    assert summary["common_pages_count"] == 1  # /home
    assert summary["new_pages_count"] == 1  # /pricing
    assert summary["missing_pages_count"] == 1  # /contact

    # Step 9: Review partial coverage warnings
    assert summary["comparison_completeness"] == "partial"
    assert len(summary["coverage_warnings"]) >= 1
    assert any("partial" in w for w in summary["coverage_warnings"])
    assert comp_data["assessment"]["verdict"] == "mixed"

    # Step 10: Export reports
    export_json = client.get(
        "/api/batch-audits/compare/export?baseline_run_id=run-base&comparison_run_id=run-comp&format=json"
    )
    assert export_json.status_code == 200
    assert "application/json" in export_json.headers["content-type"]

    export_md = client.get(
        "/api/batch-audits/compare/export?baseline_run_id=run-base&comparison_run_id=run-comp&format=markdown"
    )
    assert export_md.status_code == 200
    assert "## Executive Assessment" in export_md.text
    assert "## SEO Metadata Changes" in export_md.text
