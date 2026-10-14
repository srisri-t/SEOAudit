"""Unit tests for XML sitemap parser and XXE security defenses."""

from __future__ import annotations

import pytest

from app.engine.sitemap.parser import parse_sitemap_xml


class TestStandardSitemapParsing:
    """Tests for standard XML sitemaps (<urlset>)."""

    def test_parse_standard_sitemap(self):
        xml = """<?xml version="1.0" encoding="UTF-8"?>
        <urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
            <url>
                <loc>https://example.com/page1</loc>
                <lastmod>2026-01-01</lastmod>
                <priority>0.8</priority>
            </url>
            <url>
                <loc>https://example.com/page2</loc>
            </url>
        </urlset>
        """
        result = parse_sitemap_xml(xml)
        assert result.is_index is False
        assert len(result.urls) == 2
        assert result.urls == ["https://example.com/page1", "https://example.com/page2"]
        assert len(result.errors) == 0

    def test_parse_namespaced_sitemap_with_extensions(self):
        xml = """<?xml version="1.0" encoding="UTF-8"?>
        <urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"
                xmlns:image="http://www.google.com/schemas/sitemap-image/1.1"
                xmlns:xhtml="http://www.w3.org/1999/xhtml">
            <url>
                <loc>https://example.com/gallery</loc>
                <image:image>
                    <image:loc>https://example.com/img.jpg</image:loc>
                </image:image>
            </url>
            <url>
                <loc>https://example.com/about</loc>
            </url>
        </urlset>
        """
        result = parse_sitemap_xml(xml)
        assert result.is_index is False
        assert result.urls == ["https://example.com/gallery", "https://example.com/about"]

    def test_parse_sitemap_duplicate_urls_removed(self):
        xml = """<?xml version="1.0" encoding="UTF-8"?>
        <urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
            <url><loc>https://example.com/page1</loc></url>
            <url><loc>https://example.com/page2</loc></url>
            <url><loc>https://example.com/page1</loc></url>
            <url><loc>https://example.com/page2</loc></url>
        </urlset>
        """
        result = parse_sitemap_xml(xml)
        assert len(result.urls) == 2
        assert result.urls == ["https://example.com/page1", "https://example.com/page2"]

    def test_parse_sitemap_url_limit_enforced(self):
        xml = """<?xml version="1.0" encoding="UTF-8"?>
        <urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
            <url><loc>https://example.com/p1</loc></url>
            <url><loc>https://example.com/p2</loc></url>
            <url><loc>https://example.com/p3</loc></url>
        </urlset>
        """
        result = parse_sitemap_xml(xml, max_urls=2)
        assert len(result.urls) == 2
        assert result.urls == ["https://example.com/p1", "https://example.com/p2"]
        assert any("Reached URL limit" in w for w in result.warnings)

    def test_parse_sitemap_missing_loc_element(self):
        xml = """<?xml version="1.0" encoding="UTF-8"?>
        <urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
            <url><lastmod>2026-01-01</lastmod></url>
            <url><loc>https://example.com/valid</loc></url>
            <url><loc>   </loc></url>
        </urlset>
        """
        result = parse_sitemap_xml(xml)
        assert result.urls == ["https://example.com/valid"]
        assert len(result.warnings) >= 2
        assert any("missing required <loc>" in w for w in result.warnings)

    def test_parse_sitemap_relative_and_malformed_urls_rejected(self):
        xml = """<?xml version="1.0" encoding="UTF-8"?>
        <urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
            <url><loc>/relative/path</loc></url>
            <url><loc>not-a-url</loc></url>
            <url><loc>javascript:alert(1)</loc></url>
            <url><loc>https://example.com/valid</loc></url>
        </urlset>
        """
        result = parse_sitemap_xml(xml)
        assert result.urls == ["https://example.com/valid"]
        assert any("Rejected relative URL" in w or "Rejected insecure" in w for w in result.warnings)


class TestSitemapIndexParsing:
    """Tests for <sitemapindex> parsing."""

    def test_parse_valid_sitemap_index(self):
        xml = """<?xml version="1.0" encoding="UTF-8"?>
        <sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
            <sitemap>
                <loc>https://example.com/sitemap1.xml</loc>
                <lastmod>2026-01-01</lastmod>
            </sitemap>
            <sitemap>
                <loc>https://example.com/sitemap2.xml</loc>
            </sitemap>
        </sitemapindex>
        """
        result = parse_sitemap_xml(xml)
        assert result.is_index is True
        assert len(result.child_sitemaps) == 2
        assert result.child_sitemaps == [
            "https://example.com/sitemap1.xml",
            "https://example.com/sitemap2.xml",
        ]

    def test_parse_sitemap_index_duplicate_children_deduplicated(self):
        xml = """<?xml version="1.0" encoding="UTF-8"?>
        <sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
            <sitemap><loc>https://example.com/sitemap1.xml</loc></sitemap>
            <sitemap><loc>https://example.com/sitemap1.xml</loc></sitemap>
        </sitemapindex>
        """
        result = parse_sitemap_xml(xml)
        assert result.is_index is True
        assert len(result.child_sitemaps) == 1

    def test_parse_sitemap_index_missing_loc(self):
        xml = """<?xml version="1.0" encoding="UTF-8"?>
        <sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
            <sitemap><lastmod>2026-01-01</lastmod></sitemap>
            <sitemap><loc>https://example.com/valid.xml</loc></sitemap>
        </sitemapindex>
        """
        result = parse_sitemap_xml(xml)
        assert result.child_sitemaps == ["https://example.com/valid.xml"]
        assert any("missing required <loc>" in w for w in result.warnings)


class TestParserSecurityAndMalformedXML:
    """Tests for XML parser hardening against XXE, empty files, and malformed inputs."""

    def test_empty_xml_content_rejected(self):
        result = parse_sitemap_xml("")
        assert len(result.errors) > 0
        assert "Empty sitemap document" in result.errors[0]

        result_whitespace = parse_sitemap_xml("   \n\t  ")
        assert len(result_whitespace.errors) > 0

    def test_malformed_xml_syntax_returns_error(self):
        malformed = "<urlset><url><loc>https://example.com</urlset>"
        result = parse_sitemap_xml(malformed)
        assert len(result.errors) > 0
        assert "Invalid XML syntax" in result.errors[0]

    def test_unsupported_document_type_html(self):
        html = "<!DOCTYPE html><html><head><title>404</title></head><body>Not Found</body></html>"
        result = parse_sitemap_xml(html)
        assert len(result.errors) > 0
        assert "Unsupported document type" in result.errors[0]

    def test_unsupported_document_type_generic_xml(self):
        xml = "<catalog><book id='1'><title>Book</title></book></catalog>"
        result = parse_sitemap_xml(xml)
        assert len(result.errors) > 0
        assert "Unsupported document root" in result.errors[0]

    def test_xxe_external_entity_injection_blocked(self):
        xxe_payload = """<?xml version="1.0" encoding="ISO-8859-1"?>
        <!DOCTYPE foo [
        <!ELEMENT foo ANY >
        <!ENTITY xxe SYSTEM "file:///etc/passwd" >]>
        <urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
            <url><loc>&xxe;</loc></url>
        </urlset>
        """
        result = parse_sitemap_xml(xxe_payload)
        assert len(result.errors) > 0
        assert any("XML security violation" in err for err in result.errors)
        assert len(result.urls) == 0

    def test_billion_laughs_entity_expansion_blocked(self):
        billion_laughs = """<?xml version="1.0"?>
        <!DOCTYPE lolz [
        <!ENTITY lol "lol">
        <!ELEMENT lolz (#PCDATA)>
        <!ENTITY lol1 "&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;">
        <!ENTITY lol2 "&lol1;&lol1;&lol1;&lol1;&lol1;&lol1;&lol1;&lol1;&lol1;&lol1;">
        ]>
        <urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
            <url><loc>&lol2;</loc></url>
        </urlset>
        """
        result = parse_sitemap_xml(billion_laughs)
        assert len(result.errors) > 0
        assert any("XML security violation" in err for err in result.errors)
