"""Safe HTTP Fetcher using HTTPX with per-hop SSRF validation and response limits."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from urllib.parse import urljoin

import httpx

from app.core.exceptions import (
    AuditFetchError,
    AuditSecurityError,
    ResponseTooLargeError,
)
from app.core.url_validator import validate_and_normalize_url

DEFAULT_USER_AGENT = "UniversalSEOPlatform/0.1.0 (+http://localhost/bot-info)"
DEFAULT_MAX_REDIRECTS = 5
DEFAULT_MAX_BODY_BYTES = 2 * 1024 * 1024  # 2 Megabytes
DEFAULT_TIMEOUT_CONNECT = 5.0
DEFAULT_TIMEOUT_READ = 10.0


@dataclass
class RedirectHop:
    url: str
    status_code: int
    location: str


@dataclass
class FetchResult:
    initial_url: str
    final_url: str
    status_code: int
    status_text: str
    headers: dict[str, str]
    body: str
    raw_bytes_count: int
    content_type: str
    fetch_duration_ms: int
    redirect_count: int
    redirect_chain: list[RedirectHop] = field(default_factory=list)
    is_html: bool = False
    error: str | None = None


PROHIBITED_REQUEST_HEADERS = {
    "authorization",
    "cookie",
    "cookie2",
    "set-cookie",
    "proxy-authorization",
    "proxy-authenticate",
    "x-csrf-token",
    "x-xsrf-token",
    "x-api-key",
    "x-auth-token",
}


async def safe_fetch_url(
    target_url: str,
    max_redirects: int = DEFAULT_MAX_REDIRECTS,
    max_body_bytes: int = DEFAULT_MAX_BODY_BYTES,
    connect_timeout: float = DEFAULT_TIMEOUT_CONNECT,
    read_timeout: float = DEFAULT_TIMEOUT_READ,
    client: httpx.AsyncClient | None = None,
    custom_headers: dict[str, str] | None = None,
) -> FetchResult:
    """Safely fetch a validated URL with per-hop redirect verification and size limits.

    Args:
        target_url: Pre-validated initial URL.
        max_redirects: Maximum allowed redirect hops before failing.
        max_body_bytes: Maximum response body size in bytes.
        connect_timeout: Connection establishment timeout in seconds.
        read_timeout: Response read timeout in seconds.
        client: Optional pre-configured HTTPX AsyncClient (useful for unit tests).
        custom_headers: Optional additional/override request headers.

    Returns:
        FetchResult containing response metadata and safely buffered body.

    Raises:
        AuditSecurityError: If any redirect destination is prohibited or credential headers passed.
        AuditFetchError: If request fails due to network, DNS, or timeout errors.
    """
    current_url = validate_and_normalize_url(target_url, resolve_dns=True)
    redirect_chain: list[RedirectHop] = []
    redirect_count = 0

    headers = {
        "User-Agent": DEFAULT_USER_AGENT,
        "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
    }
    if custom_headers:
        for k, v in custom_headers.items():
            if k.lower() in PROHIBITED_REQUEST_HEADERS:
                raise AuditSecurityError(
                    f"Custom header '{k}' is prohibited: credentials, auth tokens, and cookies cannot be forwarded.",
                    security_code="CREDENTIAL_HEADER_PROHIBITED",
                )
            headers[k] = v

    timeouts = httpx.Timeout(
        connect=connect_timeout,
        read=read_timeout,
        write=5.0,
        pool=5.0,
    )

    start_time = time.perf_counter()

    # Determine whether we manage our own client lifecycle
    manage_client = client is None

    async def _do_fetch(http_client: httpx.AsyncClient) -> FetchResult:
        nonlocal current_url, redirect_count, redirect_chain

        while True:
            try:
                # Disable automatic redirects to perform manual per-hop validation
                request = http_client.build_request(
                    "GET",
                    current_url,
                    headers=headers,
                    timeout=timeouts,
                )
                response = await http_client.send(request, stream=True)
            except httpx.ConnectTimeout as err:
                raise AuditFetchError(
                    f"Connection timed out after {connect_timeout}s connecting to {current_url}.",
                    error_type="CONNECT_TIMEOUT",
                ) from err
            except httpx.ReadTimeout as err:
                raise AuditFetchError(
                    f"Read timed out after {read_timeout}s receiving data from {current_url}.",
                    error_type="READ_TIMEOUT",
                ) from err
            except (httpx.ConnectError, httpx.NetworkError) as err:
                raise AuditFetchError(
                    f"Network connection failed for {current_url}: {err}",
                    error_type="CONNECTION_FAILED",
                ) from err
            except httpx.RequestError as err:
                raise AuditFetchError(
                    f"HTTP request error for {current_url}: {err}",
                    error_type="REQUEST_ERROR",
                ) from err

            status_code = response.status_code
            status_text = response.reason_phrase or str(status_code)

            # Check if response is a redirect
            if status_code in (301, 302, 303, 307, 308):
                location = response.headers.get("location")
                await response.aclose()

                if not location:
                    # Broken redirect without Location header
                    raise AuditFetchError(
                        f"Redirect HTTP {status_code} received without Location header at {current_url}.",
                        error_type="MISSING_LOCATION_HEADER",
                    )

                redirect_count += 1
                if redirect_count > max_redirects:
                    raise AuditFetchError(
                        f"Exceeded maximum allowed redirect limit ({max_redirects} hops).",
                        error_type="REDIRECT_LIMIT_EXCEEDED",
                    )

                next_raw_url = urljoin(current_url, location)
                # CRITICAL: Validate every redirect hop against SSRF & private IP destinations!
                validated_next_url = validate_and_normalize_url(next_raw_url, resolve_dns=True)

                redirect_chain.append(
                    RedirectHop(
                        url=current_url,
                        status_code=status_code,
                        location=location,
                    )
                )

                current_url = validated_next_url
                continue

            # Non-redirect response reached: read body stream with size limit
            content_type = response.headers.get("content-type", "").lower()
            is_html = "text/html" in content_type or "application/xhtml+xml" in content_type

            chunks: list[bytes] = []
            total_bytes = 0

            try:
                async for chunk in response.aiter_bytes():
                    total_bytes += len(chunk)
                    if total_bytes > max_body_bytes:
                        await response.aclose()
                        raise ResponseTooLargeError(max_body_bytes)
                    chunks.append(chunk)
            finally:
                await response.aclose()

            raw_bytes = b"".join(chunks)

            # Decode text safely
            encoding = response.encoding or "utf-8"
            try:
                body_text = raw_bytes.decode(encoding, errors="replace")
            except (LookupError, UnicodeDecodeError):
                body_text = raw_bytes.decode("utf-8", errors="replace")

            duration_ms = int((time.perf_counter() - start_time) * 1000)

            # Convert response headers to clean dict
            resp_headers = {k.lower(): v for k, v in response.headers.items()}

            return FetchResult(
                initial_url=target_url,
                final_url=current_url,
                status_code=status_code,
                status_text=status_text,
                headers=resp_headers,
                body=body_text,
                raw_bytes_count=total_bytes,
                content_type=content_type,
                fetch_duration_ms=duration_ms,
                redirect_count=redirect_count,
                redirect_chain=redirect_chain,
                is_html=is_html,
            )

    if manage_client:
        async with httpx.AsyncClient(verify=True, follow_redirects=False) as managed_client:
            return await _do_fetch(managed_client)
    else:
        return await _do_fetch(client)
