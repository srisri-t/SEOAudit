"""Website-wide aggregate SEO analysis across batch-audited pages."""

from __future__ import annotations

from collections import defaultdict
from urllib.parse import urlsplit, urlunsplit

from app.models.batch import (
    AggregateSummary,
    BrokenLinkFinding,
    DuplicateDescriptionGroup,
    DuplicateTitleGroup,
    InternalLinkSummary,
    PageAuditResult,
)


def normalize_url_for_comparison(url: str) -> str:
    """Normalize URL by stripping fragments, lowercasing netloc, and stripping trailing slashes."""
    if not url:
        return ""
    try:
        parts = urlsplit(url.strip())
        scheme = parts.scheme.lower()
        netloc = parts.netloc.lower()
        path = parts.path
        if path.endswith("/") and path != "/":
            path = path.rstrip("/")
        # Omit query fragments for structural comparison
        return urlunsplit((scheme, netloc, path, parts.query, ""))
    except Exception:
        return url.strip().rstrip("/")


def is_internal_url(candidate_url: str, base_netlocs: set[str]) -> bool:
    """Determine if a URL belongs to the internal website scope."""
    try:
        parts = urlsplit(candidate_url)
        return parts.netloc.lower() in base_netlocs
    except Exception:
        return False


def calculate_aggregate_summary(
    pages: list[PageAuditResult],
    total_discovered: int,
    target_origin: str = "",
) -> AggregateSummary:
    """Calculate aggregate SEO metrics, duplicate content, and link integrity across batch results."""
    total_audited = len(pages)
    successful_pages = sum(1 for p in pages if p.status == "success")
    failed_pages = sum(1 for p in pages if p.status == "failed")
    skipped_pages = sum(1 for p in pages if p.status == "skipped")

    status_code_dist: dict[str, int] = defaultdict(int)
    severity_dist: dict[str, int] = defaultdict(int)

    title_to_urls: dict[str, list[str]] = defaultdict(list)
    desc_to_urls: dict[str, list[str]] = defaultdict(list)

    missing_titles = 0
    missing_descriptions = 0

    # Build lookup map of audited URLs for internal-link resolution
    audited_map: dict[str, PageAuditResult] = {}
    base_netlocs: set[str] = set()

    if target_origin:
        try:
            base_netlocs.add(urlsplit(target_origin).netloc.lower())
        except Exception:
            pass

    for page in pages:
        norm_url = normalize_url_for_comparison(page.url)
        audited_map[norm_url] = page
        if page.final_url:
            norm_final = normalize_url_for_comparison(page.final_url)
            audited_map[norm_final] = page

        try:
            netloc = urlsplit(page.url).netloc.lower()
            if netloc:
                base_netlocs.add(netloc)
        except Exception:
            pass

        # Status code breakdown
        if page.status_code is not None:
            status_code_dist[str(page.status_code)] += 1
        elif page.status == "failed":
            status_code_dist["error"] += 1
        elif page.status == "skipped":
            status_code_dist["skipped"] += 1

        # Findings severity breakdown
        for f in page.findings:
            severity_dist[f.status] += 1

        # Title analysis
        if not page.title or not page.title.strip():
            if page.status == "success":
                missing_titles += 1
        else:
            clean_title = page.title.strip()
            title_to_urls[clean_title].append(page.url)

        # Meta description analysis
        if not page.meta_description or not page.meta_description.strip():
            if page.status == "success":
                missing_descriptions += 1
        else:
            clean_desc = page.meta_description.strip()
            desc_to_urls[clean_desc].append(page.url)

    # Calculate duplicate titles (only groups with > 1 occurrence)
    duplicate_titles = [
        DuplicateTitleGroup(title=t, count=len(urls), urls=urls)
        for t, urls in title_to_urls.items()
        if len(urls) > 1
    ]
    duplicate_titles.sort(key=lambda x: (-x.count, x.title.lower()))

    # Calculate duplicate meta descriptions (only groups with > 1 occurrence)
    duplicate_descriptions = [
        DuplicateDescriptionGroup(description=d, count=len(urls), urls=urls)
        for d, urls in desc_to_urls.items()
        if len(urls) > 1
    ]
    duplicate_descriptions.sort(key=lambda x: (-x.count, x.description.lower()))

    # Internal link analysis
    total_internal_links = 0
    external_links_count = 0
    confirmed_broken: list[BrokenLinkFinding] = []
    unverified_links: list[BrokenLinkFinding] = []

    seen_link_pairs: set[tuple[str, str]] = set()

    for page in pages:
        if page.status != "success":
            continue

        for target_href in page.outgoing_links:
            if not is_internal_url(target_href, base_netlocs):
                external_links_count += 1
                continue

            total_internal_links += 1
            norm_target = normalize_url_for_comparison(target_href)
            pair = (page.url, norm_target)
            if pair in seen_link_pairs:
                continue
            seen_link_pairs.add(pair)

            if norm_target in audited_map:
                target_page = audited_map[norm_target]
                if (
                    target_page.status == "failed"
                    or (target_page.status_code is not None and target_page.status_code >= 400)
                ):
                    confirmed_broken.append(
                        BrokenLinkFinding(
                            source_url=page.url,
                            target_url=target_href,
                            status_code=target_page.status_code,
                            reason="confirmed_broken",
                        )
                    )
            else:
                unverified_links.append(
                    BrokenLinkFinding(
                        source_url=page.url,
                        target_url=target_href,
                        status_code=None,
                        reason="unverified",
                    )
                )

    internal_link_summary = InternalLinkSummary(
        total_internal_links_checked=total_internal_links,
        confirmed_broken_links=confirmed_broken,
        unverified_internal_links=unverified_links,
        external_links_count=external_links_count,
    )

    return AggregateSummary(
        total_pages_discovered=total_discovered,
        total_pages_audited=total_audited,
        successful_pages=successful_pages,
        failed_pages=failed_pages,
        skipped_pages=skipped_pages,
        status_code_distribution=dict(status_code_dist),
        findings_by_severity=dict(severity_dist),
        duplicate_titles=duplicate_titles,
        duplicate_descriptions=duplicate_descriptions,
        missing_titles_count=missing_titles,
        missing_descriptions_count=missing_descriptions,
        internal_link_analysis=internal_link_summary,
    )
