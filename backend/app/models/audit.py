"""Pydantic schemas and models for the Technical SEO Audit API."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field

FindingStatus = Literal["pass", "warning", "issue", "error"]


class AuditRequest(BaseModel):
    """Request payload for executing a single-URL SEO audit."""

    url: str = Field(
        ...,
        description="Target web page URL to audit (must be an HTTP or HTTPS scheme)",
        examples=["https://www.holyspace.live"],
    )
    include_browser: bool = Field(
        default=False,
        description="Whether to perform secondary browser rendering and hydration checks",
    )


class Finding(BaseModel):
    """An individual SEO rule finding or diagnostic verification."""

    rule_id: str = Field(
        ...,
        description="Stable identifier for the audit rule",
        examples=["page-title"],
    )
    title: str = Field(
        ...,
        description="Human-readable rule title",
        examples=["Page Title Presence & Length"],
    )
    status: FindingStatus = Field(
        ...,
        description="Audit verdict for this rule: pass, warning, issue, or error",
        examples=["pass"],
    )
    explanation: str = Field(
        ...,
        description="Concise, factual explanation of the finding",
        examples=["Page title is present and within recommended length (34 chars)."],
    )
    recommendation: str | None = Field(
        default=None,
        description="Evidence-based recommended action when non-passing, or null if passed",
        examples=["Ensure the title accurately summarizes page content in 15-65 characters."],
    )
    evidence: str | None = Field(
        default=None,
        description="Sanitized evidence string captured from the page or HTTP response",
        examples=["Holy Space - Christian Music Platform"],
    )


class AuditSummary(BaseModel):
    """Aggregated finding counts for the audit run."""

    total_checks: int = Field(..., description="Total count of evaluated audit rules")
    passed: int = Field(..., description="Count of checks that passed successfully")
    warnings: int = Field(..., description="Count of checks with advisory warnings")
    issues: int = Field(..., description="Count of confirmed SEO issues or missing required metadata")
    errors: int = Field(..., description="Count of execution, network, or extraction errors")


class RedirectHopModel(BaseModel):
    """Metadata describing a single redirect hop in the navigation chain."""

    url: str = Field(..., description="Origin URL of this hop")
    status_code: int = Field(..., description="HTTP redirect status code (e.g. 301, 302)")
    location: str = Field(..., description="Target destination specified in Location header")


class ConsoleMessage(BaseModel):
    """A captured browser console message."""

    level: str = Field(..., description="Message level (error, warning, info, log)")
    text: str = Field(..., description="Console log message body")
    location: str | None = Field(default=None, description="Script source URL or line number if available")


class PageException(BaseModel):
    """An unhandled runtime JavaScript error captured on the page."""

    message: str = Field(..., description="Exception message")
    stack: str | None = Field(default=None, description="Call stack if available")


class BrowserAuditResult(BaseModel):
    """Diagnostic data and metadata captured from headless browser rendering."""

    final_rendered_url: str = Field(..., description="Final URL after client-side navigation or SPA routing")
    browser_status_code: int | None = Field(default=None, description="HTTP status code reported by browser navigation response")
    rendered_title: str | None = Field(default=None, description="DOM title after rendering")
    rendered_meta_description: str | None = Field(default=None, description="DOM meta description after rendering")
    rendered_canonical_url: str | None = Field(default=None, description="DOM canonical URL after rendering")
    rendered_meta_robots: list[str] = Field(default_factory=list, description="Directives from DOM <meta name='robots'> after rendering")
    console_errors: list[ConsoleMessage] = Field(default_factory=list, description="Browser console error messages captured")
    page_exceptions: list[PageException] = Field(default_factory=list, description="Unhandled page JavaScript exceptions captured")
    failed_subresources: list[str] = Field(default_factory=list, description="Subresources that failed to load (e.g. 404s, network failures)")
    render_duration_ms: int = Field(default=0, description="Elapsed browser rendering duration in milliseconds")
    hydration_mismatch: bool = Field(default=False, description="True if server HTML and client-rendered DOM metadata diverge")
    mismatch_details: list[str] = Field(default_factory=list, description="Specific metadata fields that differ between server and client")


class AuditResponse(BaseModel):
    """Complete structured response schema for a single-URL audit."""

    url: str = Field(..., description="The initially submitted target URL")
    final_url: str = Field(..., description="Final URL after following safe redirects")
    status_code: int = Field(..., description="HTTP status code returned by final destination")
    status_text: str = Field(..., description="HTTP status reason phrase")
    content_type: str = Field(..., description="MIME content type from response header")
    fetch_duration_ms: int = Field(..., description="Total elapsed fetch time in milliseconds")
    redirect_count: int = Field(..., description="Number of redirect hops followed")
    redirect_chain: list[RedirectHopModel] = Field(
        default_factory=list,
        description="Detailed sequence of followed redirect hops",
    )
    title: str | None = Field(default=None, description="Extracted HTML page title")
    meta_description: str | None = Field(default=None, description="Extracted meta description content")
    canonical_url: str | None = Field(default=None, description="Extracted canonical URL")
    meta_robots: list[str] = Field(default_factory=list, description="Directives from <meta name='robots'>")
    x_robots_tag: list[str] = Field(default_factory=list, description="Directives from X-Robots-Tag header")
    summary: AuditSummary = Field(..., description="Summary counts of check results")
    findings: list[Finding] = Field(..., description="List of individual rule evaluation results")
    outgoing_links: list[str] = Field(
        default_factory=list,
        description="Extracted outgoing link URLs from page HTML",
    )
    browser_audit: BrowserAuditResult | None = Field(
        default=None,
        description="Optional browser rendering and console diagnostics (null if include_browser was false or browser unavailable)",
    )
    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
        description="UTC completion timestamp in ISO 8601 format",
    )
