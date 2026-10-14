"""Audit Runner Coordinator for executing single-URL SEO audits."""

from __future__ import annotations

from app.engine.extractor import extract_seo_metadata
from app.engine.fetcher import safe_fetch_url
from app.engine.rules import evaluate_all_rules
from app.models.audit import (
    AuditResponse,
    AuditSummary,
    Finding,
    RedirectHopModel,
)


async def run_single_url_audit(target_url: str, client=None) -> AuditResponse:
    """Execute a complete single-URL technical SEO audit.

    Args:
        target_url: The submitted web page URL.
        client: Optional pre-configured HTTPX client for testing.

    Returns:
        Structured AuditResponse model.
    """
    # 1. Fetch URL safely (with SSRF check and redirect validation)
    fetch_res = await safe_fetch_url(target_url=target_url, client=client)

    # 2. Extract SEO Metadata
    metadata = extract_seo_metadata(fetch_res)

    # 3. Evaluate Audit Rules
    findings: list[Finding] = evaluate_all_rules(fetch_res, metadata)

    # 4. Calculate Summary
    passed_cnt = sum(1 for f in findings if f.status == "pass")
    warning_cnt = sum(1 for f in findings if f.status == "warning")
    issue_cnt = sum(1 for f in findings if f.status == "issue")
    error_cnt = sum(1 for f in findings if f.status == "error")

    summary = AuditSummary(
        total_checks=len(findings),
        passed=passed_cnt,
        warnings=warning_cnt,
        issues=issue_cnt,
        errors=error_cnt,
    )

    # 5. Format redirect hops
    hops = [
        RedirectHopModel(
            url=h.url,
            status_code=h.status_code,
            location=h.location,
        )
        for h in fetch_res.redirect_chain
    ]

    return AuditResponse(
        url=target_url,
        final_url=fetch_res.final_url,
        status_code=fetch_res.status_code,
        status_text=fetch_res.status_text,
        content_type=fetch_res.content_type,
        fetch_duration_ms=fetch_res.fetch_duration_ms,
        redirect_count=fetch_res.redirect_count,
        redirect_chain=hops,
        title=metadata.title.text,
        meta_description=metadata.description.text,
        canonical_url=metadata.canonical.resolved_url,
        meta_robots=metadata.robots.meta_directives,
        x_robots_tag=metadata.robots.x_robots_directives,
        summary=summary,
        findings=findings,
    )
