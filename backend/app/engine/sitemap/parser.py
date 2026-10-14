"""Safe XML Sitemap Parser using defusedxml against XXE and entity expansion attacks."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from urllib.parse import urlparse
import xml.etree.ElementTree as ET

import defusedxml.ElementTree as DefusedET
from defusedxml.common import DefusedXmlException

from app.core.exceptions import AuditSecurityError
from app.core.url_validator import validate_and_normalize_url

logger = logging.getLogger(__name__)


def _strip_ns(tag: str) -> str:
    """Extract local tag name without XML namespace prefix."""
    if "}" in tag:
        return tag.split("}", 1)[1].lower()
    return tag.lower()


@dataclass
class ParsedSitemap:
    """Result of parsing a single sitemap XML document."""

    is_index: bool = False
    urls: list[str] = field(default_factory=list)
    child_sitemaps: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def parse_sitemap_xml(xml_content: str, max_urls: int = 10000) -> ParsedSitemap:
    """Safely parse a standard sitemap or sitemap index XML string.

    Defense-in-Depth:
    - Parses XML with defusedxml to neutralize XXE, entity expansion, and DTD attacks.
    - Handles XML namespaces commonly used in sitemaps (sitemaps.org, google news/image/video).
    - Rejects relative URLs and malformed links without throwing unhandled exceptions.
    - Deduplicates URLs while preserving document order.
    - Captures descriptive warnings for missing <loc> tags, malformed URLs, or unsupported elements.

    Args:
        xml_content: The raw XML response string.
        max_urls: Hard upper limit of URLs to extract from this document.

    Returns:
        ParsedSitemap containing extracted URLs or child sitemap links, plus warnings/errors.
    """
    result = ParsedSitemap()

    if not xml_content or not xml_content.strip():
        result.errors.append("Empty sitemap document: response content is empty or contains only whitespace.")
        return result

    # 1. Parse XML with defusedxml
    try:
        root = DefusedET.fromstring(xml_content.strip())
    except DefusedXmlException as err:
        logger.warning("XXE/DTD XML security violation blocked: %s", err)
        result.errors.append(
            f"XML security violation: Document contains prohibited external entities or DTD declarations ({err})."
        )
        return result
    except ET.ParseError as err:
        logger.info("XML parse error: %s", err)
        result.errors.append(f"Invalid XML syntax: Unable to parse document ({err}).")
        return result
    except Exception as err:
        logger.warning("Unexpected XML parser exception: %s", err)
        result.errors.append(f"Unexpected XML parsing failure: {err}")
        return result

    root_tag = _strip_ns(root.tag)

    # 2. Identify Document Type
    if root_tag == "sitemapindex":
        result.is_index = True
        _parse_sitemap_index(root, result)
    elif root_tag == "urlset":
        result.is_index = False
        _parse_urlset(root, result, max_urls=max_urls)
    else:
        # Check if the document appears to be HTML or another unsupported format
        if root_tag in ("html", "head", "body"):
            result.errors.append(
                "Unsupported document type: Received an HTML document instead of an XML sitemap (e.g. web page or custom error)."
            )
        else:
            result.errors.append(
                f"Unsupported document root element '<{root.tag}>'. Expected '<urlset>' or '<sitemapindex>'."
            )

    return result


def _parse_sitemap_index(root: ET.Element, result: ParsedSitemap) -> None:
    """Parse <sitemapindex> entries pointing to child sitemaps."""
    seen_sitemaps: set[str] = set()

    for child in root:
        if _strip_ns(child.tag) != "sitemap":
            continue

        loc_elem = None
        for elem in child:
            if _strip_ns(elem.tag) == "loc":
                loc_elem = elem
                break

        if loc_elem is None or not (loc_elem.text or "").strip():
            result.warnings.append("Skipped <sitemap> entry missing required <loc> element.")
            continue

        raw_loc = loc_elem.text.strip()

        # Validate URL syntax and require absolute HTTP/HTTPS
        try:
            parsed = urlparse(raw_loc)
            if not parsed.scheme or not parsed.netloc:
                result.warnings.append(f"Rejected relative child sitemap URL '{raw_loc}': sitemaps must use absolute URLs.")
                continue

            scheme = parsed.scheme.lower()
            if scheme not in ("http", "https"):
                result.warnings.append(f"Rejected non-HTTP child sitemap URL '{raw_loc}'.")
                continue

            if raw_loc not in seen_sitemaps:
                seen_sitemaps.add(raw_loc)
                result.child_sitemaps.append(raw_loc)
        except Exception as err:
            result.warnings.append(f"Rejected malformed child sitemap URL '{raw_loc}': {err}")

    if not result.child_sitemaps and not result.errors:
        result.warnings.append("Sitemap index contained no valid child <sitemap> entries.")


def _parse_urlset(root: ET.Element, result: ParsedSitemap, max_urls: int) -> None:
    """Parse <urlset> entries containing page URLs."""
    seen_urls: set[str] = set()

    for child in root:
        if len(result.urls) >= max_urls:
            result.warnings.append(f"Reached URL limit ({max_urls}); remaining entries in this sitemap were omitted.")
            break

        if _strip_ns(child.tag) != "url":
            continue

        loc_elem = None
        for elem in child:
            if _strip_ns(elem.tag) == "loc":
                loc_elem = elem
                break

        if loc_elem is None or not (loc_elem.text or "").strip():
            result.warnings.append("Skipped <url> entry missing required <loc> element.")
            continue

        raw_loc = loc_elem.text.strip()

        # Validate URL syntax and require absolute HTTP/HTTPS
        try:
            parsed = urlparse(raw_loc)
            if not parsed.scheme or not parsed.netloc:
                result.warnings.append(f"Rejected relative URL '{raw_loc}': sitemaps must specify absolute URLs.")
                continue

            # Normalize syntax without DNS resolution (resolution happens at fetch time)
            norm_url = validate_and_normalize_url(raw_loc, resolve_dns=False)
            if norm_url not in seen_urls:
                seen_urls.add(norm_url)
                result.urls.append(norm_url)
        except AuditSecurityError as err:
            result.warnings.append(f"Rejected insecure sitemap URL '{raw_loc}': {err.message}")
        except Exception as err:
            result.warnings.append(f"Rejected malformed sitemap URL '{raw_loc}': {err}")

    if not result.urls and not result.errors:
        result.warnings.append("Sitemap contains no valid <url> entries.")
