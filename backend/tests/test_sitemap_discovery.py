"""Unit and integration tests for Sitemap Discovery service and API endpoint."""

from __future__ import annotations

import socket
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.core.exceptions import (
    AuditFetchError,
    AuditSecurityError,
    ResponseTooLargeError,
)
from app.engine.fetcher import FetchResult
from app.engine.sitemap.discovery import discover_sitemaps
from app.main import app
from app.models.sitemap import SitemapStatus

client = TestClient(app)


def mock_public_dns(*args, **kwargs):
    return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 80))]


def make_fetch_result(
    url: str,
    body: str,
    status_code: int = 200,
    content_type: str = "application/xml",
) -> FetchResult:
    return FetchResult(
        initial_url=url,
        final_url=url,
        status_code=status_code,
        status_text="OK" if status_code == 200 else "Error",
        headers={"content-type": content_type},
        body=body,
        raw_bytes_count=len(body.encode("utf-8")),
        content_type=content_type,
        fetch_duration_ms=50,
        redirect_count=0,
    )


class TestSitemapDiscoveryService:
    """Tests for discover_sitemaps orchestrator."""

    @pytest.fixture(autouse=True)
    def mock_dns(self):
        with patch("socket.getaddrinfo", side_effect=mock_public_dns):
            yield

    @pytest.mark.anyio
    async def test_discover_via_robots_txt_success(self):
        """robots.txt declaring a sitemap URL which is then fetched and parsed."""
        robots_content = "User-agent: *\nDisallow: /admin\nSitemap: https://example.com/custom-sitemap.xml\n"
        sitemap_content = """<?xml version="1.0" encoding="UTF-8"?>
        <urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
            <url><loc>https://example.com/blog/post-1</loc></url>
            <url><loc>https://example.com/blog/post-2</loc></url>
        </urlset>
        """

        async def mock_fetch(target_url, **kwargs):
            if "robots.txt" in target_url:
                return make_fetch_result(target_url, robots_content, content_type="text/plain")
            elif "custom-sitemap.xml" in target_url:
                return make_fetch_result(target_url, sitemap_content)
            return make_fetch_result(target_url, "", status_code=404)

        with patch("app.engine.sitemap.discovery.safe_fetch_url", side_effect=mock_fetch):
            result = await discover_sitemaps("https://example.com/")

            assert result.sitemap_status == SitemapStatus.FOUND.value
            assert result.discovered_url_count == 2
            assert result.urls == ["https://example.com/blog/post-1", "https://example.com/blog/post-2"]
            assert "https://example.com/custom-sitemap.xml" in result.discovered_sitemaps

    @pytest.mark.anyio
    async def test_discover_fallback_to_standard_sitemap_xml(self):
        """When robots.txt is 404, falls back to /sitemap.xml."""
        sitemap_content = """<?xml version="1.0" encoding="UTF-8"?>
        <urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
            <url><loc>https://example.com/home</loc></url>
        </urlset>
        """

        async def mock_fetch(target_url, **kwargs):
            if "robots.txt" in target_url:
                return make_fetch_result(target_url, "", status_code=404)
            elif "sitemap.xml" in target_url:
                return make_fetch_result(target_url, sitemap_content)
            return make_fetch_result(target_url, "", status_code=404)

        with patch("app.engine.sitemap.discovery.safe_fetch_url", side_effect=mock_fetch):
            result = await discover_sitemaps("https://example.com/")

            assert result.sitemap_status == SitemapStatus.FOUND.value
            assert result.discovered_url_count == 1
            assert result.urls == ["https://example.com/home"]
            assert "https://example.com/sitemap.xml" in result.discovered_sitemaps

    @pytest.mark.anyio
    async def test_discover_explicit_sitemap_url(self):
        """User provides an explicit sitemap URL directly."""
        sitemap_content = """<?xml version="1.0" encoding="UTF-8"?>
        <urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
            <url><loc>https://example.com/explicit-page</loc></url>
        </urlset>
        """

        with patch(
            "app.engine.sitemap.discovery.safe_fetch_url",
            return_value=make_fetch_result("https://example.com/my-sitemap.xml", sitemap_content),
        ):
            result = await discover_sitemaps(
                "https://example.com/",
                explicit_sitemap_url="https://example.com/my-sitemap.xml",
            )

            assert result.sitemap_status == SitemapStatus.FOUND.value
            assert result.discovered_url_count == 1
            assert result.urls == ["https://example.com/explicit-page"]
            assert result.discovered_sitemaps == ["https://example.com/my-sitemap.xml"]

    @pytest.mark.anyio
    async def test_discover_sitemap_index_with_children(self):
        """Sitemap index file containing references to child sitemaps."""
        index_content = """<?xml version="1.0" encoding="UTF-8"?>
        <sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
            <sitemap><loc>https://example.com/sub-sitemap1.xml</loc></sitemap>
            <sitemap><loc>https://example.com/sub-sitemap2.xml</loc></sitemap>
        </sitemapindex>
        """
        child1_content = """<?xml version="1.0" encoding="UTF-8"?>
        <urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
            <url><loc>https://example.com/articles/1</loc></url>
        </urlset>
        """
        child2_content = """<?xml version="1.0" encoding="UTF-8"?>
        <urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
            <url><loc>https://example.com/articles/2</loc></url>
        </urlset>
        """

        async def mock_fetch(target_url, **kwargs):
            if "robots.txt" in target_url:
                return make_fetch_result(target_url, "", status_code=404)
            elif "sitemap.xml" in target_url:
                return make_fetch_result(target_url, index_content)
            elif "sub-sitemap1.xml" in target_url:
                return make_fetch_result(target_url, child1_content)
            elif "sub-sitemap2.xml" in target_url:
                return make_fetch_result(target_url, child2_content)
            return make_fetch_result(target_url, "", status_code=404)

        with patch("app.engine.sitemap.discovery.safe_fetch_url", side_effect=mock_fetch):
            result = await discover_sitemaps("https://example.com/")

            assert result.sitemap_status == SitemapStatus.FOUND.value
            assert result.discovered_url_count == 2
            assert "https://example.com/articles/1" in result.urls
            assert "https://example.com/articles/2" in result.urls
            assert "https://example.com/sitemap.xml" in result.discovered_sitemaps

    @pytest.mark.anyio
    async def test_discover_nested_sitemap_index_recursion_limit(self):
        """Nested sitemap index inside a child sitemap is rejected by recursion limit."""
        index1 = """<?xml version="1.0" encoding="UTF-8"?>
        <sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
            <sitemap><loc>https://example.com/child-index.xml</loc></sitemap>
        </sitemapindex>
        """
        nested_index = """<?xml version="1.0" encoding="UTF-8"?>
        <sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
            <sitemap><loc>https://example.com/deep.xml</loc></sitemap>
        </sitemapindex>
        """

        async def mock_fetch(target_url, **kwargs):
            if "sitemap.xml" in target_url:
                return make_fetch_result(target_url, index1)
            elif "child-index.xml" in target_url:
                return make_fetch_result(target_url, nested_index)
            return make_fetch_result(target_url, "", status_code=404)

        with patch("app.engine.sitemap.discovery.safe_fetch_url", side_effect=mock_fetch):
            result = await discover_sitemaps("https://example.com/", explicit_sitemap_url="https://example.com/sitemap.xml")

            assert any("recursion limit" in w for w in result.warnings)

    @pytest.mark.anyio
    async def test_discover_child_sitemap_limit_enforced(self):
        """Index with many child sitemaps respects max_child_sitemaps limit."""
        children = "\n".join(f"<sitemap><loc>https://example.com/s{i}.xml</loc></sitemap>" for i in range(10))
        index_xml = f"""<?xml version="1.0"?><sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{children}</sitemapindex>"""

        async def mock_fetch(target_url, **kwargs):
            if "index.xml" in target_url:
                return make_fetch_result(target_url, index_xml)
            return make_fetch_result(target_url, "<urlset xmlns='http://www.sitemaps.org/schemas/sitemap/0.9'><url><loc>https://example.com/p</loc></url></urlset>")

        with patch("app.engine.sitemap.discovery.safe_fetch_url", side_effect=mock_fetch):
            result = await discover_sitemaps(
                "https://example.com/",
                explicit_sitemap_url="https://example.com/index.xml",
                max_child_sitemaps=3,
            )

            assert any("limited to first 3" in w for w in result.warnings)

    @pytest.mark.anyio
    async def test_discover_ssrf_child_sitemap_blocked(self):
        """A child sitemap URL in an index pointing to private/cloud metadata IP is blocked."""
        index_with_ssrf = """<?xml version="1.0" encoding="UTF-8"?>
        <sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
            <sitemap><loc>http://169.254.169.254/latest/meta-data/</loc></sitemap>
            <sitemap><loc>http://127.0.0.1:8000/internal-sitemap.xml</loc></sitemap>
        </sitemapindex>
        """

        async def mock_fetch(target_url, **kwargs):
            if "index.xml" in target_url:
                return make_fetch_result(target_url, index_with_ssrf)
            return make_fetch_result(target_url, "", status_code=404)

        with patch("app.engine.sitemap.discovery.safe_fetch_url", side_effect=mock_fetch):
            result = await discover_sitemaps(
                "https://example.com/",
                explicit_sitemap_url="https://example.com/index.xml",
            )

            assert result.sitemap_status == SitemapStatus.BLOCKED.value
            assert any("Security validation blocked" in err for err in result.errors)
            assert result.discovered_url_count == 0

    @pytest.mark.anyio
    async def test_discover_sitemap_not_found(self):
        """When robots.txt and /sitemap.xml both return 404, status is 'Sitemap not found'."""
        with patch(
            "app.engine.sitemap.discovery.safe_fetch_url",
            return_value=make_fetch_result("https://example.com/sitemap.xml", "", status_code=404),
        ):
            result = await discover_sitemaps("https://example.com/")

            assert result.sitemap_status == SitemapStatus.NOT_FOUND.value
            assert result.discovered_url_count == 0

    @pytest.mark.anyio
    async def test_discover_sitemap_inaccessible(self):
        """When fetching fails due to timeout or network connection, status is 'Sitemap inaccessible'."""
        with patch(
            "app.engine.sitemap.discovery.safe_fetch_url",
            side_effect=AuditFetchError("Connection timed out", error_type="CONNECT_TIMEOUT"),
        ):
            result = await discover_sitemaps("https://example.com/", explicit_sitemap_url="https://example.com/sitemap.xml")

            assert result.sitemap_status == SitemapStatus.INACCESSIBLE.value
            assert any("Failed to fetch" in err for err in result.errors)

    @pytest.mark.anyio
    async def test_discover_sitemap_invalid_content(self):
        """When sitemap returns HTTP 200 but contains invalid non-XML or HTML error page, status is 'Invalid sitemap'."""
        html_404 = "<!DOCTYPE html><html><body>Error 404 Not Found</body></html>"
        with patch(
            "app.engine.sitemap.discovery.safe_fetch_url",
            return_value=make_fetch_result("https://example.com/sitemap.xml", html_404, content_type="text/html"),
        ):
            result = await discover_sitemaps("https://example.com/", explicit_sitemap_url="https://example.com/sitemap.xml")

            assert result.sitemap_status == SitemapStatus.INVALID.value
            assert any("Unsupported document type" in err for err in result.errors)

    @pytest.mark.anyio
    async def test_discover_oversized_sitemap_rejected(self):
        """When sitemap file exceeds size limit, ResponseTooLargeError marks status as Invalid sitemap."""
        with patch(
            "app.engine.sitemap.discovery.safe_fetch_url",
            side_effect=ResponseTooLargeError(5 * 1024 * 1024),
        ):
            result = await discover_sitemaps("https://example.com/", explicit_sitemap_url="https://example.com/sitemap.xml")

            assert result.sitemap_status == SitemapStatus.INVALID.value
            assert any("exceeded maximum size" in err for err in result.errors)


class TestSitemapDiscoverAPIEndpoint:
    """Tests for POST /api/sitemaps/discover endpoint."""

    def test_api_discover_success(self):
        """Verify API returns 200 with complete response structure."""
        sitemap_content = """<?xml version="1.0" encoding="UTF-8"?>
        <urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
            <url><loc>https://example.com/page1</loc></url>
            <url><loc>https://example.com/page2</loc></url>
        </urlset>
        """
        with (
            patch("socket.getaddrinfo", side_effect=mock_public_dns),
            patch(
                "app.engine.sitemap.discovery.safe_fetch_url",
                return_value=make_fetch_result("https://example.com/sitemap.xml", sitemap_content),
            ),
        ):
            response = client.post(
                "/api/sitemaps/discover",
                json={
                    "website_url": "https://example.com/",
                    "sitemap_url": "https://example.com/sitemap.xml",
                    "max_urls": 100,
                },
            )
            assert response.status_code == 200
            data = response.json()
            assert data["website_url"] == "https://example.com/"
            assert data["sitemap_status"] == "Sitemap found"
            assert data["discovered_sitemaps"] == ["https://example.com/sitemap.xml"]
            assert data["discovered_url_count"] == 2
            assert data["urls"] == ["https://example.com/page1", "https://example.com/page2"]
            assert isinstance(data["warnings"], list)
            assert isinstance(data["errors"], list)
            assert isinstance(data["processing_duration_ms"], (int, float))

    def test_api_prohibited_loopback_rejected(self):
        """Prohibited loopback website URL is rejected with HTTP 400."""
        response = client.post(
            "/api/sitemaps/discover",
            json={"website_url": "http://127.0.0.1:8000/"},
        )
        assert response.status_code == 400
        assert "Security check failed" in response.json()["detail"]

    def test_api_prohibited_metadata_ip_rejected(self):
        """Prohibited cloud metadata IP is rejected with HTTP 400."""
        response = client.post(
            "/api/sitemaps/discover",
            json={"website_url": "http://169.254.169.254/"},
        )
        assert response.status_code == 400
        assert "Security check failed" in response.json()["detail"]

    def test_api_empty_website_url_rejected(self):
        """Empty website_url is rejected with HTTP 400 or 422."""
        response = client.post(
            "/api/sitemaps/discover",
            json={"website_url": "   "},
        )
        assert response.status_code == 400

    def test_api_max_urls_validation_enforced(self):
        """max_urls must be between 1 and 10000; invalid values are rejected with 422."""
        response_zero = client.post(
            "/api/sitemaps/discover",
            json={"website_url": "https://example.com/", "max_urls": 0},
        )
        assert response_zero.status_code == 422

        response_too_large = client.post(
            "/api/sitemaps/discover",
            json={"website_url": "https://example.com/", "max_urls": 999999},
        )
        assert response_too_large.status_code == 422
