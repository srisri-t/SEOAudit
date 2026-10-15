"""Deterministic comparison engine for evaluating two batch audit runs."""

from __future__ import annotations

import logging
from typing import Any

from app.engine.comparison.normalizer import (
    are_origins_compatible,
    normalize_origin,
    normalize_url_for_matching,
)
from app.models.batch import BatchAuditRunResponse, PageAuditResult
from app.models.comparison import (
    AssessmentVerdict,
    AuditComparisonResponse,
    ComparisonAssessment,
    ComparisonCompleteness,
    ComparisonSummary,
    IssueChangeType,
    IssueComparisonItem,
    MetadataChangeType,
    MetadataFieldChange,
    PageCoverageItem,
)

logger = logging.getLogger(__name__)


def compare_audit_runs(
    baseline_run: BatchAuditRunResponse,
    baseline_pages: list[PageAuditResult],
    comparison_run: BatchAuditRunResponse,
    comparison_pages: list[PageAuditResult],
) -> AuditComparisonResponse:
    """Execute a comprehensive, deterministic comparison between two stored audit runs.

    Args:
        baseline_run: The reference/older audit run metadata.
        baseline_pages: All page results from the baseline run.
        comparison_run: The newer audit run metadata.
        comparison_pages: All page results from the comparison run.

    Returns:
        Structured AuditComparisonResponse detailing issue changes, metadata differences,
        page coverage changes, aggregated summary, and an evidence-based assessment.

    Raises:
        ValueError: If run IDs are identical or target origins are incompatible.
    """
    if baseline_run.id == comparison_run.id:
        raise ValueError("Baseline and comparison run IDs must be distinct.")

    # 1. Verify Scope Compatibility
    website_scope = _determine_and_validate_scope(
        baseline_run, baseline_pages, comparison_run, comparison_pages
    )

    # 2. Index and Map Pages by Normalized URL
    baseline_map: dict[str, PageAuditResult] = {}
    for p in baseline_pages:
        norm = normalize_url_for_matching(p.url)
        if norm and norm not in baseline_map:
            baseline_map[norm] = p

    comparison_map: dict[str, PageAuditResult] = {}
    for p in comparison_pages:
        norm = normalize_url_for_matching(p.url)
        if norm and norm not in comparison_map:
            comparison_map[norm] = p

    common_keys = sorted(set(baseline_map.keys()) & set(comparison_map.keys()))
    new_keys = sorted(set(comparison_map.keys()) - set(baseline_map.keys()))
    missing_keys = sorted(set(baseline_map.keys()) - set(comparison_map.keys()))

    # 3. Build Page Coverage Items
    page_coverage: list[PageCoverageItem] = []
    for k in common_keys:
        page_coverage.append(
            PageCoverageItem(
                url=comparison_map[k].url,
                coverage_status="common",
                baseline_page_status=baseline_map[k].status,
                comparison_page_status=comparison_map[k].status,
            )
        )
    for k in new_keys:
        page_coverage.append(
            PageCoverageItem(
                url=comparison_map[k].url,
                coverage_status="new",
                baseline_page_status=None,
                comparison_page_status=comparison_map[k].status,
            )
        )
    for k in missing_keys:
        page_coverage.append(
            PageCoverageItem(
                url=baseline_map[k].url,
                coverage_status="missing_in_comparison",
                baseline_page_status=baseline_map[k].status,
                comparison_page_status=None,
            )
        )

    # 4. Coverage Warnings & Incomplete Status Detection
    coverage_warnings: list[str] = []
    if baseline_run.status in ("partial", "cancelled", "failed"):
        coverage_warnings.append(
            f"Baseline run was not fully completed (status: '{baseline_run.status}')."
        )
    if comparison_run.status in ("partial", "cancelled", "failed"):
        coverage_warnings.append(
            f"Comparison run was not fully completed (status: '{comparison_run.status}'). "
            "Some pages or issues may not have been audited."
        )

    total_failures = sum(
        1 for p in baseline_pages if p.status in ("failed", "skipped")
    ) + sum(1 for p in comparison_pages if p.status in ("failed", "skipped"))

    if missing_keys:
        coverage_warnings.append(
            f"{len(missing_keys)} page(s) present in the baseline audit were not present in the newer audit."
        )

    # 5. Extract and Index Findings
    # Key: (normalized_url, rule_id)
    baseline_issues: dict[tuple[str, str], tuple[Any, PageAuditResult]] = {}
    for norm_url, page in baseline_map.items():
        if page.status == "success":
            for f in page.findings:
                if f.status in ("warning", "issue", "error"):
                    key = (norm_url, f.rule_id)
                    if key not in baseline_issues:
                        baseline_issues[key] = (f, page)

    comparison_issues: dict[tuple[str, str], tuple[Any, PageAuditResult]] = {}
    for norm_url, page in comparison_map.items():
        if page.status == "success":
            for f in page.findings:
                if f.status in ("warning", "issue", "error"):
                    key = (norm_url, f.rule_id)
                    if key not in comparison_issues:
                        comparison_issues[key] = (f, page)

    # 6. Compare Issues (Persistent, Resolved, Incomparable, New)
    issue_changes: list[IssueComparisonItem] = []

    # Check all baseline issues
    for (norm_url, rule_id), (b_finding, b_page) in baseline_issues.items():
        if (norm_url, rule_id) in comparison_issues:
            # Present in both runs
            c_finding, c_page = comparison_issues[(norm_url, rule_id)]
            issue_changes.append(
                IssueComparisonItem(
                    page_url=c_page.url,
                    rule_id=rule_id,
                    rule_title=c_finding.title,
                    status=c_finding.status,
                    change_type="persistent",
                    explanation=c_finding.explanation,
                    recommendation=c_finding.recommendation,
                    evidence=c_finding.evidence,
                )
            )
        elif norm_url in common_keys:
            c_page = comparison_map[norm_url]
            if c_page.status == "success":
                # Page was audited successfully and issue is no longer reported!
                issue_changes.append(
                    IssueComparisonItem(
                        page_url=c_page.url,
                        rule_id=rule_id,
                        rule_title=b_finding.title,
                        status="pass",
                        change_type="resolved",
                        explanation=f"Resolved: {b_finding.title} passed in newer audit.",
                        recommendation=None,
                        evidence=None,
                    )
                )
            else:
                # Page failed in newer audit; cannot confirm resolution
                issue_changes.append(
                    IssueComparisonItem(
                        page_url=b_page.url,
                        rule_id=rule_id,
                        rule_title=b_finding.title,
                        status=b_finding.status,
                        change_type="incomparable",
                        explanation=f"Cannot verify resolution: page failed to load in newer audit ({c_page.error_message or 'fetch error'}).",
                        recommendation=b_finding.recommendation,
                        evidence=b_finding.evidence,
                        incomparable_reason="Page retrieval failed in comparison run",
                    )
                )
        else:
            # Page not present in newer audit
            issue_changes.append(
                IssueComparisonItem(
                    page_url=b_page.url,
                    rule_id=rule_id,
                    rule_title=b_finding.title,
                    status=b_finding.status,
                    change_type="incomparable",
                    explanation="Cannot verify resolution: page was not audited in the newer run.",
                    recommendation=b_finding.recommendation,
                    evidence=b_finding.evidence,
                    incomparable_reason="Page not present in newer audit",
                )
            )

    # Check for new issues in comparison run
    for (norm_url, rule_id), (c_finding, c_page) in comparison_issues.items():
        if (norm_url, rule_id) not in baseline_issues:
            issue_changes.append(
                IssueComparisonItem(
                    page_url=c_page.url,
                    rule_id=rule_id,
                    rule_title=c_finding.title,
                    status=c_finding.status,
                    change_type="new",
                    explanation=c_finding.explanation,
                    recommendation=c_finding.recommendation,
                    evidence=c_finding.evidence,
                )
            )

    # 7. Metadata Differencing for Common Successful Pages
    metadata_changes: list[MetadataFieldChange] = []
    for norm_url in common_keys:
        b_page = baseline_map[norm_url]
        c_page = comparison_map[norm_url]

        if b_page.status == "success" and c_page.status == "success":
            # Title
            if b_page.title != c_page.title:
                m_type: MetadataChangeType = (
                    "added"
                    if not b_page.title and c_page.title
                    else ("removed" if b_page.title and not c_page.title else "changed")
                )
                metadata_changes.append(
                    MetadataFieldChange(
                        page_url=c_page.url,
                        field_name="title",
                        baseline_value=b_page.title,
                        comparison_value=c_page.title,
                        change_type=m_type,
                    )
                )

            # Meta Description
            if b_page.meta_description != c_page.meta_description:
                m_type = (
                    "added"
                    if not b_page.meta_description and c_page.meta_description
                    else (
                        "removed"
                        if b_page.meta_description and not c_page.meta_description
                        else "changed"
                    )
                )
                metadata_changes.append(
                    MetadataFieldChange(
                        page_url=c_page.url,
                        field_name="meta_description",
                        baseline_value=b_page.meta_description,
                        comparison_value=c_page.meta_description,
                        change_type=m_type,
                    )
                )

            # Canonical URL
            if b_page.canonical_url != c_page.canonical_url:
                m_type = (
                    "added"
                    if not b_page.canonical_url and c_page.canonical_url
                    else (
                        "removed"
                        if b_page.canonical_url and not c_page.canonical_url
                        else "changed"
                    )
                )
                metadata_changes.append(
                    MetadataFieldChange(
                        page_url=c_page.url,
                        field_name="canonical_url",
                        baseline_value=b_page.canonical_url,
                        comparison_value=c_page.canonical_url,
                        change_type=m_type,
                    )
                )

            # HTTP Status Code
            if b_page.status_code != c_page.status_code:
                metadata_changes.append(
                    MetadataFieldChange(
                        page_url=c_page.url,
                        field_name="status_code",
                        baseline_value=str(b_page.status_code) if b_page.status_code else None,
                        comparison_value=str(c_page.status_code) if c_page.status_code else None,
                        change_type="changed",
                    )
                )

    # 8. Aggregation Counts
    new_count = sum(1 for item in issue_changes if item.change_type == "new")
    resolved_count = sum(1 for item in issue_changes if item.change_type == "resolved")
    persistent_count = sum(1 for item in issue_changes if item.change_type == "persistent")
    incomparable_count = sum(1 for item in issue_changes if item.change_type == "incomparable")

    # Completeness determination
    completeness: ComparisonCompleteness = "complete"
    if (
        baseline_run.status in ("partial", "cancelled", "failed")
        or comparison_run.status in ("partial", "cancelled", "failed")
    ):
        completeness = "partial"
    elif (
        len(baseline_pages) > 0
        and (len(missing_keys) > 0.5 * len(baseline_pages) or total_failures > 0.5 * (len(baseline_pages) + len(comparison_pages)))
    ):
        completeness = "incomplete"

    summary = ComparisonSummary(
        baseline_run_id=baseline_run.id,
        baseline_created_at=baseline_run.created_at,
        comparison_run_id=comparison_run.id,
        comparison_created_at=comparison_run.created_at,
        website_scope=website_scope,
        total_pages_baseline=len(baseline_pages),
        total_pages_comparison=len(comparison_pages),
        common_pages_count=len(common_keys),
        new_pages_count=len(new_keys),
        missing_pages_count=len(missing_keys),
        new_issues_count=new_count,
        resolved_issues_count=resolved_count,
        persistent_issues_count=persistent_count,
        incomparable_findings_count=incomparable_count,
        metadata_changes_count=len(metadata_changes),
        page_retrieval_failures=total_failures,
        coverage_warnings=coverage_warnings,
        comparison_completeness=completeness,
    )

    # 9. Derive Assessment Verdict
    assessment = _derive_assessment(summary)

    return AuditComparisonResponse(
        baseline_run=baseline_run,
        comparison_run=comparison_run,
        summary=summary,
        assessment=assessment,
        issue_changes=issue_changes,
        metadata_changes=metadata_changes,
        page_coverage=page_coverage,
    )


def _determine_and_validate_scope(
    baseline_run: BatchAuditRunResponse,
    baseline_pages: list[PageAuditResult],
    comparison_run: BatchAuditRunResponse,
    comparison_pages: list[PageAuditResult],
) -> str:
    """Validate that both runs evaluate compatible website scopes."""
    base_origin = baseline_run.target_origin.strip()
    comp_origin = comparison_run.target_origin.strip()

    # If both origins are explicitly set and not 'unknown'
    if base_origin and comp_origin and base_origin != "unknown" and comp_origin != "unknown":
        if not are_origins_compatible(base_origin, comp_origin):
            raise ValueError(
                f"Runs have incompatible website scopes: '{base_origin}' vs '{comp_origin}'. "
                "Audit comparison requires both runs to target the same website."
            )
        return normalize_origin(base_origin)

    # Fallback: check origins of audited pages
    base_page_origins = {
        normalize_origin(p.url) for p in baseline_pages if p.url
    }
    comp_page_origins = {
        normalize_origin(p.url) for p in comparison_pages if p.url
    }

    if base_page_origins and comp_page_origins:
        # Check if they share a common origin
        common_origins = base_page_origins & comp_page_origins
        if not common_origins:
            raise ValueError(
                f"Page URLs indicate incompatible website scopes: {base_page_origins} vs {comp_page_origins}."
            )
        return sorted(common_origins)[0]

    return normalize_origin(base_origin or comp_origin or "unknown")


def _derive_assessment(summary: ComparisonSummary) -> ComparisonAssessment:
    """Derive an evidence-based assessment of the website's SEO health progression."""
    if summary.comparison_completeness == "incomplete":
        return ComparisonAssessment(
            verdict="incomplete",
            headline="Incomplete Comparison",
            explanation=(
                f"Comparison cannot establish a reliable trend due to incomplete coverage "
                f"({summary.page_retrieval_failures} page retrieval failures, "
                f"{summary.missing_pages_count} unverified missing pages)."
            ),
        )

    # If run had partial coverage with significant missing pages, qualify the assessment
    is_partial = summary.comparison_completeness == "partial"

    new_i = summary.new_issues_count
    res_i = summary.resolved_issues_count
    pers_i = summary.persistent_issues_count
    meta_c = summary.metadata_changes_count

    if is_partial and (summary.missing_pages_count > 0 or summary.page_retrieval_failures > 0):
        if new_i > 0 and res_i == 0:
            return ComparisonAssessment(
                verdict="deteriorated",
                headline=f"Deteriorated with Partial Coverage ({new_i} New Issues)",
                explanation=(
                    f"Newer audit identified {new_i} new issues with 0 verified resolutions, "
                    f"though {summary.missing_pages_count} baseline pages were not evaluated."
                ),
            )
        return ComparisonAssessment(
            verdict="mixed",
            headline="Mixed Changes under Partial Run Coverage",
            explanation=(
                f"The newer run ended in a partial or interrupted state. "
                f"{res_i} issues were verified resolved and {new_i} new issues detected, "
                f"while {summary.incomparable_findings_count} findings remain unverified."
            ),
        )

    # Full coverage assessment
    if new_i == 0 and res_i == 0:
        if meta_c == 0:
            return ComparisonAssessment(
                verdict="unchanged",
                headline="No Detected SEO Changes",
                explanation=(
                    f"All {summary.common_pages_count} common pages maintained identical SEO findings "
                    f"and metadata across both runs ({pers_i} persistent issues)."
                ),
            )
        else:
            return ComparisonAssessment(
                verdict="mixed",
                headline="SEO Metadata Updated (No Rule Regressions)",
                explanation=(
                    f"{meta_c} metadata field(s) were updated across common pages without introducing "
                    f"new SEO rule violations ({pers_i} persistent issues)."
                ),
            )

    if new_i == 0 and res_i > 0:
        return ComparisonAssessment(
            verdict="improved",
            headline=f"SEO Health Improved ({res_i} Issues Resolved)",
            explanation=(
                f"{res_i} previous SEO issue(s) were successfully resolved across audited pages "
                f"with 0 regressions ({pers_i} persistent issues remaining)."
            ),
        )

    if new_i > 0 and res_i == 0:
        return ComparisonAssessment(
            verdict="deteriorated",
            headline=f"SEO Health Deteriorated ({new_i} New Issues)",
            explanation=(
                f"{new_i} new SEO issue(s) were detected across audited pages with 0 resolved issues, "
                f"indicating site health regression ({pers_i} persistent issues)."
            ),
        )

    # Both new and resolved issues present
    if res_i > new_i:
        return ComparisonAssessment(
            verdict="improved",
            headline=f"Net Improvement ({res_i} Resolved vs {new_i} New)",
            explanation=(
                f"{res_i} issue(s) resolved outpaced {new_i} new issue(s) introduced, "
                f"yielding net SEO improvement ({pers_i} persistent issues remaining)."
            ),
        )
    elif new_i > res_i:
        return ComparisonAssessment(
            verdict="deteriorated",
            headline=f"Net Deterioration ({new_i} New vs {res_i} Resolved)",
            explanation=(
                f"{new_i} new issue(s) exceeded {res_i} resolved issue(s), indicating "
                f"net SEO regression ({pers_i} persistent issues remaining)."
            ),
        )
    else:
        return ComparisonAssessment(
            verdict="mixed",
            headline=f"Mixed Changes ({new_i} New, {res_i} Resolved)",
            explanation=(
                f"Equal number of new and resolved issues ({new_i} each), "
                f"with {pers_i} persistent issues remaining across common pages."
            ),
        )
