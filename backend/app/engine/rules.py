"""Technical SEO Audit Rules.

Evaluates HTTP responses and extracted metadata against 8 objective rules:
1. HTTP Status Code
2. Redirect Behavior & Final URL
3. Page Title Presence & Length
4. Meta Description Presence & Length
5. Canonical URL Presence & Validity
6. Meta Robots Noindex Directive
7. X-Robots-Tag Noindex Header
8. Content-Type & HTML Validity
"""

from __future__ import annotations

from app.engine.extractor import ExtractedMetadata
from app.engine.fetcher import FetchResult
from app.models.audit import Finding


def evaluate_http_status(fetch_res: FetchResult) -> Finding:
    """Evaluate HTTP status code."""
    code = fetch_res.status_code
    phrase = fetch_res.status_text

    if code == 200:
        return Finding(
            rule_id="http-status",
            title="HTTP Response Status",
            status="pass",
            explanation=f"Server returned HTTP 200 {phrase}. Page was delivered successfully.",
            evidence=f"HTTP {code} {phrase}",
        )
    elif 300 <= code < 400:
        return Finding(
            rule_id="http-status",
            title="HTTP Response Status",
            status="warning",
            explanation=f"Server returned redirect status HTTP {code} {phrase}.",
            recommendation="Confirm the target URL resolves to a final 200 OK endpoint.",
            evidence=f"HTTP {code} {phrase}",
        )
    elif 400 <= code < 500:
        return Finding(
            rule_id="http-status",
            title="HTTP Response Status",
            status="issue",
            explanation=f"Server returned client error HTTP {code} {phrase}. Search engines will not index this page.",
            recommendation="Fix broken links or restore missing content at this URL.",
            evidence=f"HTTP {code} {phrase}",
        )
    else:
        return Finding(
            rule_id="http-status",
            title="HTTP Response Status",
            status="error",
            explanation=f"Server returned error HTTP {code} {phrase}.",
            recommendation="Investigate web server logs and resolve backend application errors.",
            evidence=f"HTTP {code} {phrase}",
        )


def evaluate_redirect_chain(fetch_res: FetchResult) -> Finding:
    """Evaluate redirect behavior, hop counts, and final URL stability."""
    count = fetch_res.redirect_count
    chain = fetch_res.redirect_chain

    if count == 0:
        return Finding(
            rule_id="redirect-chain",
            title="Redirect Behavior & Final URL",
            status="pass",
            explanation="Direct connection without redirects. URL responds directly.",
            evidence=f"Final URL: {fetch_res.final_url}",
        )
    elif count == 1:
        hop = chain[0]
        status = hop.status_code
        if status in (301, 308):
            return Finding(
                rule_id="redirect-chain",
                title="Redirect Behavior & Final URL",
                status="pass",
                explanation=f"Clean single permanent redirect (HTTP {status}) followed to destination.",
                evidence=f"{hop.url} -> HTTP {status} -> {fetch_res.final_url}",
            )
        else:
            return Finding(
                rule_id="redirect-chain",
                title="Redirect Behavior & Final URL",
                status="warning",
                explanation=f"Single temporary redirect (HTTP {status}) followed. Permanent redirects (301) are preferred for canonical ranking signals.",
                recommendation="Change temporary redirects (302/307) to permanent redirects (301) if the move is lasting.",
                evidence=f"{hop.url} -> HTTP {status} -> {fetch_res.final_url}",
            )
    else:
        evidence_chain = " -> ".join([f"{h.url} ({h.status_code})" for h in chain]) + f" -> {fetch_res.final_url}"
        return Finding(
            rule_id="redirect-chain",
            title="Redirect Behavior & Final URL",
            status="warning",
            explanation=f"Multiple redirects followed ({count} hops). Redirect chains waste crawl budget and increase page load latency.",
            recommendation="Update internal links and server configuration to point directly to the final URL.",
            evidence=evidence_chain,
        )


def evaluate_page_title(metadata: ExtractedMetadata) -> Finding:
    """Evaluate HTML title presence, uniqueness, and length."""
    title_data = metadata.title

    if title_data.is_missing:
        return Finding(
            rule_id="page-title",
            title="Page Title Presence & Length",
            status="issue",
            explanation="The <title> tag is completely missing from the HTML document.",
            recommendation="Add a descriptive <title> element inside the <head> section (recommended 15-65 characters).",
            evidence=None,
        )
    if title_data.is_empty:
        return Finding(
            rule_id="page-title",
            title="Page Title Presence & Length",
            status="issue",
            explanation="A <title> tag is present but contains only empty whitespace.",
            recommendation="Specify clear, relevant title text that identifies the page topic.",
            evidence="<title></title>",
        )

    evidence_text = f"\"{title_data.text}\" ({title_data.length} chars)"

    if title_data.count > 1:
        return Finding(
            rule_id="page-title",
            title="Page Title Presence & Length",
            status="warning",
            explanation=f"Multiple <title> tags ({title_data.count}) were detected. Search engines will ignore subsequent titles.",
            recommendation="Consolidate titles into a single authoritative <title> element.",
            evidence=evidence_text,
        )

    if title_data.length < 15:
        return Finding(
            rule_id="page-title",
            title="Page Title Presence & Length",
            status="warning",
            explanation=f"Page title is short ({title_data.length} characters). A more descriptive title improves relevance.",
            recommendation="Expand title length to between 15 and 65 characters.",
            evidence=evidence_text,
        )
    elif title_data.length > 70:
        return Finding(
            rule_id="page-title",
            title="Page Title Presence & Length",
            status="warning",
            explanation=f"Page title is long ({title_data.length} characters) and may be truncated on search result pages.",
            recommendation="Trim the title to under 65-70 characters to ensure full display in search results.",
            evidence=evidence_text,
        )
    else:
        return Finding(
            rule_id="page-title",
            title="Page Title Presence & Length",
            status="pass",
            explanation=f"Page title is present and within the recommended length ({title_data.length} characters).",
            evidence=evidence_text,
        )


def evaluate_meta_description(metadata: ExtractedMetadata) -> Finding:
    """Evaluate meta description presence and length."""
    desc = metadata.description

    if desc.is_missing:
        return Finding(
            rule_id="meta-description",
            title="Meta Description Presence & Length",
            status="issue",
            explanation="The meta description tag (<meta name='description'>) is missing.",
            recommendation="Add a meta description tag summarizing the page contents in 50-160 characters.",
            evidence=None,
        )
    if desc.is_empty:
        return Finding(
            rule_id="meta-description",
            title="Meta Description Presence & Length",
            status="issue",
            explanation="The meta description tag is present but its content attribute is empty.",
            recommendation="Provide an engaging summary in the meta description content attribute.",
            evidence='<meta name="description" content="">',
        )

    evidence_text = f"\"{desc.text}\" ({desc.length} chars)"

    if desc.count > 1:
        return Finding(
            rule_id="meta-description",
            title="Meta Description Presence & Length",
            status="warning",
            explanation=f"Multiple meta description tags ({desc.count}) were detected on this page.",
            recommendation="Ensure only a single meta description is defined per page.",
            evidence=evidence_text,
        )

    if desc.length < 50:
        return Finding(
            rule_id="meta-description",
            title="Meta Description Presence & Length",
            status="warning",
            explanation=f"Meta description is short ({desc.length} characters). It may not provide enough context for search snippets.",
            recommendation="Expand the description to between 50 and 160 characters.",
            evidence=evidence_text,
        )
    elif desc.length > 165:
        return Finding(
            rule_id="meta-description",
            title="Meta Description Presence & Length",
            status="warning",
            explanation=f"Meta description is long ({desc.length} characters) and will likely be truncated on search results pages.",
            recommendation="Trim description to between 50 and 160 characters to fit standard search result snippets.",
            evidence=evidence_text,
        )
    else:
        return Finding(
            rule_id="meta-description",
            title="Meta Description Presence & Length",
            status="pass",
            explanation=f"Meta description is present with optimal length ({desc.length} characters).",
            evidence=evidence_text,
        )


def evaluate_canonical_link(metadata: ExtractedMetadata, final_url: str) -> Finding:
    """Evaluate canonical link tag presence and validity."""
    canonical = metadata.canonical

    if canonical.is_missing:
        return Finding(
            rule_id="canonical-url",
            title="Canonical URL Tag",
            status="warning",
            explanation="No canonical tag (<link rel='canonical'>) was found. While optional, specifying an explicit canonical tag prevents duplicate content issues.",
            recommendation="Add a canonical tag in <head> pointing to the authoritative version of this URL.",
            evidence=None,
        )
    if canonical.is_empty:
        return Finding(
            rule_id="canonical-url",
            title="Canonical URL Tag",
            status="issue",
            explanation="Canonical link tag is present but href attribute is empty.",
            recommendation="Provide the absolute authoritative URL in the canonical href attribute.",
            evidence='<link rel="canonical" href="">',
        )

    if canonical.count > 1:
        return Finding(
            rule_id="canonical-url",
            title="Canonical URL Tag",
            status="warning",
            explanation=f"Multiple canonical tags ({canonical.count}) detected. Search engines may disregard conflicting canonical directives.",
            recommendation="Remove duplicate canonical tags to leave a single unambiguous canonical URL.",
            evidence=canonical.resolved_url,
        )

    if canonical.is_self_referential:
        return Finding(
            rule_id="canonical-url",
            title="Canonical URL Tag",
            status="pass",
            explanation="Canonical link is correctly configured and self-referential to the current URL.",
            evidence=canonical.resolved_url,
        )
    else:
        return Finding(
            rule_id="canonical-url",
            title="Canonical URL Tag",
            status="warning",
            explanation=f"Canonical link points to an alternative URL ({canonical.resolved_url}) rather than itself.",
            recommendation="Verify that pointing canonical authority to a different URL is intentional.",
            evidence=f"Current: {final_url} | Canonical: {canonical.resolved_url}",
        )


def evaluate_meta_robots(metadata: ExtractedMetadata) -> Finding:
    """Evaluate meta robots indexing directives."""
    robots = metadata.robots
    directives_str = ", ".join(robots.meta_directives) if robots.meta_directives else "none found (default index, follow)"

    if robots.has_meta_noindex:
        return Finding(
            rule_id="meta-robots",
            title="Meta Robots Indexing Directive",
            status="issue",
            explanation="The <meta name='robots'> tag specifies 'noindex' (or 'none'), which instructs search engines NOT to index this page.",
            recommendation="Remove the 'noindex' directive from meta robots if this page should appear in search results.",
            evidence=directives_str,
        )
    else:
        return Finding(
            rule_id="meta-robots",
            title="Meta Robots Indexing Directive",
            status="pass",
            explanation="No 'noindex' directive was found in meta robots tags; page is eligible for search engine indexing.",
            evidence=directives_str,
        )


def evaluate_x_robots_tag(metadata: ExtractedMetadata) -> Finding:
    """Evaluate X-Robots-Tag HTTP response header."""
    robots = metadata.robots
    directives_str = ", ".join(robots.x_robots_directives) if robots.x_robots_directives else "Header not present"

    if robots.has_x_noindex:
        return Finding(
            rule_id="x-robots-tag",
            title="X-Robots-Tag Header Directive",
            status="issue",
            explanation="The HTTP response contains an 'X-Robots-Tag' header with a 'noindex' directive, blocking search engine indexation.",
            recommendation="Remove the 'noindex' directive from web server response headers if this page is intended for search indexation.",
            evidence=directives_str,
        )
    else:
        return Finding(
            rule_id="x-robots-tag",
            title="X-Robots-Tag Header Directive",
            status="pass",
            explanation="No 'noindex' directive detected in HTTP response X-Robots-Tag header.",
            evidence=directives_str,
        )


def evaluate_content_type(fetch_res: FetchResult) -> Finding:
    """Evaluate response MIME type and fetch integrity."""
    ct = fetch_res.content_type

    if not ct:
        return Finding(
            rule_id="content-type",
            title="Content-Type & HTML Validity",
            status="warning",
            explanation="Server did not return a Content-Type HTTP header.",
            recommendation="Configure the web server to declare an explicit Content-Type header (e.g. text/html; charset=utf-8).",
            evidence=None,
        )
    elif not fetch_res.is_html:
        return Finding(
            rule_id="content-type",
            title="Content-Type & HTML Validity",
            status="issue",
            explanation=f"Response Content-Type is '{ct}'. Technical SEO checks require HTML content.",
            recommendation="Verify that this URL is intended to serve an HTML document rather than a binary or media file.",
            evidence=ct,
        )
    else:
        return Finding(
            rule_id="content-type",
            title="Content-Type & HTML Validity",
            status="pass",
            explanation=f"Valid HTML Content-Type header detected ({ct}).",
            evidence=ct,
        )


def evaluate_all_rules(fetch_res: FetchResult, metadata: ExtractedMetadata) -> list[Finding]:
    """Execute all 8 SEO audit rules and return structured findings."""
    return [
        evaluate_http_status(fetch_res),
        evaluate_redirect_chain(fetch_res),
        evaluate_page_title(metadata),
        evaluate_meta_description(metadata),
        evaluate_canonical_link(metadata, fetch_res.final_url),
        evaluate_meta_robots(metadata),
        evaluate_x_robots_tag(metadata),
        evaluate_content_type(fetch_res),
    ]
