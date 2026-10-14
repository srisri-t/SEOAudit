"""Unit tests for metadata drift comparison and browser diagnostic rule evaluation."""

from __future__ import annotations

import pytest

from app.engine.browser.comparison import (
    compare_server_and_rendered_metadata,
    evaluate_browser_rules,
)
from app.engine.extractor import (
    CanonicalData,
    DescriptionData,
    ExtractedMetadata,
    RobotsDirectiveData,
    TitleData,
)
from app.models.audit import BrowserAuditResult, ConsoleMessage, PageException


def make_server_metadata(
    title: str = "Test Title",
    description: str = "Test Description",
    canonical: str = "https://example.com/page",
    meta_directives: list[str] | None = None,
) -> ExtractedMetadata:
    directives = meta_directives if meta_directives is not None else ["index", "follow"]
    return ExtractedMetadata(
        title=TitleData(text=title, length=len(title), count=1 if title else 0, is_missing=not bool(title), is_empty=not bool(title)),
        description=DescriptionData(text=description, length=len(description), count=1 if description else 0, is_missing=not bool(description), is_empty=not bool(description)),
        canonical=CanonicalData(raw_href=canonical, resolved_url=canonical, count=1 if canonical else 0, is_missing=not bool(canonical), is_empty=not bool(canonical), is_self_referential=True),
        robots=RobotsDirectiveData(meta_directives=directives),
    )


class TestMetadataComparison:
    """Tests for compare_server_and_rendered_metadata."""

    def test_identical_metadata_no_mismatch(self):
        server_meta = make_server_metadata()
        rendered_result = BrowserAuditResult(
            final_rendered_url="https://example.com/page",
            rendered_title="Test Title",
            rendered_meta_description="Test Description",
            rendered_canonical_url="https://example.com/page",
            rendered_meta_robots=["index", "follow"],
        )

        mismatch, details = compare_server_and_rendered_metadata(server_meta, rendered_result)
        assert mismatch is False
        assert len(details) == 0

    def test_title_discrepancy_detected(self):
        server_meta = make_server_metadata(title="Old Server Title")
        rendered_result = BrowserAuditResult(
            final_rendered_url="https://example.com/page",
            rendered_title="New Rendered Dynamic Title",
            rendered_meta_description="Test Description",
            rendered_canonical_url="https://example.com/page",
            rendered_meta_robots=["index", "follow"],
        )

        mismatch, details = compare_server_and_rendered_metadata(server_meta, rendered_result)
        assert mismatch is True
        assert len(details) == 1
        assert "Title discrepancy" in details[0]

    def test_canonical_and_robots_discrepancy_detected(self):
        server_meta = make_server_metadata(
            canonical="https://example.com/page",
            meta_directives=["index", "follow"],
        )
        rendered_result = BrowserAuditResult(
            final_rendered_url="https://example.com/page",
            rendered_title="Test Title",
            rendered_meta_description="Test Description",
            rendered_canonical_url="https://example.com/alternate",
            rendered_meta_robots=["noindex", "nofollow"],
        )

        mismatch, details = compare_server_and_rendered_metadata(server_meta, rendered_result)
        assert mismatch is True
        assert len(details) == 2
        assert any("Canonical URL discrepancy" in d for d in details)
        assert any("Robots directives discrepancy" in d for d in details)

    def test_both_representations_missing_optional_metadata_is_not_mismatch(self):
        """When optional metadata is absent in both representations, no mismatch is flagged."""
        server_meta = make_server_metadata(
            title="",
            description="",
            canonical="",
            meta_directives=[],
        )
        rendered_result = BrowserAuditResult(
            final_rendered_url="https://example.com/page",
            rendered_title=None,
            rendered_meta_description=None,
            rendered_canonical_url=None,
            rendered_meta_robots=[],
        )

        mismatch, details = compare_server_and_rendered_metadata(server_meta, rendered_result)
        assert mismatch is False
        assert len(details) == 0

    def test_canonical_normalization_avoids_false_positives(self):
        """Canonical URLs differing only by trailing slash or hostname case do not mismatch."""
        server_meta = make_server_metadata(canonical="https://EXAMPLE.COM/page/")
        rendered_result = BrowserAuditResult(
            final_rendered_url="https://example.com/page",
            rendered_title="Test Title",
            rendered_meta_description="Test Description",
            rendered_canonical_url="https://example.com/page",
            rendered_meta_robots=["index", "follow"],
        )

        mismatch, details = compare_server_and_rendered_metadata(server_meta, rendered_result)
        assert mismatch is False
        assert len(details) == 0



class TestEvaluateBrowserRules:
    """Tests for evaluate_browser_rules."""

    def test_clean_browser_result_passes_all_rules(self):
        result = BrowserAuditResult(
            final_rendered_url="https://example.com/page",
            hydration_mismatch=False,
            console_errors=[],
            page_exceptions=[],
            failed_subresources=[],
        )

        findings = evaluate_browser_rules(result)
        assert len(findings) == 2
        health_finding = next(f for f in findings if f.rule_id == "browser-console-health")
        drift_finding = next(f for f in findings if f.rule_id == "browser-hydration-drift")

        assert health_finding.status == "pass"
        assert drift_finding.status == "pass"

    def test_console_errors_and_page_exceptions_flagged(self):
        # 1. Console errors only -> warning
        res_warnings = BrowserAuditResult(
            final_rendered_url="https://example.com/page",
            console_errors=[ConsoleMessage(level="error", text="Uncaught TypeError in chunk.js")],
        )
        findings = evaluate_browser_rules(res_warnings)
        health = next(f for f in findings if f.rule_id == "browser-console-health")
        assert health.status == "warning"

        # 2. Runtime unhandled exception -> issue
        res_issue = BrowserAuditResult(
            final_rendered_url="https://example.com/page",
            page_exceptions=[PageException(message="ReferenceError: foo is not defined")],
        )
        findings2 = evaluate_browser_rules(res_issue)
        health2 = next(f for f in findings2 if f.rule_id == "browser-console-health")
        assert health2.status == "issue"

    def test_hydration_drift_rule_evaluation(self):
        # Normal discrepancy -> warning
        res_drift = BrowserAuditResult(
            final_rendered_url="https://example.com/page",
            hydration_mismatch=True,
            mismatch_details=["Title discrepancy: Server delivered 'A', DOM has 'B'."],
            rendered_meta_robots=["index"],
        )
        findings = evaluate_browser_rules(res_drift)
        drift = next(f for f in findings if f.rule_id == "browser-hydration-drift")
        assert drift.status == "warning"

        # Client added noindex -> issue
        res_noindex = BrowserAuditResult(
            final_rendered_url="https://example.com/page",
            hydration_mismatch=True,
            mismatch_details=["Robots discrepancy"],
            rendered_meta_robots=["noindex", "nofollow"],
        )
        findings2 = evaluate_browser_rules(res_noindex)
        drift2 = next(f for f in findings2 if f.rule_id == "browser-hydration-drift")
        assert drift2.status == "issue"
