import socket
from unittest.mock import patch

import httpx
import pytest

from app.core.exceptions import (
    AuditFetchError,
    AuditSecurityError,
    ResponseTooLargeError,
)
from app.engine.fetcher import safe_fetch_url


# Helper to mock public DNS for test domains
def mock_public_dns(*args, **kwargs):
    return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 80))]


@pytest.mark.anyio
async def test_fetch_html_success():
    """Verify normal 200 OK HTML fetch."""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-type": "text/html; charset=utf-8"},
            html="<html><head><title>Test Page</title></head><body><h1>Hello</h1></body></html>",
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        with patch("socket.getaddrinfo", side_effect=mock_public_dns):
            res = await safe_fetch_url("https://example.com/test", client=client)

    assert res.status_code == 200
    assert res.is_html is True
    assert "Test Page" in res.body
    assert res.redirect_count == 0


@pytest.mark.anyio
async def test_fetch_single_redirect_to_allowed_destination():
    """Verify 301 redirect is followed to valid public destination."""
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/old":
            return httpx.Response(301, headers={"location": "https://example.com/new"})
        return httpx.Response(
            200,
            headers={"content-type": "text/html"},
            html="<html><head><title>New Destination</title></head></html>",
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        with patch("socket.getaddrinfo", side_effect=mock_public_dns):
            res = await safe_fetch_url("https://example.com/old", client=client)

    assert res.status_code == 200
    assert res.redirect_count == 1
    assert res.final_url == "https://example.com/new"
    assert len(res.redirect_chain) == 1
    assert res.redirect_chain[0].status_code == 301


@pytest.mark.anyio
async def test_fetch_redirect_to_prohibited_destination_blocked():
    """Verify SSRF via redirect (e.g. redirecting to AWS metadata or loopback) is blocked."""
    def handler(request: httpx.Request) -> httpx.Response:
        # Attacker tries to redirect crawler to cloud metadata service
        return httpx.Response(302, headers={"location": "http://169.254.169.254/latest/meta-data/"})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        with patch("socket.getaddrinfo", side_effect=mock_public_dns):
            with pytest.raises(AuditSecurityError, match="Prohibited IP address destination"):
                await safe_fetch_url("https://example.com/redirect-to-metadata", client=client)


@pytest.mark.anyio
async def test_fetch_redirect_limit_exceeded():
    """Verify redirect loop / excessive redirects fail after max_redirects limit."""
    def handler(request: httpx.Request) -> httpx.Response:
        # Endless loop
        return httpx.Response(302, headers={"location": f"https://example.com/loop-{request.url.path}"})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        with patch("socket.getaddrinfo", side_effect=mock_public_dns):
            with pytest.raises(AuditFetchError, match="Exceeded maximum allowed redirect limit"):
                await safe_fetch_url("https://example.com/start", max_redirects=3, client=client)


@pytest.mark.anyio
async def test_fetch_oversized_response_rejected():
    """Verify response exceeding max_body_bytes raises ResponseTooLargeError."""
    large_payload = b"X" * 1000

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, headers={"content-type": "text/html"}, content=large_payload)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        with patch("socket.getaddrinfo", side_effect=mock_public_dns):
            with pytest.raises(ResponseTooLargeError, match="exceeded maximum allowed limit"):
                await safe_fetch_url("https://example.com/large", max_body_bytes=500, client=client)


@pytest.mark.anyio
async def test_fetch_non_html_response():
    """Verify non-HTML response (e.g. PDF) is captured without crashing."""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-type": "application/pdf"},
            content=b"%PDF-1.4 ...",
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        with patch("socket.getaddrinfo", side_effect=mock_public_dns):
            res = await safe_fetch_url("https://example.com/document.pdf", client=client)

    assert res.status_code == 200
    assert res.is_html is False
    assert res.content_type == "application/pdf"


@pytest.mark.anyio
async def test_fetch_http_404_and_500():
    """Verify 404 and 500 error pages are captured with their status codes."""
    def handler_404(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, headers={"content-type": "text/html"}, html="<h1>Not Found</h1>")

    transport = httpx.MockTransport(handler_404)
    async with httpx.AsyncClient(transport=transport) as client:
        with patch("socket.getaddrinfo", side_effect=mock_public_dns):
            res = await safe_fetch_url("https://example.com/missing", client=client)

    assert res.status_code == 404
    assert res.is_html is True


@pytest.mark.anyio
async def test_fetch_connection_timeout():
    """Verify connect timeout raises AuditFetchError."""
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("Connection timed out")

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        with patch("socket.getaddrinfo", side_effect=mock_public_dns):
            with pytest.raises(AuditFetchError, match="Connection timed out"):
                await safe_fetch_url("https://example.com/timeout", client=client)


@pytest.mark.anyio
async def test_fetch_prohibited_custom_headers_rejected():
    """Verify sensitive auth and cookie headers in custom_headers are rejected."""
    with patch("socket.getaddrinfo", side_effect=mock_public_dns):
        with pytest.raises(AuditSecurityError, match="credentials, auth tokens, and cookies cannot be forwarded"):
            await safe_fetch_url(
                "https://example.com/test",
                custom_headers={"Authorization": "Bearer secret-token"},
            )

        with pytest.raises(AuditSecurityError, match="credentials, auth tokens, and cookies cannot be forwarded"):
            await safe_fetch_url(
                "https://example.com/test",
                custom_headers={"Cookie": "session=12345"},
            )

        with pytest.raises(AuditSecurityError, match="credentials, auth tokens, and cookies cannot be forwarded"):
            await safe_fetch_url(
                "https://example.com/test",
                custom_headers={"X-API-Key": "super-secret-key"},
            )


@pytest.mark.anyio
async def test_fetch_allowed_custom_headers():
    """Verify safe custom headers (e.g. Accept) are passed to outgoing request."""
    captured_accept = None

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal captured_accept
        captured_accept = request.headers.get("accept")
        return httpx.Response(200, headers={"content-type": "application/xml"}, text="<xml/>")

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        with patch("socket.getaddrinfo", side_effect=mock_public_dns):
            res = await safe_fetch_url(
                "https://example.com/sitemap.xml",
                client=client,
                custom_headers={"Accept": "application/xml"},
            )

    assert res.status_code == 200
    assert captured_accept == "application/xml"

