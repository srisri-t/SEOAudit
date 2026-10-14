"""Subresource security and route interception for headless browser auditing.

Defense-in-Depth:
1. Enforces strict URL scheme checking (only 'http' and 'https' permitted, safe data:image allowed).
2. Intercepts all subresource requests (scripts, stylesheets, images, iframes, fetch/XHR, fonts).
3. Pre-flight DNS resolution and IP verification against private, loopback, link-local (cloud metadata),
   multicast, and reserved blocks using validate_and_normalize_url.
4. Aborts prohibited requests immediately via route.abort('blockedbyclient').
5. Note on TOCTOU: In standard socket environments, there remains an inherent microsecond window
   between route pre-flight DNS validation and Chromium's internal socket connection.
"""

from __future__ import annotations

import logging
from urllib.parse import urlparse

from app.core.exceptions import AuditSecurityError
from app.core.url_validator import validate_and_normalize_url

logger = logging.getLogger(__name__)

# Permitted subresource request schemes
ALLOWED_SUBRESOURCE_SCHEMES = ("http", "https")
SAFE_DATA_PREFIXES = (
    "data:image/",
    "data:font/",
    "data:application/font-",
    "data:application/x-font-",
)
MAX_BLOCKED_TRACKER_ENTRIES = 50


async def handle_subresource_route(route, blocked_tracker: list[str] | None = None) -> None:
    """Evaluate an outgoing browser request against SSRF and network security rules."""
    request_url = route.request.url

    def _track(msg: str) -> None:
        if blocked_tracker is not None and len(blocked_tracker) < MAX_BLOCKED_TRACKER_ENTRIES:
            blocked_tracker.append(msg)

    # Allow safe inline data URIs (images and fonts embedded in stylesheets)
    req_lower = request_url.lower()
    if any(req_lower.startswith(prefix) for prefix in SAFE_DATA_PREFIXES):
        await route.continue_()
        return

    # Check scheme
    parsed = urlparse(request_url)
    scheme = (parsed.scheme or "").lower()

    if scheme not in ALLOWED_SUBRESOURCE_SCHEMES:
        logger.warning("Blocked subresource with prohibited scheme '%s': %s", scheme, request_url)
        _track(f"Blocked prohibited scheme '{scheme}': {request_url}")
        await route.abort("blockedbyclient")
        return

    # Validate destination against SSRF & prohibited IP/host blocks
    try:
        validate_and_normalize_url(request_url, resolve_dns=True)
    except AuditSecurityError as err:
        logger.warning("SSRF subresource blocked: %s (%s)", request_url, err.message)
        _track(f"SSRF blocked subresource '{request_url}': {err.message}")
        await route.abort("blockedbyclient")
        return
    except Exception as err:
        logger.warning("Malformed subresource URL blocked: %s (%s)", request_url, err)
        _track(f"Blocked malformed subresource '{request_url}': {err}")
        await route.abort("blockedbyclient")
        return

    # Valid public target
    await route.continue_()
