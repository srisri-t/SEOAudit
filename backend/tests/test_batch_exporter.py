"""Tests for report exports (JSON, CSV, Markdown) and formula injection mitigation."""

from __future__ import annotations

import csv
import io
import json

from app.engine.batch.exporter import (
    export_batch_csv,
    export_batch_json,
    export_batch_markdown,
    sanitize_csv_cell,
)
from app.models.audit import Finding
from app.models.batch import (
    AggregateSummary,
    BatchAuditConfig,
    BatchAuditRunResponse,
    DuplicateTitleGroup,
    InternalLinkSummary,
    PageAuditResult,
)


def test_sanitize_csv_cell_formula_injection():
    """Verify dangerous formula prefixes are escaped with a leading single quote."""
    # Dangerous formula characters: =, +, -, @, \t, \r
    assert sanitize_csv_cell("=1+1") == "'=1+1"
    assert sanitize_csv_cell("+cmd|' /C calc'!A0") == "'+cmd|' /C calc'!A0"
    assert sanitize_csv_cell("-2+3") == "'-2+3"
    assert sanitize_csv_cell("@SUM(A1:A10)") == "'@SUM(A1:A10)"
    assert sanitize_csv_cell("\tTabbed") == "'\tTabbed"
    assert sanitize_csv_cell("\rReturn") == "'\rReturn"

    # Safe values remain untouched
    assert sanitize_csv_cell("Normal Title") == "Normal Title"
    assert sanitize_csv_cell("https://example.com") == "https://example.com"
    assert sanitize_csv_cell(200) == "200"
    assert sanitize_csv_cell(None) == ""


def test_export_batch_json_structure():
    """Verify complete JSON export contains run metadata and pages."""
    run = BatchAuditRunResponse(
        id="test-run-json",
        target_origin="https://example.com",
        status="completed",
        mode="static",
        config=BatchAuditConfig(),
        total_pages=1,
        completed_pages=1,
        created_at="2026-10-14T12:00:00Z",
        aggregate_summary=AggregateSummary(
            total_pages_discovered=1,
            total_pages_audited=1,
            successful_pages=1,
        ),
    )
    pages = [
        PageAuditResult(
            run_id="test-run-json",
            url="https://example.com/home",
            status="success",
            status_code=200,
            title="Home",
            findings=[
                Finding(
                    rule_id="page-title",
                    title="Page Title Presence",
                    status="pass",
                    explanation="Title OK",
                )
            ],
        )
    ]

    json_str = export_batch_json(run, pages)
    parsed = json.loads(json_str)

    assert "run" in parsed
    assert "pages" in parsed
    assert parsed["run"]["id"] == "test-run-json"
    assert len(parsed["pages"]) == 1
    assert parsed["pages"][0]["title"] == "Home"
    assert parsed["pages"][0]["findings"][0]["status"] == "pass"


def test_export_batch_csv_with_formula_escaping():
    """Verify CSV export writes valid CSV and neutralizes formula injection in titles."""
    run = BatchAuditRunResponse(
        id="test-run-csv",
        target_origin="https://example.com",
        status="completed",
        mode="static",
        config=BatchAuditConfig(),
        total_pages=2,
        completed_pages=2,
        created_at="2026-10-14T12:00:00Z",
    )
    pages = [
        PageAuditResult(
            run_id="test-run-csv",
            url="https://example.com/safe",
            status="success",
            status_code=200,
            title="Safe Title",
            meta_description="Normal description",
        ),
        PageAuditResult(
            run_id="test-run-csv",
            url="https://example.com/malicious",
            status="success",
            status_code=200,
            title="=HYPERLINK('http://attacker.com')",
            meta_description="@ALERT('pwned')",
        ),
    ]

    csv_str = export_batch_csv(run, pages)
    reader = list(csv.reader(io.StringIO(csv_str)))

    # Header row
    assert reader[0][0] == "run_id"
    assert reader[0][7] == "title"
    assert reader[0][8] == "meta_description"

    # Row 1 (safe)
    assert reader[1][7] == "Safe Title"

    # Row 2 (sanitized formula values)
    assert reader[2][7] == "'=HYPERLINK('http://attacker.com')"
    assert reader[2][8] == "'@ALERT('pwned')"


def test_export_batch_markdown():
    """Verify Markdown export contains executive summary and tables."""
    run = BatchAuditRunResponse(
        id="test-run-md",
        target_origin="https://example.com",
        status="completed",
        mode="static",
        config=BatchAuditConfig(),
        total_pages=2,
        completed_pages=2,
        created_at="2026-10-14T12:00:00Z",
        aggregate_summary=AggregateSummary(
            total_pages_discovered=2,
            total_pages_audited=2,
            successful_pages=2,
            duplicate_titles=[
                DuplicateTitleGroup(
                    title="Shared Title",
                    count=2,
                    urls=["https://example.com/1", "https://example.com/2"],
                )
            ],
            status_code_distribution={"200": 2},
            findings_by_severity={"pass": 10, "warning": 2},
            internal_link_analysis=InternalLinkSummary(),
        ),
    )
    pages = [
        PageAuditResult(
            run_id="test-run-md",
            url="https://example.com/1",
            status="success",
            status_code=200,
            title="Shared Title",
            fetch_duration_ms=150,
        ),
        PageAuditResult(
            run_id="test-run-md",
            url="https://example.com/2",
            status="success",
            status_code=200,
            title="Shared Title",
            fetch_duration_ms=180,
        ),
    ]

    md_str = export_batch_markdown(run, pages)

    assert "# Universal SEO Automation Platform — Batch Audit Report" in md_str
    assert "test-run-md" in md_str
    assert "## Executive Summary" in md_str
    assert "## Duplicate Page Titles" in md_str
    assert "Shared Title" in md_str
    assert "## Page Results Summary" in md_str
