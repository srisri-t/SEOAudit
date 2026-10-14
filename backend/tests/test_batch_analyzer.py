"""Tests for website-wide aggregate SEO analysis and link validation."""

from __future__ import annotations

from app.engine.batch.analyzer import (
    calculate_aggregate_summary,
    normalize_url_for_comparison,
)
from app.models.audit import Finding
from app.models.batch import PageAuditResult


def test_normalize_url_for_comparison():
    """Verify URL normalization removes fragments, lowercases host, and strips trailing slashes."""
    u1 = "https://EXAMPLE.COM/about/"
    u2 = "https://example.com/about#team"
    u3 = "https://example.com/about"

    assert normalize_url_for_comparison(u1) == "https://example.com/about"
    assert normalize_url_for_comparison(u2) == "https://example.com/about"
    assert normalize_url_for_comparison(u3) == "https://example.com/about"

    # Root trailing slash preservation
    assert normalize_url_for_comparison("https://example.com/") == "https://example.com/"


def test_duplicate_titles_and_descriptions():
    """Verify grouping of identical titles and descriptions across distinct pages."""
    pages = [
        PageAuditResult(
            run_id="run-dup",
            url="https://example.com/p1",
            status="success",
            status_code=200,
            title="Shared Product Title",
            meta_description="Shared Description Text",
        ),
        PageAuditResult(
            run_id="run-dup",
            url="https://example.com/p2",
            status="success",
            status_code=200,
            title="Shared Product Title",
            meta_description="Unique Description 2",
        ),
        PageAuditResult(
            run_id="run-dup",
            url="https://example.com/p3",
            status="success",
            status_code=200,
            title="Shared Product Title",
            meta_description="Shared Description Text",
        ),
        PageAuditResult(
            run_id="run-dup",
            url="https://example.com/p4",
            status="success",
            status_code=200,
            title="Unique Title 4",
            meta_description=None,  # Missing description
        ),
        PageAuditResult(
            run_id="run-dup",
            url="https://example.com/p5",
            status="success",
            status_code=200,
            title=None,  # Missing title
            meta_description="",  # Empty description
        ),
    ]

    summary = calculate_aggregate_summary(
        pages=pages,
        total_discovered=5,
        target_origin="https://example.com",
    )

    assert summary.total_pages_audited == 5
    assert summary.successful_pages == 5
    assert summary.missing_titles_count == 1
    assert summary.missing_descriptions_count == 2

    # Duplicate titles
    assert len(summary.duplicate_titles) == 1
    assert summary.duplicate_titles[0].title == "Shared Product Title"
    assert summary.duplicate_titles[0].count == 3
    assert set(summary.duplicate_titles[0].urls) == {
        "https://example.com/p1",
        "https://example.com/p2",
        "https://example.com/p3",
    }

    # Duplicate descriptions
    assert len(summary.duplicate_descriptions) == 1
    assert summary.duplicate_descriptions[0].description == "Shared Description Text"
    assert summary.duplicate_descriptions[0].count == 2
    assert set(summary.duplicate_descriptions[0].urls) == {
        "https://example.com/p1",
        "https://example.com/p3",
    }


def test_internal_link_analysis_broken_and_unverified():
    """Verify internal link verification identifies confirmed broken links and unverified links."""
    pages = [
        # Source page linking to:
        # 1. /good (audited, 200)
        # 2. /broken (audited, 404)
        # 3. /failed (audited, failed)
        # 4. /unvisited (not in audited batch)
        # 5. https://external.org (external link)
        PageAuditResult(
            run_id="run-link",
            url="https://example.com/index",
            status="success",
            status_code=200,
            title="Home",
            outgoing_links=[
                "https://example.com/good",
                "https://example.com/broken",
                "https://example.com/failed",
                "https://example.com/unvisited",
                "https://github.com/srisri-t/SEOAudit",
            ],
        ),
        PageAuditResult(
            run_id="run-link",
            url="https://example.com/good",
            status="success",
            status_code=200,
            title="Good Page",
            outgoing_links=[],
        ),
        PageAuditResult(
            run_id="run-link",
            url="https://example.com/broken",
            status="success",
            status_code=404,
            title="Not Found",
            outgoing_links=[],
        ),
        PageAuditResult(
            run_id="run-link",
            url="https://example.com/failed",
            status="failed",
            status_code=None,
            error_message="Connection refused",
            outgoing_links=[],
        ),
    ]

    summary = calculate_aggregate_summary(
        pages=pages,
        total_discovered=4,
        target_origin="https://example.com",
    )

    link_info = summary.internal_link_analysis
    assert link_info.total_internal_links_checked == 4
    assert link_info.external_links_count == 1

    # Confirmed broken should include /broken (404) and /failed
    broken_targets = {bl.target_url for bl in link_info.confirmed_broken_links}
    assert "https://example.com/broken" in broken_targets
    assert "https://example.com/failed" in broken_targets
    assert len(link_info.confirmed_broken_links) == 2

    # Unverified should include /unvisited
    unverified_targets = {ul.target_url for ul in link_info.unverified_internal_links}
    assert "https://example.com/unvisited" in unverified_targets
    assert len(link_info.unverified_internal_links) == 1
