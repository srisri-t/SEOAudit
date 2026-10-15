"""Unit and scenario tests for M6.1 Audit Comparison Engine."""

from __future__ import annotations

import pytest

from app.engine.comparison.comparator import compare_audit_runs
from app.engine.comparison.exporter import (
    export_comparison_json,
    export_comparison_markdown,
)
from app.engine.comparison.normalizer import (
    are_origins_compatible,
    normalize_origin,
    normalize_url_for_matching,
)
from app.models.audit import Finding
from app.models.batch import (
    BatchAuditConfig,
    BatchAuditRunResponse,
    PageAuditResult,
)


def make_dummy_run(
    run_id: str,
    target_origin: str = "https://example.com",
    status: str = "completed",
    created_at: str = "2026-10-14T10:00:00Z",
) -> BatchAuditRunResponse:
    """Helper to construct dummy BatchAuditRunResponse."""
    return BatchAuditRunResponse(
        id=run_id,
        target_origin=target_origin,
        status=status,
        mode="static",
        config=BatchAuditConfig(),
        total_pages=1,
        completed_pages=1,
        created_at=created_at,
    )


def make_dummy_page(
    run_id: str,
    url: str,
    status: str = "success",
    title: str | None = "Example Page",
    meta_description: str | None = "A great page",
    canonical_url: str | None = "https://example.com",
    status_code: int = 200,
    findings: list[Finding] | None = None,
    error_message: str | None = None,
) -> PageAuditResult:
    """Helper to construct dummy PageAuditResult."""
    return PageAuditResult(
        run_id=run_id,
        url=url,
        final_url=url,
        status=status,
        status_code=status_code,
        title=title,
        meta_description=meta_description,
        canonical_url=canonical_url,
        findings=findings or [],
        error_message=error_message,
    )


# ==============================================================================
# 1. URL Normalization Tests
# ==============================================================================

def test_url_normalization_scheme_and_host_casing():
    """Case-insensitive host and scheme normalization."""
    url1 = "HTTPS://Example.COM/Path"
    url2 = "https://example.com/path"
    assert normalize_url_for_matching(url1) == "https://example.com/Path"
    assert normalize_url_for_matching(url2) == "https://example.com/path"
    # Note: scheme and host are lowercased
    assert normalize_url_for_matching("HTTP://MY-SITE.ORG/abc") == "http://my-site.org/abc"


def test_url_normalization_default_ports():
    """Default HTTP (80) and HTTPS (443) ports are removed."""
    assert normalize_url_for_matching("http://example.com:80/about") == "http://example.com/about"
    assert normalize_url_for_matching("https://example.com:443/about") == "https://example.com/about"
    assert normalize_url_for_matching("https://example.com:8443/about") == "https://example.com:8443/about"


def test_url_normalization_fragment_stripping():
    """Fragments are removed completely."""
    assert normalize_url_for_matching("https://example.com/page#section-1") == "https://example.com/page"
    assert normalize_url_for_matching("https://example.com/page#") == "https://example.com/page"


def test_url_normalization_trailing_slashes():
    """Root path preserves trailing slash, subpaths have trailing slash trimmed."""
    assert normalize_url_for_matching("https://example.com") == "https://example.com/"
    assert normalize_url_for_matching("https://example.com/") == "https://example.com/"
    assert normalize_url_for_matching("https://example.com/about/") == "https://example.com/about"
    assert normalize_url_for_matching("https://example.com/about") == "https://example.com/about"


def test_url_normalization_query_strings_preserved_and_sorted():
    """Query parameters are preserved and sorted deterministically."""
    url1 = "https://example.com/search?b=2&a=1"
    url2 = "https://example.com/search?a=1&b=2"
    assert normalize_url_for_matching(url1) == "https://example.com/search?a=1&b=2"
    assert normalize_url_for_matching(url1) == normalize_url_for_matching(url2)

    # Distinct queries must not be merged
    assert normalize_url_for_matching("https://example.com/p?id=1") != normalize_url_for_matching("https://example.com/p?id=2")


def test_origin_normalization_and_compatibility():
    """Origin comparison correctly validates site scope."""
    assert normalize_origin("https://example.com/some/path") == "https://example.com"
    assert normalize_origin("http://example.com:80") == "http://example.com"
    assert normalize_origin("https://example.com:443") == "https://example.com"
    assert are_origins_compatible("https://example.com/", "https://example.com:443") is True
    assert are_origins_compatible("https://example.com", "http://example.com") is False
    assert are_origins_compatible("https://site-a.com", "https://site-b.com") is False


# ==============================================================================
# 2. Comparison Engine Core Tests
# ==============================================================================

def test_identical_runs_produce_no_changes():
    """Comparing identical runs results in 'unchanged' verdict and zero changes."""
    base_run = make_dummy_run("run-1", created_at="2026-10-14T09:00:00Z")
    comp_run = make_dummy_run("run-2", created_at="2026-10-14T10:00:00Z")

    page_1 = make_dummy_page("run-1", "https://example.com/p1")
    page_2 = make_dummy_page("run-2", "https://example.com/p1")

    res = compare_audit_runs(base_run, [page_1], comp_run, [page_2])

    assert res.assessment.verdict == "unchanged"
    assert res.summary.new_issues_count == 0
    assert res.summary.resolved_issues_count == 0
    assert res.summary.persistent_issues_count == 0
    assert res.summary.metadata_changes_count == 0
    assert res.summary.common_pages_count == 1
    assert res.summary.comparison_completeness == "complete"


def test_detect_new_issue():
    """An issue present in the newer run but absent in baseline is flagged as 'new'."""
    base_run = make_dummy_run("run-1")
    comp_run = make_dummy_run("run-2")

    base_page = make_dummy_page("run-1", "https://example.com/page", findings=[])
    comp_page = make_dummy_page(
        "run-2",
        "https://example.com/page",
        findings=[
            Finding(
                rule_id="meta-description",
                title="Meta Description Presence",
                status="issue",
                explanation="Meta description tag is missing.",
            )
        ],
    )

    res = compare_audit_runs(base_run, [base_page], comp_run, [comp_page])

    assert res.summary.new_issues_count == 1
    assert res.summary.resolved_issues_count == 0
    assert res.assessment.verdict == "deteriorated"
    assert len(res.issue_changes) == 1
    assert res.issue_changes[0].change_type == "new"
    assert res.issue_changes[0].rule_id == "meta-description"


def test_detect_resolved_issue():
    """An issue present in baseline that passes in newer run is flagged as 'resolved'."""
    base_run = make_dummy_run("run-1")
    comp_run = make_dummy_run("run-2")

    base_page = make_dummy_page(
        "run-1",
        "https://example.com/page",
        findings=[
            Finding(
                rule_id="page-title",
                title="Page Title Presence",
                status="issue",
                explanation="Page title was missing.",
            )
        ],
    )
    comp_page = make_dummy_page(
        "run-2",
        "https://example.com/page",
        findings=[
            Finding(
                rule_id="page-title",
                title="Page Title Presence",
                status="pass",
                explanation="Page title is now present.",
            )
        ],
    )

    res = compare_audit_runs(base_run, [base_page], comp_run, [comp_page])

    assert res.summary.resolved_issues_count == 1
    assert res.summary.new_issues_count == 0
    assert res.assessment.verdict == "improved"
    assert len(res.issue_changes) == 1
    assert res.issue_changes[0].change_type == "resolved"


def test_detect_persistent_issue():
    """An issue present in both runs is flagged as 'persistent'."""
    base_run = make_dummy_run("run-1")
    comp_run = make_dummy_run("run-2")

    finding = Finding(
        rule_id="img-alt-tags",
        title="Image Alt Attribute Presence",
        status="warning",
        explanation="Images are missing alt text.",
    )

    base_page = make_dummy_page("run-1", "https://example.com/page", findings=[finding])
    comp_page = make_dummy_page("run-2", "https://example.com/page", findings=[finding])

    res = compare_audit_runs(base_run, [base_page], comp_run, [comp_page])

    assert res.summary.persistent_issues_count == 1
    assert res.summary.new_issues_count == 0
    assert res.summary.resolved_issues_count == 0
    assert res.issue_changes[0].change_type == "persistent"


def test_duplicate_findings_do_not_inflate_counts():
    """Repeated identical findings for the same rule on the same page are deduplicated."""
    base_run = make_dummy_run("run-1")
    comp_run = make_dummy_run("run-2")

    finding = Finding(
        rule_id="h1-presence",
        title="H1 Heading",
        status="issue",
        explanation="No H1 tag found.",
    )

    # Page with duplicated findings in list
    base_page = make_dummy_page("run-1", "https://example.com/page", findings=[finding, finding])
    comp_page = make_dummy_page("run-2", "https://example.com/page", findings=[finding, finding])

    res = compare_audit_runs(base_run, [base_page], comp_run, [comp_page])

    assert res.summary.persistent_issues_count == 1
    assert len(res.issue_changes) == 1


def test_page_coverage_new_and_missing_pages():
    """Identifies newly discovered pages and pages missing in comparison run."""
    base_run = make_dummy_run("run-1")
    comp_run = make_dummy_run("run-2")

    base_p1 = make_dummy_page("run-1", "https://example.com/p1")
    base_p2 = make_dummy_page("run-1", "https://example.com/p2")

    comp_p1 = make_dummy_page("run-2", "https://example.com/p1")
    comp_p3 = make_dummy_page("run-2", "https://example.com/p3")

    res = compare_audit_runs(base_run, [base_p1, base_p2], comp_run, [comp_p1, comp_p3])

    assert res.summary.common_pages_count == 1
    assert res.summary.missing_pages_count == 1  # p2 missing in comp
    assert res.summary.new_pages_count == 1      # p3 new in comp

    statuses = {item.url: item.coverage_status for item in res.page_coverage}
    assert statuses["https://example.com/p1"] == "common"
    assert statuses["https://example.com/p2"] == "missing_in_comparison"
    assert statuses["https://example.com/p3"] == "new"


def test_partial_coverage_does_not_falsely_mark_issues_resolved():
    """If a page is missing in comparison run, its issues are marked 'incomparable', not 'resolved'."""
    base_run = make_dummy_run("run-1")
    comp_run = make_dummy_run("run-2")

    base_p1 = make_dummy_page(
        "run-1",
        "https://example.com/missing-page",
        findings=[
            Finding(
                rule_id="h1-presence",
                title="H1 Heading",
                status="issue",
                explanation="No H1 tag found.",
            )
        ],
    )
    # Comparison run does not contain this page
    comp_p2 = make_dummy_page("run-2", "https://example.com/other-page")

    res = compare_audit_runs(base_run, [base_p1], comp_run, [comp_p2])

    assert res.summary.resolved_issues_count == 0  # CRITICAL: must NOT be resolved!
    assert res.summary.incomparable_findings_count == 1
    incomp_item = [i for i in res.issue_changes if i.change_type == "incomparable"][0]
    assert incomp_item.incomparable_reason == "Page not present in newer audit"


def test_failed_page_retrieval_does_not_become_false_improvement():
    """If a page fails to load in newer run, its issues are 'incomparable', not resolved."""
    base_run = make_dummy_run("run-1")
    comp_run = make_dummy_run("run-2")

    base_page = make_dummy_page(
        "run-1",
        "https://example.com/page",
        findings=[
            Finding(
                rule_id="page-title",
                title="Page Title Presence",
                status="issue",
                explanation="Title missing.",
            )
        ],
    )
    # In newer run, page fetch failed with 500
    comp_page = make_dummy_page(
        "run-2",
        "https://example.com/page",
        status="failed",
        status_code=500,
        error_message="HTTP 500 Internal Server Error",
        findings=[],
    )

    res = compare_audit_runs(base_run, [base_page], comp_run, [comp_page])

    assert res.summary.resolved_issues_count == 0  # CRITICAL: must not count as resolved!
    assert res.summary.incomparable_findings_count == 1
    assert res.issue_changes[0].change_type == "incomparable"
    assert "Page retrieval failed" in res.issue_changes[0].incomparable_reason


def test_metadata_changes_detection():
    """Detects added, removed, and changed titles, descriptions, and status codes."""
    base_run = make_dummy_run("run-1")
    comp_run = make_dummy_run("run-2")

    base_page = make_dummy_page(
        "run-1",
        "https://example.com/about",
        title="Old Title",
        meta_description=None,
        canonical_url="https://example.com/about",
        status_code=200,
    )
    comp_page = make_dummy_page(
        "run-2",
        "https://example.com/about",
        title="New Title",
        meta_description="Newly added description",
        canonical_url="https://example.com/about",  # unchanged
        status_code=200,
    )

    res = compare_audit_runs(base_run, [base_page], comp_run, [comp_page])

    assert res.summary.metadata_changes_count == 2
    changes = {c.field_name: c for c in res.metadata_changes}
    assert changes["title"].change_type == "changed"
    assert changes["title"].baseline_value == "Old Title"
    assert changes["title"].comparison_value == "New Title"

    assert changes["meta_description"].change_type == "added"
    assert changes["meta_description"].baseline_value is None
    assert changes["meta_description"].comparison_value == "Newly added description"

    # Canonical unchanged should not be in changes list
    assert "canonical_url" not in changes


def test_incompatible_website_scopes_raise_error():
    """Comparing runs targeting different domains raises ValueError."""
    run_a = make_dummy_run("run-1", target_origin="https://site-a.com")
    run_b = make_dummy_run("run-2", target_origin="https://site-b.com")

    p1 = make_dummy_page("run-1", "https://site-a.com/")
    p2 = make_dummy_page("run-2", "https://site-b.com/")

    with pytest.raises(ValueError, match="incompatible website scopes"):
        compare_audit_runs(run_a, [p1], run_b, [p2])


def test_same_run_ids_raise_error():
    """Comparing identical run IDs raises ValueError."""
    run_a = make_dummy_run("run-1")
    p1 = make_dummy_page("run-1", "https://example.com/")

    with pytest.raises(ValueError, match="must be distinct"):
        compare_audit_runs(run_a, [p1], run_a, [p1])


def test_export_comparison_json_and_markdown():
    """JSON and Markdown exports are generated cleanly with sanitized tables."""
    base_run = make_dummy_run("run-1")
    comp_run = make_dummy_run("run-2")

    base_page = make_dummy_page("run-1", "https://example.com/page", title="Title A")
    comp_page = make_dummy_page("run-2", "https://example.com/page", title="Title | with pipes | B")

    comparison = compare_audit_runs(base_run, [base_page], comp_run, [comp_page])

    # Test JSON
    json_text = export_comparison_json(comparison)
    assert '"baseline_run"' in json_text
    assert '"summary"' in json_text
    assert "Title | with pipes | B" in json_text

    # Test Markdown
    md_text = export_comparison_markdown(comparison)
    assert "# Universal SEO Automation Platform — Audit Run Comparison" in md_text
    assert "## Executive Assessment" in md_text
    assert "## Summary Metrics" in md_text
    # Pipe characters must be escaped as \|
    assert "Title \\| with pipes \\| B" in md_text
