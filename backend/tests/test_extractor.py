from app.engine.extractor import extract_seo_metadata
from app.engine.fetcher import FetchResult


def make_fetch_result(
    body: str,
    headers: dict | None = None,
    final_url: str = "https://example.com/page",
    is_html: bool = True,
    status_code: int = 200,
) -> FetchResult:
    return FetchResult(
        initial_url="https://example.com/page",
        final_url=final_url,
        status_code=status_code,
        status_text="OK",
        headers=headers or {"content-type": "text/html; charset=utf-8"},
        body=body,
        raw_bytes_count=len(body.encode("utf-8")),
        content_type="text/html",
        fetch_duration_ms=100,
        redirect_count=0,
        is_html=is_html,
    )


def test_extractor_full_metadata():
    html = """
    <!DOCTYPE html>
    <html>
      <head>
        <title>   Holy Space - Official Music Platform  </title>
        <meta name="description" content="Stream and discover uplifting Christian music and praise songs on Holy Space." />
        <link rel="canonical" href="https://example.com/page" />
        <meta name="robots" content="index, follow" />
      </head>
      <body>
        <h1>Welcome</h1>
      </body>
    </html>
    """
    res = make_fetch_result(html, headers={"x-robots-tag": "all"})
    meta = extract_seo_metadata(res)

    assert meta.title.is_missing is False
    assert meta.title.is_empty is False
    assert meta.title.text == "Holy Space - Official Music Platform"
    assert meta.title.count == 1

    assert meta.description.is_missing is False
    assert meta.description.is_empty is False
    assert "Stream and discover" in meta.description.text
    assert meta.description.count == 1

    assert meta.canonical.is_missing is False
    assert meta.canonical.is_empty is False
    assert meta.canonical.is_self_referential is True
    assert meta.canonical.resolved_url == "https://example.com/page"

    assert meta.robots.has_meta_noindex is False
    assert meta.robots.has_x_noindex is False
    assert meta.robots.has_any_noindex is False


def test_extractor_missing_and_empty_title():
    # Missing title
    meta_missing = extract_seo_metadata(make_fetch_result("<html><head></head><body></body></html>"))
    assert meta_missing.title.is_missing is True
    assert meta_missing.title.text is None

    # Empty whitespace title
    meta_empty = extract_seo_metadata(make_fetch_result("<html><head><title>   </title></head></html>"))
    assert meta_empty.title.is_missing is False
    assert meta_empty.title.is_empty is True
    assert meta_empty.title.text is None


def test_extractor_missing_and_empty_description():
    # Missing description
    meta_missing = extract_seo_metadata(make_fetch_result("<html><head><title>A</title></head></html>"))
    assert meta_missing.description.is_missing is True
    assert meta_missing.description.text is None

    # Empty content
    meta_empty = extract_seo_metadata(
        make_fetch_result('<html><head><meta name="description" content="   " /></head></html>')
    )
    assert meta_empty.description.is_missing is False
    assert meta_empty.description.is_empty is True
    assert meta_empty.description.text is None


def test_extractor_relative_and_external_canonical():
    # Relative canonical href resolved against final_url
    html_rel = '<html><head><link rel="canonical" href="/subpath" /></head></html>'
    meta_rel = extract_seo_metadata(make_fetch_result(html_rel, final_url="https://example.com/item/1"))
    assert meta_rel.canonical.resolved_url == "https://example.com/subpath"
    assert meta_rel.canonical.is_self_referential is False

    # Self-referential canonical
    html_self = '<html><head><link rel="canonical" href="https://example.com/item/1/" /></head></html>'
    meta_self = extract_seo_metadata(make_fetch_result(html_self, final_url="https://example.com/item/1"))
    assert meta_self.canonical.is_self_referential is True


def test_extractor_meta_robots_noindex_and_none():
    html_noindex = '<html><head><meta name="robots" content="noindex, nofollow" /></head></html>'
    meta_noindex = extract_seo_metadata(make_fetch_result(html_noindex))
    assert meta_noindex.robots.has_meta_noindex is True
    assert meta_noindex.robots.has_any_noindex is True

    html_none = '<html><head><meta name="googlebot" content="none" /></head></html>'
    meta_none = extract_seo_metadata(make_fetch_result(html_none))
    assert meta_none.robots.has_meta_noindex is True
    assert meta_none.robots.has_any_noindex is True


def test_extractor_x_robots_tag_header():
    res = make_fetch_result("<html></html>", headers={"x-robots-tag": "noindex, noarchive"})
    meta = extract_seo_metadata(res)
    assert meta.robots.has_x_noindex is True
    assert meta.robots.has_any_noindex is True
    assert "noindex" in meta.robots.x_robots_directives


def test_extractor_duplicate_tags():
    html = """
    <html>
      <head>
        <title>First Title</title>
        <title>Second Title</title>
        <meta name="description" content="First Description" />
        <meta name="description" content="Second Description" />
        <link rel="canonical" href="https://example.com/1" />
        <link rel="canonical" href="https://example.com/2" />
      </head>
    </html>
    """
    meta = extract_seo_metadata(make_fetch_result(html))
    assert meta.title.count == 2
    assert meta.title.text == "First Title"
    assert meta.description.count == 2
    assert meta.canonical.count == 2


def test_extractor_malformed_html():
    """Verify parser handles unclosed tags and messy HTML without raising exceptions."""
    malformed = "<title>Unclosed Title<meta name=description content='Missing quotes><p>Broken"
    meta = extract_seo_metadata(make_fetch_result(malformed))
    assert meta.title.count >= 1
