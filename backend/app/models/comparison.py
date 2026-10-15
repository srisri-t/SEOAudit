"""Pydantic schemas and models for M6.1 Audit Run Comparison."""

from __future__ import annotations

from typing import Any, Literal
from pydantic import BaseModel, Field

from app.models.audit import FindingStatus
from app.models.batch import BatchAuditRunResponse

ComparisonCompleteness = Literal["complete", "partial", "incomplete"]
AssessmentVerdict = Literal["improved", "deteriorated", "mixed", "unchanged", "incomplete"]
IssueChangeType = Literal["new", "resolved", "persistent", "incomparable"]
MetadataChangeType = Literal["added", "removed", "changed", "unchanged", "unavailable"]
CoveragePageStatus = Literal["common", "new", "missing_in_comparison"]


class AuditComparisonRequest(BaseModel):
    """Request payload to compare two existing batch audit runs."""

    baseline_run_id: str = Field(
        ...,
        description="ID of the older or reference baseline audit run",
        min_length=1,
    )
    comparison_run_id: str = Field(
        ...,
        description="ID of the newer audit run being compared against the baseline",
        min_length=1,
    )


class IssueComparisonItem(BaseModel):
    """An individual SEO issue compared across runs."""

    page_url: str = Field(..., description="Target page URL")
    rule_id: str = Field(..., description="Stable audit rule identifier (e.g. page-title, meta-description)")
    rule_title: str = Field(..., description="Human-readable rule title")
    status: FindingStatus = Field(..., description="Status verdict in the newer run (or baseline if resolved)")
    change_type: IssueChangeType = Field(
        ...,
        description="Whether this issue is new, resolved, persistent across runs, or incomparable",
    )
    explanation: str = Field(..., description="Factual explanation of the issue")
    recommendation: str | None = Field(default=None, description="Recommended remediation action")
    evidence: str | None = Field(default=None, description="Captured evidence from the page")
    incomparable_reason: str | None = Field(
        default=None,
        description="Reason why issue could not be reliably compared (e.g. page fetch failure, partial coverage)",
    )


class MetadataFieldChange(BaseModel):
    """SEO metadata difference for a page present in both runs."""

    page_url: str = Field(..., description="Target page URL")
    field_name: Literal["title", "meta_description", "canonical_url", "status_code"] = Field(
        ...,
        description="Name of the metadata field evaluated",
    )
    baseline_value: str | None = Field(default=None, description="Value extracted in the baseline run")
    comparison_value: str | None = Field(default=None, description="Value extracted in the comparison run")
    change_type: MetadataChangeType = Field(
        ...,
        description="Classification: added, removed, changed, unchanged, or unavailable",
    )


class PageCoverageItem(BaseModel):
    """Page presence and status comparison between the two runs."""

    url: str = Field(..., description="Page URL")
    coverage_status: CoveragePageStatus = Field(
        ...,
        description="Presence classification: common (both), new (newer run only), or missing_in_comparison (baseline only)",
    )
    baseline_page_status: str | None = Field(
        default=None,
        description="Status in baseline run: success, failed, skipped, or not_present",
    )
    comparison_page_status: str | None = Field(
        default=None,
        description="Status in comparison run: success, failed, skipped, or not_present",
    )


class ComparisonSummary(BaseModel):
    """Aggregated metrics and counts comparing the two runs."""

    baseline_run_id: str
    baseline_created_at: str
    comparison_run_id: str
    comparison_created_at: str
    website_scope: str

    total_pages_baseline: int = 0
    total_pages_comparison: int = 0
    common_pages_count: int = 0
    new_pages_count: int = 0
    missing_pages_count: int = 0

    new_issues_count: int = 0
    resolved_issues_count: int = 0
    persistent_issues_count: int = 0
    incomparable_findings_count: int = 0

    metadata_changes_count: int = 0
    page_retrieval_failures: int = 0

    coverage_warnings: list[str] = Field(default_factory=list)
    comparison_completeness: ComparisonCompleteness = "complete"


class ComparisonAssessment(BaseModel):
    """High-level evidence-based verdict and explanation of the comparison."""

    verdict: AssessmentVerdict = Field(
        ...,
        description="Overall verdict: improved, deteriorated, mixed, unchanged, or incomplete",
    )
    headline: str = Field(..., description="Concise summary headline")
    explanation: str = Field(..., description="Detailed, factual reasoning based on comparison evidence")


class AuditComparisonResponse(BaseModel):
    """Complete structured response schema for audit comparison."""

    baseline_run: BatchAuditRunResponse
    comparison_run: BatchAuditRunResponse
    summary: ComparisonSummary
    assessment: ComparisonAssessment
    issue_changes: list[IssueComparisonItem] = Field(default_factory=list)
    metadata_changes: list[MetadataFieldChange] = Field(default_factory=list)
    page_coverage: list[PageCoverageItem] = Field(default_factory=list)
