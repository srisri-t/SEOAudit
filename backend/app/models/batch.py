"""Pydantic schemas and models for batch auditing and export engine."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal
from pydantic import BaseModel, Field, model_validator

from app.models.audit import Finding

RunStatus = Literal["queued", "running", "completed", "partial", "failed", "cancelled"]
PageStatus = Literal["success", "failed", "skipped"]
AuditMode = Literal["static", "browser"]


class BatchAuditConfig(BaseModel):
    """Configuration for batch audit execution."""

    max_pages: int = Field(
        default=50,
        ge=1,
        le=250,
        description="Maximum number of pages to audit within this batch run",
    )
    concurrency: int = Field(
        default=3,
        ge=1,
        le=10,
        description="Maximum number of parallel page audits running concurrently",
    )
    page_timeout_seconds: float = Field(
        default=15.0,
        ge=2.0,
        le=60.0,
        description="Execution timeout per individual page audit in seconds",
    )
    include_browser: bool = Field(
        default=False,
        description="Whether to perform headless browser rendering on audited pages",
    )


class BatchAuditCreateRequest(BaseModel):
    """Request payload to initiate a batch audit."""

    urls: list[str] = Field(
        default_factory=list,
        description="Explicit list of web page URLs to audit",
    )
    website_url: str | None = Field(
        default=None,
        description="Optional root website URL to discover sitemaps from",
    )
    sitemap_url: str | None = Field(
        default=None,
        description="Optional explicit sitemap XML URL to fetch and parse",
    )
    config: BatchAuditConfig = Field(
        default_factory=BatchAuditConfig,
        description="Execution limits and options for the batch run",
    )

    @model_validator(mode="after")
    def validate_inputs(self) -> BatchAuditCreateRequest:
        has_urls = bool(self.urls and any(u.strip() for u in self.urls))
        has_website = bool(self.website_url and self.website_url.strip())
        has_sitemap = bool(self.sitemap_url and self.sitemap_url.strip())
        if not (has_urls or has_website or has_sitemap):
            raise ValueError(
                "At least one URL source must be provided: 'urls', 'website_url', or 'sitemap_url'."
            )
        return self


class DuplicateTitleGroup(BaseModel):
    """Group of URLs sharing the same page title."""

    title: str
    count: int
    urls: list[str]


class DuplicateDescriptionGroup(BaseModel):
    """Group of URLs sharing the same meta description."""

    description: str
    count: int
    urls: list[str]


class BrokenLinkFinding(BaseModel):
    """Representation of an internal link issue discovered across the batch."""

    source_url: str
    target_url: str
    status_code: int | None = None
    reason: Literal["confirmed_broken", "unverified", "error"]


class InternalLinkSummary(BaseModel):
    """Audit analysis of internal link references within the batch scope."""

    total_internal_links_checked: int = 0
    confirmed_broken_links: list[BrokenLinkFinding] = Field(default_factory=list)
    unverified_internal_links: list[BrokenLinkFinding] = Field(default_factory=list)
    external_links_count: int = 0


class AggregateSummary(BaseModel):
    """Complete aggregate SEO metrics calculated across all pages in a batch run."""

    total_pages_discovered: int = 0
    total_pages_audited: int = 0
    successful_pages: int = 0
    failed_pages: int = 0
    skipped_pages: int = 0
    status_code_distribution: dict[str, int] = Field(default_factory=dict)
    findings_by_severity: dict[str, int] = Field(default_factory=dict)
    duplicate_titles: list[DuplicateTitleGroup] = Field(default_factory=list)
    duplicate_descriptions: list[DuplicateDescriptionGroup] = Field(default_factory=list)
    missing_titles_count: int = 0
    missing_descriptions_count: int = 0
    internal_link_analysis: InternalLinkSummary = Field(
        default_factory=InternalLinkSummary
    )


class PageAuditResult(BaseModel):
    """Audit result for a single URL within a batch run."""

    id: int | None = None
    run_id: str
    url: str
    final_url: str | None = None
    status: PageStatus
    status_code: int | None = None
    status_text: str | None = None
    fetch_duration_ms: int | None = None
    title: str | None = None
    meta_description: str | None = None
    canonical_url: str | None = None
    findings: list[Finding] = Field(default_factory=list)
    outgoing_links: list[str] = Field(default_factory=list)
    error_message: str | None = None
    audited_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


class BatchAuditRunResponse(BaseModel):
    """Full representation of a batch audit run."""

    id: str
    target_origin: str
    status: RunStatus
    mode: AuditMode
    config: BatchAuditConfig
    total_pages: int = 0
    completed_pages: int = 0
    failed_pages: int = 0
    skipped_pages: int = 0
    created_at: str
    started_at: str | None = None
    completed_at: str | None = None
    error_message: str | None = None
    aggregate_summary: AggregateSummary | None = None


class BatchPagesResponse(BaseModel):
    """Paginated page-level audit results."""

    run_id: str
    total: int
    limit: int
    offset: int
    pages: list[PageAuditResult]


class BatchAuditListResponse(BaseModel):
    """Listing of recent audit runs."""

    total: int
    runs: list[BatchAuditRunResponse]
