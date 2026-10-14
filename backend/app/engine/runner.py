import logging

from app.engine.browser.auditor import run_browser_audit
from app.engine.browser.comparison import evaluate_browser_rules
from app.engine.extractor import extract_seo_metadata
from app.engine.fetcher import safe_fetch_url
from app.engine.rules import evaluate_all_rules
from app.models.audit import (
    AuditResponse,
    AuditSummary,
    BrowserAuditResult,
    Finding,
    RedirectHopModel,
)

logger = logging.getLogger(__name__)


async def run_single_url_audit(
    target_url: str,
    include_browser: bool = False,
    client=None,
    browser_context_override=None,
) -> AuditResponse:
    """Execute a complete single-URL technical SEO audit.

    Args:
        target_url: The submitted web page URL.
        include_browser: If true, runs secondary headless browser rendering and console analysis.
        client: Optional pre-configured HTTPX client for testing.
        browser_context_override: Optional pre-configured browser context for testing.

    Returns:
        Structured AuditResponse model.
    """
    # 1. Fetch URL safely (with SSRF check and redirect validation)
    fetch_res = await safe_fetch_url(target_url=target_url, client=client)

    # 2. Extract SEO Metadata
    metadata = extract_seo_metadata(fetch_res)

    # 3. Evaluate Static Audit Rules
    findings: list[Finding] = evaluate_all_rules(fetch_res, metadata)

    # 4. Optional: Run Browser-Rendered Dynamic Audit
    browser_result: BrowserAuditResult | None = None
    if include_browser:
        try:
            browser_result = await run_browser_audit(
                target_url=fetch_res.final_url,
                server_metadata=metadata,
                context_override=browser_context_override,
            )
            # Evaluate dynamic browser rules
            browser_findings = evaluate_browser_rules(browser_result)
            findings.extend(browser_findings)
        except Exception as err:
            logger.warning("Browser audit failed for %s: %s", target_url, err)
            findings.append(
                Finding(
                    rule_id="browser-execution",
                    title="Browser Rendering Execution",
                    status="warning",
                    explanation=f"Headless browser audit could not complete: {err}",
                    recommendation="Ensure Chromium is installed ('playwright install chromium') and the URL is reachable.",
                    evidence=str(err),
                )
            )

    # 5. Calculate Summary
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

    # 6. Format redirect hops
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
        browser_audit=browser_result,
    )
