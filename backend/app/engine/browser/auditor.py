"""Browser audit runner for executing headless Chromium rendering, DOM extraction, and diagnostics."""

from __future__ import annotations

import logging
import time

from app.core.exceptions import (
    AuditSecurityError,
    BrowserNavigationError,
    BrowserUnavailableError,
)
from app.core.url_validator import validate_and_normalize_url
from app.engine.browser.client import browser_session
from app.engine.browser.collector import BrowserCollector
from app.engine.browser.comparison import compare_server_and_rendered_metadata
from app.engine.browser.security import handle_subresource_route
from app.engine.extractor import ExtractedMetadata
from app.models.audit import BrowserAuditResult

logger = logging.getLogger(__name__)

DEFAULT_BROWSER_TIMEOUT_SECONDS = 15.0


async def run_browser_audit(
    target_url: str,
    server_metadata: ExtractedMetadata | None = None,
    timeout_seconds: float = DEFAULT_BROWSER_TIMEOUT_SECONDS,
    context_override=None,
) -> BrowserAuditResult:
    """Execute a headless browser audit for a validated target URL.

    Args:
        target_url: The target web page URL.
        server_metadata: Optional static metadata from HTTPX fetch for drift comparison.
        timeout_seconds: Navigation timeout threshold in seconds.
        context_override: Optional pre-configured browser context for unit testing.

    Returns:
        BrowserAuditResult with rendered metadata, console errors, and comparison flags.

    Raises:
        AuditSecurityError: If target URL or subresource resolves to a prohibited destination.
        BrowserUnavailableError: If Chromium runtime is missing or cannot launch.
        BrowserNavigationError: If page navigation fails or times out.
    """
    # 1. Pre-flight SSRF and syntax validation
    validated_url = validate_and_normalize_url(target_url, resolve_dns=True)
    start_time = time.perf_counter()

    async def _execute_with_context(ctx) -> BrowserAuditResult:
        # 2. Setup Subresource Security via Route Interception
        blocked_security_tracker: list[str] = []
        await ctx.route("**/*", lambda route: handle_subresource_route(route, blocked_security_tracker))

        # 3. Create isolated Page & attach diagnostic collectors
        page = await ctx.new_page()
        collector = BrowserCollector()
        collector.attach_to_page(page)

        # Prevent popups or additional tabs from bypassing isolation or exhausting memory
        page.on("popup", lambda popup: asyncio.create_task(popup.close()))

        # Guard against client-side JavaScript frame navigations to prohibited destinations
        def _on_frame_navigated(frame):
            if frame == page.main_frame and frame.url not in ("about:blank", ""):
                try:
                    validate_and_normalize_url(frame.url, resolve_dns=True)
                except AuditSecurityError as ssrf_err:
                    logger.warning("SSRF frame navigation blocked: %s (%s)", frame.url, ssrf_err.message)
                    asyncio.create_task(page.close())

        page.on("framenavigated", _on_frame_navigated)

        # 4. Navigate with bounded timeout
        timeout_ms = int(timeout_seconds * 1000)
        try:
            response = await page.goto(
                validated_url,
                timeout=timeout_ms,
                wait_until="domcontentloaded",
            )
        except Exception as err:
            err_str = str(err)
            if "Timeout" in err_str or "timed out" in err_str:
                raise BrowserNavigationError(
                    f"Browser navigation timed out after {timeout_seconds}s for {validated_url}.",
                    error_type="TIMEOUT",
                ) from err
            raise BrowserNavigationError(
                f"Browser navigation failed for {validated_url}: {err}",
                error_type="NAVIGATION_FAILED",
            ) from err

        # 5. Allow brief hydration window for dynamic client frameworks
        try:
            await page.wait_for_load_state("networkidle", timeout=2500)
        except Exception:
            # Non-fatal: background requests or streaming long-polling
            pass

        # 6. Extract rendered DOM metadata
        dom_meta = await page.evaluate(
            """() => {
                const title = document.title || "";
                const descEl = document.querySelector('meta[name="description"]');
                const description = descEl ? descEl.getAttribute("content") : null;
                const canonEl = document.querySelector('link[rel="canonical"]');
                const canonical = canonEl ? canonEl.getAttribute("href") : null;
                const robotsEls = document.querySelectorAll('meta[name="robots"]');
                const robots = [];
                robotsEls.forEach(el => {
                    const content = el.getAttribute("content");
                    if (content) {
                        content.split(",").forEach(part => {
                            const trimmed = part.trim();
                            if (trimmed) robots.push(trimmed);
                        });
                    }
                });
                return {
                    title: title.trim(),
                    description: description ? description.trim() : null,
                    canonical: canonical ? canonical.trim() : null,
                    robots: robots,
                };
            }"""
        )

        render_duration_ms = int((time.perf_counter() - start_time) * 1000)
        browser_status = response.status if response else None

        result = BrowserAuditResult(
            final_rendered_url=page.url,
            browser_status_code=browser_status,
            rendered_title=dom_meta.get("title") or None,
            rendered_meta_description=dom_meta.get("description") or None,
            rendered_canonical_url=dom_meta.get("canonical") or None,
            rendered_meta_robots=dom_meta.get("robots") or [],
            console_errors=collector.console_errors,
            page_exceptions=collector.page_exceptions,
            failed_subresources=collector.failed_subresources,
            render_duration_ms=render_duration_ms,
        )

        # 7. Metadata drift comparison if server metadata is available
        if server_metadata is not None:
            mismatch, details = compare_server_and_rendered_metadata(server_metadata, result)
            result.hydration_mismatch = mismatch
            result.mismatch_details = details

        return result

    # Run inside managed session or provided override context
    if context_override is not None:
        return await _execute_with_context(context_override)

    async with browser_session() as managed_context:
        return await _execute_with_context(managed_context)
