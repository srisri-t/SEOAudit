"""Sitemap Discovery and Multi-Strategy Orchestration Service."""

from __future__ import annotations

import logging
import re
import time
from urllib.parse import urljoin

import httpx

from app.core.exceptions import (
    AuditFetchError,
    AuditSecurityError,
    ResponseTooLargeError,
)
from app.core.url_validator import validate_and_normalize_url
from app.engine.fetcher import safe_fetch_url
from app.engine.sitemap.parser import parse_sitemap_xml
from app.models.sitemap import SitemapDiscoverResponse, SitemapStatus

logger = logging.getLogger(__name__)

# Defaults and safety thresholds
DEFAULT_MAX_URLS = 1000
HARD_MAX_URLS = 10000
DEFAULT_MAX_CHILD_SITEMAPS = 50
MAX_SITEMAP_BODY_BYTES = 5 * 1024 * 1024  # 5 Megabytes per sitemap file
DEFAULT_TOTAL_TIMEOUT_SECONDS = 30.0

ROBOTS_SITEMAP_REGEX = re.compile(r"^\s*sitemap\s*:\s*(\S+)", re.IGNORECASE)


async def discover_sitemaps(
    website_url: str,
    explicit_sitemap_url: str | None = None,
    max_urls: int = DEFAULT_MAX_URLS,
    max_child_sitemaps: int = DEFAULT_MAX_CHILD_SITEMAPS,
    total_timeout_seconds: float = DEFAULT_TOTAL_TIMEOUT_SECONDS,
    client: httpx.AsyncClient | None = None,
) -> SitemapDiscoverResponse:
    """Discover, fetch, and parse XML sitemaps for a website.

    Multi-Phase Discovery Process:
    1. If explicit_sitemap_url is specified:
       Validates against SSRF and fetches/parses only that sitemap.
    2. Otherwise, automatically searches:
       a. Fetches /robots.txt and parses 'Sitemap:' directives.
       b. If no sitemaps found in robots.txt, attempts standard /sitemap.xml.
    3. For sitemap index files:
       Recursively processes child sitemaps with strict depth (1 level) and count limits.
    4. Enforces strict SSRF validation for every target and child sitemap URL.

    Args:
        website_url: Base target website URL.
        explicit_sitemap_url: Optional direct sitemap URL.
        max_urls: Upper bound on extracted URLs (capped at HARD_MAX_URLS).
        max_child_sitemaps: Maximum number of child sitemaps to fetch from an index.
        total_timeout_seconds: Overall processing timeout threshold.
        client: Optional HTTPX AsyncClient for testing/mocking.

    Returns:
        SitemapDiscoverResponse with discovered sitemaps, page URLs, warnings, and status.
    """
    start_time = time.perf_counter()
    bounded_max_urls = max(1, min(max_urls, HARD_MAX_URLS))

    discovered_sitemaps: list[str] = []
    all_urls: list[str] = []
    seen_urls: set[str] = set()
    warnings: list[str] = []
    errors: list[str] = []

    # Track operational telemetry for accurate final status calculation
    has_security_block = False
    has_inaccessible_error = False
    has_not_found = False
    has_invalid_content = False

    def _elapsed_time() -> float:
        return round((time.perf_counter() - start_time) * 1000, 2)

    def _is_time_exhausted() -> bool:
        return (time.perf_counter() - start_time) >= total_timeout_seconds

    # Validate website_url base syntax
    try:
        norm_website_url = validate_and_normalize_url(website_url, resolve_dns=True)
    except AuditSecurityError as err:
        logger.warning("SSRF security rejection on initial website_url '%s': %s", website_url, err.message)
        return SitemapDiscoverResponse(
            website_url=website_url,
            sitemap_status=SitemapStatus.BLOCKED.value,
            discovered_sitemaps=[],
            discovered_url_count=0,
            urls=[],
            warnings=[],
            errors=[f"Security validation blocked destination: {err.message}"],
            processing_duration_ms=_elapsed_time(),
        )
    except Exception as err:
        return SitemapDiscoverResponse(
            website_url=website_url,
            sitemap_status=SitemapStatus.INVALID.value,
            discovered_sitemaps=[],
            discovered_url_count=0,
            urls=[],
            warnings=[],
            errors=[f"Invalid website URL provided: {err}"],
            processing_duration_ms=_elapsed_time(),
        )

    # Manage HTTPX client lifecycle if not provided
    manage_client = client is None
    async with httpx.AsyncClient(verify=True, follow_redirects=False) if manage_client else client as http_client:

        # -------------------------------------------------------------
        # Helper: Fetch and parse a single sitemap URL (index or urlset)
        # -------------------------------------------------------------
        async def _process_sitemap_target(
            target_sitemap_url: str,
            current_depth: int = 0,
        ) -> None:
            nonlocal has_security_block, has_inaccessible_error, has_not_found, has_invalid_content

            if len(all_urls) >= bounded_max_urls or _is_time_exhausted():
                return

            # SSRF verification on this specific sitemap target
            try:
                validated_sitemap_url = validate_and_normalize_url(target_sitemap_url, resolve_dns=True)
            except AuditSecurityError as err:
                logger.warning("Child sitemap SSRF blocked: %s (%s)", target_sitemap_url, err.message)
                has_security_block = True
                errors.append(f"Security validation blocked sitemap '{target_sitemap_url}': {err.message}")
                return
            except Exception as err:
                errors.append(f"Malformed sitemap URL '{target_sitemap_url}': {err}")
                return

            # Fetch sitemap with timeouts dynamically bounded to the remaining overall budget
            remaining_seconds = max(0.5, total_timeout_seconds - (time.perf_counter() - start_time))
            effective_connect_timeout = min(5.0, remaining_seconds)
            effective_read_timeout = min(10.0, remaining_seconds)

            try:
                fetch_res = await safe_fetch_url(
                    target_url=validated_sitemap_url,
                    max_body_bytes=MAX_SITEMAP_BODY_BYTES,
                    connect_timeout=effective_connect_timeout,
                    read_timeout=effective_read_timeout,
                    client=http_client,
                    custom_headers={"Accept": "application/xml, text/xml, application/x-xml, */*;q=0.8"},
                )
            except AuditSecurityError as err:
                has_security_block = True
                errors.append(f"Security validation blocked sitemap fetch for '{validated_sitemap_url}': {err.message}")
                return
            except ResponseTooLargeError as err:
                has_invalid_content = True
                errors.append(f"Sitemap file '{validated_sitemap_url}' exceeded maximum size: {err.message}")
                return
            except AuditFetchError as err:
                has_inaccessible_error = True
                errors.append(f"Failed to fetch sitemap '{validated_sitemap_url}': {err.message}")
                return
            except Exception as err:
                has_inaccessible_error = True
                errors.append(f"Unexpected error fetching sitemap '{validated_sitemap_url}': {err}")
                return

            # Evaluate HTTP status code
            if fetch_res.status_code == 404 or fetch_res.status_code == 410:
                has_not_found = True
                errors.append(f"Sitemap returned HTTP {fetch_res.status_code} Not Found: {validated_sitemap_url}")
                return
            elif fetch_res.status_code >= 400:
                has_inaccessible_error = True
                errors.append(f"Sitemap returned HTTP error {fetch_res.status_code} ({fetch_res.status_text}): {validated_sitemap_url}")
                return

            # Parse XML
            parsed = parse_sitemap_xml(
                xml_content=fetch_res.body,
                max_urls=bounded_max_urls - len(all_urls),
            )

            if parsed.warnings:
                warnings.extend(parsed.warnings)

            if parsed.errors:
                has_invalid_content = True
                for err in parsed.errors:
                    errors.append(f"Error in '{validated_sitemap_url}': {err}")
                return

            # Record successfully fetched and validated sitemap
            if validated_sitemap_url not in discovered_sitemaps:
                discovered_sitemaps.append(validated_sitemap_url)

            # Handle Sitemap Index vs Standard URL Set
            if parsed.is_index:
                if current_depth >= 1:
                    warnings.append(
                        f"Nested sitemap index '{validated_sitemap_url}' rejected: recursion limit (1 level) reached."
                    )
                    return

                # Process child sitemaps up to max_child_sitemaps limit
                children_to_process = parsed.child_sitemaps[:max_child_sitemaps]
                if len(parsed.child_sitemaps) > max_child_sitemaps:
                    warnings.append(
                        f"Sitemap index contained {len(parsed.child_sitemaps)} child sitemaps; "
                        f"limited to first {max_child_sitemaps}."
                    )

                for child_url in children_to_process:
                    if len(all_urls) >= bounded_max_urls or _is_time_exhausted():
                        break
                    await _process_sitemap_target(child_url, current_depth=current_depth + 1)
            else:
                # Standard URL Set
                for page_url in parsed.urls:
                    if len(all_urls) >= bounded_max_urls:
                        break
                    if page_url not in seen_urls:
                        seen_urls.add(page_url)
                        all_urls.append(page_url)

        # -------------------------------------------------------------
        # Path 1: User provided an explicit sitemap URL
        # -------------------------------------------------------------
        if explicit_sitemap_url and explicit_sitemap_url.strip():
            target = explicit_sitemap_url.strip()
            await _process_sitemap_target(target, current_depth=0)

        # -------------------------------------------------------------
        # Path 2: Auto-discovery via robots.txt and standard /sitemap.xml
        # -------------------------------------------------------------
        else:
            robots_sitemaps: list[str] = []

            # Step A: Check robots.txt
            robots_url = urljoin(norm_website_url, "/robots.txt")
            remaining_seconds = max(0.5, total_timeout_seconds - (time.perf_counter() - start_time))
            robots_connect_timeout = min(5.0, remaining_seconds)
            robots_read_timeout = min(10.0, remaining_seconds)
            try:
                robots_res = await safe_fetch_url(
                    target_url=robots_url,
                    max_body_bytes=512 * 1024,  # robots.txt is typically small
                    connect_timeout=robots_connect_timeout,
                    read_timeout=robots_read_timeout,
                    client=http_client,
                    custom_headers={"Accept": "text/plain, */*"},
                )
                if robots_res.status_code == 200 and robots_res.body:
                    for line in robots_res.body.splitlines():
                        match = ROBOTS_SITEMAP_REGEX.match(line)
                        if match:
                            raw_sitemap_candidate = match.group(1).strip()
                            # Resolve relative URL against website_url if necessary
                            full_candidate = urljoin(norm_website_url, raw_sitemap_candidate)
                            if full_candidate not in robots_sitemaps:
                                robots_sitemaps.append(full_candidate)
            except AuditSecurityError as err:
                logger.warning("SSRF blocked during robots.txt fetch: %s", err.message)
                has_security_block = True
                warnings.append(f"Security validation blocked robots.txt lookup: {err.message}")
            except Exception as err:
                # Non-fatal: missing or failing robots.txt just moves on to standard locations
                logger.debug("robots.txt lookup failed: %s", err)

            # Step B: Select candidate sitemaps
            candidate_list: list[str] = []
            if robots_sitemaps:
                candidate_list.extend(robots_sitemaps)
            else:
                # Fall back to standard /sitemap.xml location
                candidate_list.append(urljoin(norm_website_url, "/sitemap.xml"))

            # Step C: Process candidate sitemaps
            for candidate in candidate_list:
                if len(all_urls) >= bounded_max_urls or _is_time_exhausted():
                    break
                await _process_sitemap_target(candidate, current_depth=0)

    # -------------------------------------------------------------
    # Final Status Determination
    # -------------------------------------------------------------
    if all_urls:
        final_status = SitemapStatus.FOUND.value
    elif has_security_block:
        final_status = SitemapStatus.BLOCKED.value
    elif has_invalid_content:
        final_status = SitemapStatus.INVALID.value
    elif has_inaccessible_error:
        final_status = SitemapStatus.INACCESSIBLE.value
    elif has_not_found:
        final_status = SitemapStatus.NOT_FOUND.value
    elif discovered_sitemaps and not errors:
        final_status = SitemapStatus.FOUND.value
    else:
        final_status = SitemapStatus.NOT_FOUND.value

    if _is_time_exhausted():
        warnings.append(f"Processing timeout reached ({total_timeout_seconds}s); results may be partial.")

    return SitemapDiscoverResponse(
        website_url=website_url,
        sitemap_status=final_status,
        discovered_sitemaps=discovered_sitemaps,
        discovered_url_count=len(all_urls),
        urls=all_urls,
        warnings=warnings,
        errors=errors,
        processing_duration_ms=_elapsed_time(),
    )
