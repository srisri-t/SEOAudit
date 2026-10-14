"""Unit tests for Playwright browser subresource SSRF route interception."""

from __future__ import annotations

import socket
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.engine.browser.security import handle_subresource_route


def mock_public_dns(*args, **kwargs):
    return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 80))]


class TestSubresourceRouteSecurity:
    """Tests verifying subresource interception aborts SSRF and unsafe schemes."""

    @pytest.mark.anyio
    async def test_allow_safe_data_image(self):
        """Safe inline data URI images are allowed to render."""
        mock_route = AsyncMock()
        mock_route.request.url = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="

        tracker = []
        await handle_subresource_route(mock_route, blocked_tracker=tracker)

        mock_route.continue_.assert_awaited_once()
        mock_route.abort.assert_not_called()
        assert len(tracker) == 0

    @pytest.mark.anyio
    async def test_block_prohibited_schemes(self):
        """Prohibited schemes such as file://, chrome://, and javascript: are aborted."""
        prohibited_urls = [
            "file:///C:/Windows/System32/drivers/etc/hosts",
            "chrome://settings",
            "javascript:alert(1)",
            "gopher://example.com",
            "about:blank",
        ]

        for url in prohibited_urls:
            mock_route = AsyncMock()
            mock_route.request.url = url
            tracker = []

            await handle_subresource_route(mock_route, blocked_tracker=tracker)

            mock_route.abort.assert_awaited_once_with("blockedbyclient")
            mock_route.continue_.assert_not_called()
            assert len(tracker) == 1
            assert "prohibited scheme" in tracker[0].lower()

    @pytest.mark.anyio
    async def test_block_private_and_cloud_metadata_subresources(self):
        """Subresources targeting private IPs, loopback, or cloud metadata are aborted."""
        ssrf_targets = [
            "http://169.254.169.254/latest/meta-data/",
            "http://127.0.0.1:8000/api/internal",
            "http://localhost:3000/bundle.js",
            "http://10.0.0.1/admin/config.json",
            "http://192.168.1.1/router.png",
            "http://172.16.0.1/secret.css",
        ]

        for url in ssrf_targets:
            mock_route = AsyncMock()
            mock_route.request.url = url
            tracker = []

            await handle_subresource_route(mock_route, blocked_tracker=tracker)

            mock_route.abort.assert_awaited_once_with("blockedbyclient")
            mock_route.continue_.assert_not_called()
            assert len(tracker) == 1
            assert "ssrf blocked" in tracker[0].lower()

    @pytest.mark.anyio
    async def test_allow_valid_public_subresources(self):
        """Legitimate public HTTP and HTTPS subresources are continued."""
        mock_route = AsyncMock()
        mock_route.request.url = "https://fonts.googleapis.com/css2?family=Inter"

        tracker = []
        with patch("socket.getaddrinfo", side_effect=mock_public_dns):
            await handle_subresource_route(mock_route, blocked_tracker=tracker)

        mock_route.continue_.assert_awaited_once()
        mock_route.abort.assert_not_called()
        assert len(tracker) == 0

    @pytest.mark.anyio
    async def test_block_ipv6_and_mapped_subresources(self):
        """IPv6 loopback, ULA, and IPv4-mapped IPv6 subresources are blocked."""
        ipv6_targets = [
            "http://[::1]:8080/metrics",
            "http://[fc00::1]/admin",
            "http://[fe80::1]/config",
            "http://[::ffff:127.0.0.1]/secret",
            "http://[::ffff:192.168.1.1]/gateway",
            "http://[::ffff:169.254.169.254]/meta",
        ]

        for url in ipv6_targets:
            mock_route = AsyncMock()
            mock_route.request.url = url
            tracker = []

            await handle_subresource_route(mock_route, blocked_tracker=tracker)

            mock_route.abort.assert_awaited_once_with("blockedbyclient")
            mock_route.continue_.assert_not_called()
            assert len(tracker) == 1
            assert "ssrf blocked" in tracker[0].lower()

    @pytest.mark.anyio
    async def test_allow_safe_font_data_uri_and_block_html_data_uri(self):
        """Font data URIs are allowed, while text/html data URIs are blocked."""
        font_url = "data:font/woff2;base64,d09GMgABAAAAAA..."
        mock_route_font = AsyncMock()
        mock_route_font.request.url = font_url
        await handle_subresource_route(mock_route_font)
        mock_route_font.continue_.assert_awaited_once()

        html_data_url = "data:text/html,<script>alert(1)</script>"
        mock_route_html = AsyncMock()
        mock_route_html.request.url = html_data_url
        tracker = []
        await handle_subresource_route(mock_route_html, blocked_tracker=tracker)
        mock_route_html.abort.assert_awaited_once_with("blockedbyclient")
        assert len(tracker) == 1
