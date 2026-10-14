"""Metadata drift comparison and dynamic SEO rule evaluation."""

from __future__ import annotations

from app.engine.extractor import ExtractedMetadata
from app.models.audit import BrowserAuditResult, Finding


def compare_server_and_rendered_metadata(
    server_meta: ExtractedMetadata,
    rendered_result: BrowserAuditResult,
) -> tuple[bool, list[str]]:
    """Compare server-delivered static metadata with rendered DOM metadata.

    Returns:
        (hydration_mismatch: bool, mismatch_details: list[str])
    """
    details: list[str] = []

    # 1. Compare Title
    server_title = (server_meta.title.text or "").strip()
    rendered_title = (rendered_result.rendered_title or "").strip()
    if server_title != rendered_title:
        details.append(
            f"Title discrepancy: Server delivered '{server_title or '(none)'}', "
            f"but rendered DOM contains '{rendered_title or '(none)'}'."
        )

    # 2. Compare Meta Description
    server_desc = (server_meta.description.text or "").strip()
    rendered_desc = (rendered_result.rendered_meta_description or "").strip()
    if server_desc != rendered_desc:
        details.append(
            f"Meta description discrepancy: Server delivered '{server_desc or '(none)'}', "
            f"but rendered DOM contains '{rendered_desc or '(none)'}'."
        )

    # 3. Compare Canonical URL
    def _normalize_canonical(raw: str | None) -> str:
        if not raw:
            return ""
        trimmed = raw.strip().rstrip("/")
        try:
            from urllib.parse import urlparse, urlunparse
            p = urlparse(trimmed)
            if p.netloc:
                return urlunparse((p.scheme.lower(), p.netloc.lower(), p.path, p.params, p.query, ""))
        except Exception:
            pass
        return trimmed

    server_canonical = _normalize_canonical(server_meta.canonical.resolved_url)
    rendered_canonical = _normalize_canonical(rendered_result.rendered_canonical_url)
    if server_canonical != rendered_canonical:
        details.append(
            f"Canonical URL discrepancy: Server delivered '{server_canonical or '(none)'}', "
            f"but rendered DOM contains '{rendered_canonical or '(none)'}'."
        )

    # 4. Compare Meta Robots Directives
    server_robots = sorted(set(d.lower() for d in server_meta.robots.meta_directives))
    rendered_robots = sorted(set(d.lower() for d in rendered_result.rendered_meta_robots))
    if server_robots != rendered_robots:
        details.append(
            f"Robots directives discrepancy: Server delivered {server_robots or 'none'}, "
            f"but rendered DOM contains {rendered_robots or 'none'}."
        )

    mismatch = len(details) > 0
    return mismatch, details


def evaluate_browser_rules(
    rendered_result: BrowserAuditResult,
) -> list[Finding]:
    """Evaluate diagnostic browser rules for console health and hydration drift."""
    findings: list[Finding] = []

    # Rule 1: Browser Console & JS Health
    has_exceptions = len(rendered_result.page_exceptions) > 0
    has_console_errors = len(rendered_result.console_errors) > 0
    has_failed_subresources = len(rendered_result.failed_subresources) > 0

    if has_exceptions:
        sample_err = rendered_result.page_exceptions[0].message
        findings.append(
            Finding(
                rule_id="browser-console-health",
                title="Browser Console & JavaScript Health",
                status="issue",
                explanation=(
                    f"Encountered {len(rendered_result.page_exceptions)} uncaught JavaScript exception(s) "
                    f"during page rendering. Client-side features or hydration may fail."
                ),
                recommendation="Investigate and fix unhandled runtime script exceptions in the application code.",
                evidence=f"Exception: {sample_err}",
            )
        )
    elif has_console_errors:
        sample_log = rendered_result.console_errors[0].text
        findings.append(
            Finding(
                rule_id="browser-console-health",
                title="Browser Console & JavaScript Health",
                status="warning",
                explanation=f"Captured {len(rendered_result.console_errors)} console error message(s) during page rendering.",
                recommendation="Inspect browser console logs and resolve client-side JavaScript errors.",
                evidence=f"Console error: {sample_log}",
            )
        )
    elif has_failed_subresources:
        sample_sub = rendered_result.failed_subresources[0]
        findings.append(
            Finding(
                rule_id="browser-console-health",
                title="Browser Console & JavaScript Health",
                status="warning",
                explanation=f"{len(rendered_result.failed_subresources)} subresource(s) failed to load.",
                recommendation="Verify all script, stylesheet, and image links respond with HTTP 200.",
                evidence=f"Failed: {sample_sub}",
            )
        )
    else:
        findings.append(
            Finding(
                rule_id="browser-console-health",
                title="Browser Console & JavaScript Health",
                status="pass",
                explanation="Page rendered without console errors, runtime script exceptions, or failed subresources.",
                evidence="0 console errors, 0 exceptions",
            )
        )

    # Rule 2: Hydration Drift & Metadata Consistency
    if rendered_result.hydration_mismatch:
        # Check if client added a noindex directive that wasn't there originally
        client_added_noindex = "noindex" in [d.lower() for d in rendered_result.rendered_meta_robots]
        status = "issue" if client_added_noindex else "warning"

        summary_diff = "; ".join(rendered_result.mismatch_details)
        findings.append(
            Finding(
                rule_id="browser-hydration-drift",
                title="Server vs Rendered Metadata Consistency",
                status=status,
                explanation=(
                    f"Detected differences between server-delivered HTML and client-rendered DOM: {summary_diff}"
                ),
                recommendation=(
                    "Ensure crucial SEO metadata (title, description, canonical, robots) is rendered identically "
                    "in server HTML to avoid search engine indexation discrepancies."
                ),
                evidence=summary_diff,
            )
        )
    else:
        findings.append(
            Finding(
                rule_id="browser-hydration-drift",
                title="Server vs Rendered Metadata Consistency",
                status="pass",
                explanation="Rendered DOM metadata matches server-delivered static HTML without hydration drift.",
                evidence="Title, description, canonical, and robots directives match across server and browser.",
            )
        )

    return findings
