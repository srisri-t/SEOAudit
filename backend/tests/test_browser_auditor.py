"""Unit and integration tests for Browser Auditor, API endpoints, and runner integration."""

from __future__ import annotations

import socket
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.core.exceptions import (
    AuditSecurityError,
    BrowserNavigationError,
    BrowserUnavailableError,
)
from app.engine.browser.auditor import run_browser_audit
from app.engine.fetcher import FetchResult
from app.engine.runner import run_single_url_audit
from app.main import app
from app.models.audit import BrowserAuditResult

client = TestClient(app)


def mock_public_dns(*args, **kwargs):
    return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 80))]


def make_html_fetch_result(url: str, html_content: str) -> FetchResult:
    return FetchResult(
        initial_url=url,
        final_url=url,
        status_code=200,
        status_text="OK",
        headers={"content-type": "text/html; charset=utf-8"},
        body=html_content,
        raw_bytes_count=len(html_content.encode("utf-8")),
        content_type="text/html; charset=utf-8",
        fetch_duration_ms=45,
        redirect_count=0,
        is_html=True,
    )


class TestBrowserAuditorMocked:
    """Unit tests for run_browser_audit logic with mocked Playwright context."""

    @pytest.mark.anyio
    async def test_run_browser_audit_dom_extraction(self):
        """Verifies DOM evaluation, title, description, and canonical extraction."""
        mock_page = AsyncMock()
        mock_page.on = MagicMock()
        mock_page.url = "https://example.com/final"
        mock_response = MagicMock()
        mock_response.status = 200
        mock_page.goto.return_value = mock_response

        # Simulated DOM evaluation return value
        mock_page.evaluate.return_value = {
            "title": "Rendered Dynamic Title",
            "description": "Rendered Dynamic Meta Description",
            "canonical": "https://example.com/canonical",
            "robots": ["noindex", "nofollow"],
        }

        mock_context = AsyncMock()
        mock_context.new_page.return_value = mock_page

        with patch("socket.getaddrinfo", side_effect=mock_public_dns):
            result = await run_browser_audit(
                target_url="https://example.com/",
                context_override=mock_context,
            )

        assert result.rendered_title == "Rendered Dynamic Title"
        assert result.rendered_meta_description == "Rendered Dynamic Meta Description"
        assert result.rendered_canonical_url == "https://example.com/canonical"
        assert result.rendered_meta_robots == ["noindex", "nofollow"]
        assert result.browser_status_code == 200
        assert result.final_rendered_url == "https://example.com/final"

    @pytest.mark.anyio
    async def test_run_browser_audit_navigation_timeout(self):
        """Verifies TimeoutError in goto translates to clean BrowserNavigationError."""
        mock_page = AsyncMock()
        mock_page.on = MagicMock()
        mock_page.goto.side_effect = Exception("Timeout 15000ms exceeded")

        mock_context = AsyncMock()
        mock_context.new_page.return_value = mock_page

        with patch("socket.getaddrinfo", side_effect=mock_public_dns):
            with pytest.raises(BrowserNavigationError, match="timed out"):
                await run_browser_audit(
                    target_url="https://example.com/hang",
                    timeout_seconds=5.0,
                    context_override=mock_context,
                )

    @pytest.mark.anyio
    async def test_run_browser_audit_ssrf_destination_rejected(self):
        """Initial target pointing to prohibited IP is rejected by SSRF guard."""
        with pytest.raises(AuditSecurityError, match="Prohibited IP address destination detected"):
            await run_browser_audit(target_url="http://127.0.0.1:8000/")


class TestRunnerBrowserIntegration:
    """Tests for run_single_url_audit when include_browser=True."""

    @pytest.mark.anyio
    async def test_single_url_audit_with_browser_success(self):
        html = """<!DOCTYPE html><html><head><title>Server Title</title></head><body><h1>Hello</h1></body></html>"""
        fetch_res = make_html_fetch_result("https://example.com/", html)

        mock_browser_res = BrowserAuditResult(
            final_rendered_url="https://example.com/",
            browser_status_code=200,
            rendered_title="Client Hydrated Title",
            rendered_meta_description=None,
            rendered_canonical_url=None,
            rendered_meta_robots=[],
            console_errors=[],
            page_exceptions=[],
            failed_subresources=[],
            hydration_mismatch=True,
            mismatch_details=["Title discrepancy"],
        )

        with (
            patch("socket.getaddrinfo", side_effect=mock_public_dns),
            patch("app.engine.runner.safe_fetch_url", return_value=fetch_res),
            patch("app.engine.runner.run_browser_audit", return_value=mock_browser_res),
        ):
            response = await run_single_url_audit(
                target_url="https://example.com/",
                include_browser=True,
            )

            assert response.browser_audit is not None
            assert response.browser_audit.rendered_title == "Client Hydrated Title"
            # Verify browser diagnostic rules were evaluated
            assert any(f.rule_id == "browser-console-health" for f in response.findings)
            assert any(f.rule_id == "browser-hydration-drift" for f in response.findings)


class TestBrowserAPIEndpoints:
    """Tests for POST /api/audits/browser and POST /api/audits/url with browser."""

    def test_api_browser_endpoint_success(self):
        mock_browser_res = BrowserAuditResult(
            final_rendered_url="https://example.com/",
            browser_status_code=200,
            rendered_title="Rendered Page",
            rendered_meta_description="A rendered page",
            rendered_canonical_url="https://example.com/",
            rendered_meta_robots=["index", "follow"],
            console_errors=[],
            page_exceptions=[],
            failed_subresources=[],
            render_duration_ms=120,
        )

        with (
            patch("socket.getaddrinfo", side_effect=mock_public_dns),
            patch("app.engine.browser.auditor.run_browser_audit", return_value=mock_browser_res),
        ):
            resp = client.post("/api/audits/browser", json={"url": "https://example.com/"})
            assert resp.status_code == 200
            data = resp.json()
            assert data["final_rendered_url"] == "https://example.com/"
            assert data["rendered_title"] == "Rendered Page"
            assert data["browser_status_code"] == 200

    def test_api_browser_endpoint_prohibited_ip_rejected(self):
        resp = client.post("/api/audits/browser", json={"url": "http://127.0.0.1:8000/"})
        assert resp.status_code == 400
        assert "Security check failed" in resp.json()["detail"]

    def test_api_browser_endpoint_metadata_ip_rejected(self):
        resp = client.post("/api/audits/browser", json={"url": "http://169.254.169.254/latest/meta-data/"})
        assert resp.status_code == 400
        assert "Security check failed" in resp.json()["detail"]

    def test_api_url_audit_with_browser_flag(self):
        html = """<!DOCTYPE html><html><head><title>Title</title></head><body>Content</body></html>"""
        fetch_res = make_html_fetch_result("https://example.com/", html)

        mock_browser_res = BrowserAuditResult(
            final_rendered_url="https://example.com/",
            browser_status_code=200,
            rendered_title="Title",
            rendered_meta_description=None,
            rendered_canonical_url=None,
            rendered_meta_robots=[],
            console_errors=[],
            page_exceptions=[],
            failed_subresources=[],
            render_duration_ms=100,
        )

        with (
            patch("socket.getaddrinfo", side_effect=mock_public_dns),
            patch("app.engine.runner.safe_fetch_url", return_value=fetch_res),
            patch("app.engine.runner.run_browser_audit", return_value=mock_browser_res),
        ):
            resp = client.post(
                "/api/audits/url",
                json={"url": "https://example.com/", "include_browser": True},
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["browser_audit"] is not None
            assert data["browser_audit"]["rendered_title"] == "Title"

    def test_api_browser_endpoint_unavailable_returns_503(self):
        """When Chromium binary or Playwright is missing, dedicated endpoint returns HTTP 503."""
        with (
            patch("socket.getaddrinfo", side_effect=mock_public_dns),
            patch(
                "app.engine.browser.auditor.run_browser_audit",
                side_effect=BrowserUnavailableError("Chromium executable is not installed."),
            ),
        ):
            resp = client.post("/api/audits/browser", json={"url": "https://example.com/"})
            assert resp.status_code == 503
            assert "unavailable" in resp.json()["detail"].lower() or "installed" in resp.json()["detail"].lower()

    def test_api_browser_endpoint_navigation_timeout_returns_502(self):
        """When browser navigation times out, dedicated endpoint returns HTTP 502."""
        with (
            patch("socket.getaddrinfo", side_effect=mock_public_dns),
            patch(
                "app.engine.browser.auditor.run_browser_audit",
                side_effect=BrowserNavigationError("Browser navigation timed out after 15.0s."),
            ),
        ):
            resp = client.post("/api/audits/browser", json={"url": "https://example.com/"})
            assert resp.status_code == 502
            assert "timed out" in resp.json()["detail"].lower()


class TestBrowserCollectorLimits:
    """Tests verifying collector enforces deterministic size and count bounding."""

    def test_collector_caps_excessive_console_and_exceptions(self):
        from app.engine.browser.collector import (
            BrowserCollector,
            MAX_CONSOLE_ERRORS,
            MAX_PAGE_EXCEPTIONS,
            MAX_FAILED_SUBRESOURCES,
            MAX_STRING_LENGTH,
        )

        collector = BrowserCollector()

        # Emit 100 console errors with very long strings
        long_text = "E" * 5000
        mock_msg = MagicMock()
        mock_msg.type = "error"
        mock_msg.text = long_text
        mock_msg.location = {"url": "https://example.com/app.js", "lineNumber": 42}

        for _ in range(100):
            collector._handle_console(mock_msg)

        assert len(collector.console_errors) == MAX_CONSOLE_ERRORS
        assert len(collector.console_errors[0].text) == MAX_STRING_LENGTH

        # Emit 50 page exceptions with very long stack
        long_exc = Exception("X" * 3000)
        setattr(long_exc, "stack", "S" * 6000)

        for _ in range(50):
            collector._handle_page_error(long_exc)

        assert len(collector.page_exceptions) == MAX_PAGE_EXCEPTIONS
        assert len(collector.page_exceptions[0].message) == MAX_STRING_LENGTH

        # Emit 100 failed subresources
        mock_req = MagicMock()
        mock_req.url = "https://example.com/missing.png"
        mock_req.failure = "net::ERR_FAILED"

        for _ in range(100):
            collector._handle_request_failed(mock_req)

        assert len(collector.failed_subresources) == MAX_FAILED_SUBRESOURCES
