"""Generic fallback adapter: no curated selectors, so these tests exercise the
heuristics themselves (largest chapter-link cluster; readability-lxml content
extraction) rather than a fixed selector contract."""
from __future__ import annotations

from app.core.adapters.base import ChapterRef
from app.core.adapters.generic import GenericAdapter

from support import FixtureFetcher, load_fixture


def test_matches_any_http_url_but_not_garbage():
    assert GenericAdapter.matches("https://some-random-webnovel-site.example/toc/123") is True
    assert GenericAdapter.matches("not a url") is False


async def test_finds_largest_chapter_link_cluster_and_ignores_nav():
    url = "https://example.test/novel/test-novel"
    fetcher = FixtureFetcher({url: load_fixture("generic", "toc.html")})
    adapter = GenericAdapter()

    result = await adapter.fetch_novel(fetcher, url)

    assert result.meta.title == "Test Novel"
    assert result.meta.cover_url == "https://example.test/covers/test-novel.jpg"
    assert len(result.chapters) == 6
    assert all("/chapter/" in c.url for c in result.chapters)


async def test_no_chapter_list_found_reports_note_and_no_chapters():
    url = "https://example.test/novel/empty"
    fetcher = FixtureFetcher({url: load_fixture("generic", "no_toc.html")})
    adapter = GenericAdapter()

    result = await adapter.fetch_novel(fetcher, url)

    assert result.chapters == []
    assert "no chapter list" in result.note.lower()


async def test_fetch_chapter_extracts_main_content_over_boilerplate():
    adapter = GenericAdapter()
    ref = ChapterRef(
        number=1, url="https://example.test/novel/test-novel/chapter/1",
        title="Chapter 1: The Beginning",
    )
    fetcher = FixtureFetcher({ref.url: load_fixture("generic", "chapter.html")})

    content = await adapter.fetch_chapter(fetcher, ref)

    assert content.title == "Chapter 1: The Beginning"
    assert content.html.count("<p>") == 3
    assert "Copyright" not in content.html
    assert "Home" not in content.html


# Confirmed against a real headless Chromium run (not just this fake): see the
# "smoke test" note in CHANGELOG v0.5.0 — this reproduces the same shell/rendered
# shapes against FixtureFetcher so the auto-detect branch has automated coverage
# without every test run needing a real browser.
_JS_SHELL_HTML = '<html><body><div id="root"></div><script>var bootstrap = "app";</script></body></html>'
_RENDERED_HTML = (
    "<html><body><div id=\"root\">"
    "<h1>Chapter 1: Rendered</h1>"
    "<p>This text only exists once JavaScript has run in a real browser, since the raw "
    "HTML response is just an empty shell before the script populates it.</p>"
    "<p>A second paragraph of the actual chapter content goes here as well, long enough "
    "that this whole page clearly reads as real, fully-loaded prose rather than a shell.</p>"
    "</div></body></html>"
)


def test_looks_like_js_shell_detects_empty_and_full_pages():
    assert GenericAdapter._looks_like_js_shell(_JS_SHELL_HTML) is True
    assert GenericAdapter._looks_like_js_shell(_RENDERED_HTML) is False


async def test_fetch_chapter_falls_back_to_render_for_js_shell():
    adapter = GenericAdapter()
    ref = ChapterRef(number=1, url="https://example.test/novel/test-novel/chapter/1")
    fetcher = FixtureFetcher({ref.url: _JS_SHELL_HTML})
    fetcher.register_rendered(ref.url, _RENDERED_HTML)

    content = await adapter.fetch_chapter(fetcher, ref)

    assert content.title == "Chapter 1: Rendered"
    assert content.html.count("<p>") == 2


async def test_fetch_chapter_skips_render_when_static_content_is_sufficient():
    adapter = GenericAdapter()
    ref = ChapterRef(number=1, url="https://example.test/novel/test-novel/chapter/1")
    # No rendered route registered at all - if the code wrongly called get_rendered()
    # here, FixtureFetcher would raise, failing this test.
    fetcher = FixtureFetcher({ref.url: load_fixture("generic", "chapter.html")})

    content = await adapter.fetch_chapter(fetcher, ref)

    assert content.html.count("<p>") == 3


_RENDERED_TOC_HTML = (
    "<html><body><h1>JS Novel</h1><div class=\"chapter-list\">"
    + "".join(f'<a href="/novel/js-novel/chapter/{n}">Chapter {n}</a>' for n in range(1, 7))
    + "</div></body></html>"
)


async def test_fetch_novel_falls_back_to_render_when_toc_is_a_js_shell():
    url = "https://example.test/novel/js-novel"
    adapter = GenericAdapter()
    fetcher = FixtureFetcher({url: _JS_SHELL_HTML})
    fetcher.register_rendered(url, _RENDERED_TOC_HTML)

    result = await adapter.fetch_novel(fetcher, url)

    assert result.meta.title == "JS Novel"
    assert len(result.chapters) == 6


async def test_fetch_novel_skips_render_when_toc_already_parsed():
    # toc.html's own visible text is short (mostly link titles), but chapters are found
    # from the static HTML alone - render must never be attempted, or FixtureFetcher
    # (no rendered route registered here) would raise and fail this test.
    url = "https://example.test/novel/test-novel"
    fetcher = FixtureFetcher({url: load_fixture("generic", "toc.html")})
    adapter = GenericAdapter()

    result = await adapter.fetch_novel(fetcher, url)

    assert len(result.chapters) == 6
