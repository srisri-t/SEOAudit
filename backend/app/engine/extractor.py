"""SEO Metadata Extraction using BeautifulSoup."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from app.engine.fetcher import FetchResult


@dataclass
class TitleData:
    text: str | None
    length: int
    count: int
    is_missing: bool
    is_empty: bool


@dataclass
class DescriptionData:
    text: str | None
    length: int
    count: int
    is_missing: bool
    is_empty: bool


@dataclass
class CanonicalData:
    raw_href: str | None
    resolved_url: str | None
    count: int
    is_missing: bool
    is_empty: bool
    is_self_referential: bool


@dataclass
class RobotsDirectiveData:
    meta_directives: list[str] = field(default_factory=list)
    x_robots_directives: list[str] = field(default_factory=list)
    has_meta_noindex: bool = False
    has_x_noindex: bool = False
    has_any_noindex: bool = False


@dataclass
class ExtractedMetadata:
    title: TitleData
    description: DescriptionData
    canonical: CanonicalData
    robots: RobotsDirectiveData
    raw_headings_h1: list[str] = field(default_factory=list)


def parse_directives(directive_str: str) -> list[str]:
    """Parse comma-separated robots directives into a clean list of lowercase tokens."""
    if not directive_str:
        return []
    tokens = re.split(r"[,;]+", directive_str)
    return [t.strip().lower() for t in tokens if t.strip()]


def extract_seo_metadata(fetch_result: FetchResult) -> ExtractedMetadata:
    """Extract and parse SEO elements from the fetched response."""
    # 1. Parse X-Robots-Tag from response headers
    x_robots_header = fetch_result.headers.get("x-robots-tag", "")
    x_directives = parse_directives(x_robots_header)
    has_x_noindex = any(d in ("noindex", "none") for d in x_directives)

    # Default empty values if body is not HTML
    if not fetch_result.is_html or not fetch_result.body:
        return ExtractedMetadata(
            title=TitleData(text=None, length=0, count=0, is_missing=True, is_empty=True),
            description=DescriptionData(text=None, length=0, count=0, is_missing=True, is_empty=True),
            canonical=CanonicalData(
                raw_href=None,
                resolved_url=None,
                count=0,
                is_missing=True,
                is_empty=True,
                is_self_referential=False,
            ),
            robots=RobotsDirectiveData(
                meta_directives=[],
                x_robots_directives=x_directives,
                has_meta_noindex=False,
                has_x_noindex=has_x_noindex,
                has_any_noindex=has_x_noindex,
            ),
        )

    # Parse HTML using BeautifulSoup
    soup = BeautifulSoup(fetch_result.body, "html.parser")

    # 2. Extract Title
    title_tags = soup.find_all("title")
    title_count = len(title_tags)
    if title_count > 0:
        raw_title = title_tags[0].get_text()
        clean_title = raw_title.strip() if raw_title else ""
        is_title_empty = len(clean_title) == 0
        title_text = clean_title if not is_title_empty else None
        title_data = TitleData(
            text=title_text,
            length=len(clean_title),
            count=title_count,
            is_missing=False,
            is_empty=is_title_empty,
        )
    else:
        title_data = TitleData(
            text=None,
            length=0,
            count=0,
            is_missing=True,
            is_empty=True,
        )

    # 3. Extract Meta Description
    desc_tags = soup.find_all(
        "meta",
        attrs={"name": lambda val: val and val.lower() == "description"},
    )
    desc_count = len(desc_tags)
    if desc_count > 0:
        raw_content = desc_tags[0].get("content", "")
        clean_desc = raw_content.strip() if raw_content else ""
        is_desc_empty = len(clean_desc) == 0
        desc_text = clean_desc if not is_desc_empty else None
        desc_data = DescriptionData(
            text=desc_text,
            length=len(clean_desc),
            count=desc_count,
            is_missing=False,
            is_empty=is_desc_empty,
        )
    else:
        desc_data = DescriptionData(
            text=None,
            length=0,
            count=0,
            is_missing=True,
            is_empty=True,
        )

    # 4. Extract Canonical Link
    canonical_tags = soup.find_all(
        "link",
        attrs={"rel": lambda val: val and any(r.lower() == "canonical" for r in (val if isinstance(val, list) else [val]))},
    )
    canonical_count = len(canonical_tags)
    if canonical_count > 0:
        raw_href = canonical_tags[0].get("href", "")
        clean_href = raw_href.strip() if raw_href else ""
        is_canonical_empty = len(clean_href) == 0

        if not is_canonical_empty:
            resolved = urljoin(fetch_result.final_url, clean_href)
            is_self_ref = resolved.rstrip("/").lower() == fetch_result.final_url.rstrip("/").lower()
        else:
            resolved = None
            is_self_ref = False

        canonical_data = CanonicalData(
            raw_href=clean_href if not is_canonical_empty else None,
            resolved_url=resolved,
            count=canonical_count,
            is_missing=False,
            is_empty=is_canonical_empty,
            is_self_referential=is_self_ref,
        )
    else:
        canonical_data = CanonicalData(
            raw_href=None,
            resolved_url=None,
            count=0,
            is_missing=True,
            is_empty=True,
            is_self_referential=False,
        )

    # 5. Extract Meta Robots directives
    meta_robots_tags = soup.find_all(
        "meta",
        attrs={"name": lambda val: val and val.lower() in ("robots", "googlebot")},
    )
    all_meta_directives: list[str] = []
    for tag in meta_robots_tags:
        content = tag.get("content", "")
        all_meta_directives.extend(parse_directives(content))

    has_meta_noindex = any(d in ("noindex", "none") for d in all_meta_directives)

    robots_data = RobotsDirectiveData(
        meta_directives=all_meta_directives,
        x_robots_directives=x_directives,
        has_meta_noindex=has_meta_noindex,
        has_x_noindex=has_x_noindex,
        has_any_noindex=has_meta_noindex or has_x_noindex,
    )

    # 6. Optional H1 elements for context
    h1_elements = [h1.get_text().strip() for h1 in soup.find_all("h1") if h1.get_text().strip()]

    return ExtractedMetadata(
        title=title_data,
        description=desc_data,
        canonical=canonical_data,
        robots=robots_data,
        raw_headings_h1=h1_elements,
    )
