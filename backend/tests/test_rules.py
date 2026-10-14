from app.engine.extractor import (
    CanonicalData,
    DescriptionData,
    ExtractedMetadata,
    RobotsDirectiveData,
    TitleData,
)
from app.engine.fetcher import FetchResult, RedirectHop
from app.engine.rules import (
    evaluate_all_rules,
    evaluate_canonical_link,
    evaluate_content_type,
    evaluate_http_status,
    evaluate_meta_description,
    evaluate_meta_robots,
    evaluate_page_title,
    evaluate_redirect_chain,
    evaluate_x_robots_tag,
)


def mock_fetch(
    status_code: int = 200,
    status_text: str = "OK",
    content_type: str = "text/html",
    redirect_count: int = 0,
    redirect_chain: list | None = None,
    is_html: bool = True,
    final_url: str = "https://example.com/",
) -> FetchResult:
    return FetchResult(
        initial_url="https://example.com/",
        final_url=final_url,
        status_code=status_code,
        status_text=status_text,
        headers={"content-type": content_type},
        body="<html></html>",
        raw_bytes_count=13,
        content_type=content_type,
        fetch_duration_ms=50,
        redirect_count=redirect_count,
        redirect_chain=redirect_chain or [],
        is_html=is_html,
    )


def mock_meta(
    title: str | None = "Good Title Example - 35 Characters Long",
    title_count: int = 1,
    desc: str | None = "This is a comprehensive and optimal meta description providing useful search context for users.",
    desc_count: int = 1,
    canonical_url: str | None = "https://example.com/",
    is_self_ref: bool = True,
    meta_noindex: bool = False,
    x_noindex: bool = False,
) -> ExtractedMetadata:
    return ExtractedMetadata(
        title=TitleData(
            text=title,
            length=len(title) if title else 0,
            count=title_count,
            is_missing=title is None,
            is_empty=title == "",
        ),
        description=DescriptionData(
            text=desc,
            length=len(desc) if desc else 0,
            count=desc_count,
            is_missing=desc is None,
            is_empty=desc == "",
        ),
        canonical=CanonicalData(
            raw_href=canonical_url,
            resolved_url=canonical_url,
            count=1 if canonical_url else 0,
            is_missing=canonical_url is None,
            is_empty=canonical_url == "",
            is_self_referential=is_self_ref,
        ),
        robots=RobotsDirectiveData(
            meta_directives=["noindex"] if meta_noindex else ["index"],
            x_robots_directives=["noindex"] if x_noindex else [],
            has_meta_noindex=meta_noindex,
            has_x_noindex=x_noindex,
            has_any_noindex=meta_noindex or x_noindex,
        ),
    )


class TestRulesEvaluation:
    def test_http_status_rule(self):
        assert evaluate_http_status(mock_fetch(200)).status == "pass"
        assert evaluate_http_status(mock_fetch(302)).status == "warning"
        assert evaluate_http_status(mock_fetch(404)).status == "issue"
        assert evaluate_http_status(mock_fetch(500)).status == "error"

    def test_redirect_chain_rule(self):
        # 0 redirects
        assert evaluate_redirect_chain(mock_fetch(redirect_count=0)).status == "pass"

        # 1 permanent redirect
        hop_301 = [RedirectHop(url="http://example.com", status_code=301, location="https://example.com")]
        assert evaluate_redirect_chain(mock_fetch(redirect_count=1, redirect_chain=hop_301)).status == "pass"

        # 1 temporary redirect
        hop_302 = [RedirectHop(url="http://example.com", status_code=302, location="https://example.com")]
        assert evaluate_redirect_chain(mock_fetch(redirect_count=1, redirect_chain=hop_302)).status == "warning"

        # 2 redirects (chain)
        hops_chain = [
            RedirectHop(url="http://example.com", status_code=301, location="https://example.com"),
            RedirectHop(url="https://example.com", status_code=302, location="https://example.com/en"),
        ]
        assert evaluate_redirect_chain(mock_fetch(redirect_count=2, redirect_chain=hops_chain)).status == "warning"

    def test_page_title_rule(self):
        # Optimal title
        meta_ok = mock_meta(title="Standard Page Title (32 chars)")
        assert evaluate_page_title(meta_ok).status == "pass"

        # Missing title
        meta_missing = mock_meta(title=None)
        assert evaluate_page_title(meta_missing).status == "issue"

        # Empty title
        meta_empty = mock_meta(title="")
        assert evaluate_page_title(meta_empty).status == "issue"

        # Short title (<15 chars)
        meta_short = mock_meta(title="Short")
        assert evaluate_page_title(meta_short).status == "warning"

        # Long title (>70 chars)
        meta_long = mock_meta(title="This title is excessively long and verbose and will definitely be truncated in search results by Google")
        assert evaluate_page_title(meta_long).status == "warning"

        # Multiple titles
        meta_multi = mock_meta(title="Valid Title", title_count=2)
        assert evaluate_page_title(meta_multi).status == "warning"

    def test_meta_description_rule(self):
        # Optimal description
        assert evaluate_meta_description(mock_meta()).status == "pass"

        # Missing description
        assert evaluate_meta_description(mock_meta(desc=None)).status == "issue"

        # Empty description
        assert evaluate_meta_description(mock_meta(desc="")).status == "issue"

        # Short description (<50 chars)
        assert evaluate_meta_description(mock_meta(desc="Too brief summary.")).status == "warning"

        # Long description (>165 chars)
        long_desc = "X" * 180
        assert evaluate_meta_description(mock_meta(desc=long_desc)).status == "warning"

    def test_canonical_link_rule(self):
        # Self referential canonical
        assert evaluate_canonical_link(mock_meta(), "https://example.com/").status == "pass"

        # Missing canonical
        assert evaluate_canonical_link(mock_meta(canonical_url=None), "https://example.com/").status == "warning"

        # Empty canonical
        assert evaluate_canonical_link(mock_meta(canonical_url=""), "https://example.com/").status == "issue"

        # External canonical
        meta_ext = mock_meta(canonical_url="https://other.com/target", is_self_ref=False)
        assert evaluate_canonical_link(meta_ext, "https://example.com/").status == "warning"

    def test_meta_robots_rule(self):
        assert evaluate_meta_robots(mock_meta(meta_noindex=False)).status == "pass"
        assert evaluate_meta_robots(mock_meta(meta_noindex=True)).status == "issue"

    def test_x_robots_tag_rule(self):
        assert evaluate_x_robots_tag(mock_meta(x_noindex=False)).status == "pass"
        assert evaluate_x_robots_tag(mock_meta(x_noindex=True)).status == "issue"

    def test_content_type_rule(self):
        assert evaluate_content_type(mock_fetch(content_type="text/html; charset=utf-8", is_html=True)).status == "pass"
        assert evaluate_content_type(mock_fetch(content_type="application/pdf", is_html=False)).status == "issue"
        assert evaluate_content_type(mock_fetch(content_type="", is_html=False)).status == "warning"

    def test_evaluate_all_rules_returns_8_rules(self):
        findings = evaluate_all_rules(mock_fetch(), mock_meta())
        assert len(findings) == 8
        rule_ids = [f.rule_id for f in findings]
        assert rule_ids == [
            "http-status",
            "redirect-chain",
            "page-title",
            "meta-description",
            "canonical-url",
            "meta-robots",
            "x-robots-tag",
            "content-type",
        ]
