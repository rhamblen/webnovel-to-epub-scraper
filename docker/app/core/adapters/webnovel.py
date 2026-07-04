"""Curated adapter for webnovel.com (Qidian's official platform).

Most webnovel.com titles gate later chapters behind an in-app purchase, which stays
out of scope per ADR 0004 (personal use, no paywalled sources). But a prefix of
chapters — however many the author/platform made free, sometimes zero, sometimes
dozens — is served to any anonymous visitor with no login and no charge. This adapter
imports and scrapes *only* that free prefix and stops cleanly at the paywall boundary;
it never attempts to log in, pay, or otherwise access a locked chapter.

Both the book page and each chapter page embed their data as a plain JS object literal
(``g_data.book= {...}`` / ``var chapInfo= {...}``) rather than through ``JSON.parse``,
so the site escapes punctuation in string values with stray backslashes (``\\<``, ``\\ ``,
``\\'``) that are meaningless no-ops to a JS engine but invalid JSON escapes. Normalizing
them to bare characters — exactly what a browser's JS engine already does when it
evaluates that literal — turns the blob into valid JSON. This is just correctly parsing
data the site already sends to any visitor, the same category of work as reading HTML.

Structure, confirmed 2026-07:
  search       GET /search?keywords=<q>        rows: a[href^="/book/"][data-bookid]
  book page    /book/<id>                       g_data.book= {bookInfo:{...}, volumeItems:
                                                 [{chapterItems:[{chapterId, chapterIndex,
                                                 chapterName, isVip}, ...]}, ...]}
                                                 isVip == 0 -> free; nonzero -> paywalled.
  chapter page /book/<id>/<chapterId>            var chapInfo= {chapterInfo:{vipStatus,
                                                 price, chapterName, contents:[{content}]}}
                                                 vipStatus/price both 0 confirms free.

Per-chapter vipStatus/price is re-checked at fetch time (not just trusted from the book
page's isVip) as a safety net — a chapter must never be scraped unless the source itself
is currently serving it unlocked.
"""
from __future__ import annotations

import json
import re
from urllib.parse import quote_plus, urlparse

from ..clean import clean_chapter_html
from ..fetch import Fetcher
from .base import Adapter, ChapterContent, ChapterRef, NovelMeta, NovelResult, SearchResult

HOST = "https://www.webnovel.com"
_BOOK_ID_RE = re.compile(r"/book/(?:[^/?#]*_)?(\d+)")
_FREE = (0, "0", 0.0)

# How many top search results get a book-page fetch to fill in free/total chapter counts.
_ENRICH_TOP_N = 3

# A backslash not starting a *valid* JSON escape is a JS-literal no-op; dropping it
# (keeping just the following character) is what a JS engine would already resolve it to.
_UNESCAPE_RE = re.compile(r'\\(?!["\\/bfnrtu])(.)')


def _cover_url(book_id: str) -> str:
    return f"https://book-pic.webnovel.com/bookcover/{book_id}"


def _extract_balanced_object(text: str, start: int) -> str:
    """Return the ``{...}`` substring starting at ``start``, respecting string quoting."""
    depth = 0
    in_str = False
    i = start
    n = len(text)
    while i < n:
        c = text[i]
        if in_str:
            if c == "\\":
                i += 2
                continue
            if c == '"':
                in_str = False
        else:
            if c == '"':
                in_str = True
            elif c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    return text[start:i + 1]
        i += 1
    raise ValueError("unbalanced JS object literal")


def _extract_js_object(html: str, var_marker: str) -> dict:
    i = html.find(var_marker)
    if i == -1:
        raise ValueError(f"expected data block not found on page ({var_marker!r})")
    start = html.index("{", i)
    raw = _extract_balanced_object(html, start)
    return json.loads(_UNESCAPE_RE.sub(r"\1", raw))


def _free_chapter_items(book_state: dict) -> tuple[list[dict], int]:
    """Return (free chapter items sorted by index, total chapter count)."""
    all_items = [
        ci
        for vol in book_state.get("volumeItems", [])
        for ci in vol.get("chapterItems", [])
    ]
    free = [ci for ci in all_items if ci.get("isVip") in _FREE]
    free.sort(key=lambda ci: ci.get("chapterIndex", 0))
    return free, len(all_items)


class WebnovelAdapter(Adapter):
    name = "webnovel"
    needs_render = False
    searchable = True
    cover_hosts = ("book-pic.webnovel.com",)

    @classmethod
    def matches(cls, url: str) -> bool:
        return bool(re.search(r"(^|\.)webnovel\.com$", urlparse(url).netloc, re.I))

    async def search(self, fetcher: Fetcher, query: str) -> list[SearchResult]:
        from bs4 import BeautifulSoup

        resp = await fetcher.get(f"{HOST}/search?keywords={quote_plus(query)}")
        soup = BeautifulSoup(resp.text, "html.parser")
        results: list[SearchResult] = []
        seen: set[str] = set()
        for a in soup.select('a[href^="/book/"][data-bookid]'):
            book_id = a.get("data-bookid", "")
            title = a.get("title") or a.get("data-bookname") or a.get_text(strip=True)
            if not book_id or not title or book_id in seen:
                continue
            seen.add(book_id)
            results.append(
                SearchResult(
                    title=title, url=f"{HOST}/book/{book_id}", source=self.name,
                    cover_url=_cover_url(book_id),
                )
            )
            if len(results) >= 10:
                break

        for r in results[:_ENRICH_TOP_N]:
            try:
                book_id = _BOOK_ID_RE.search(urlparse(r.url).path).group(1)
                state = _extract_js_object((await fetcher.get(r.url)).text, "g_data.book=")
                free, total = _free_chapter_items(state)
                if total:
                    r.chapters = total
                    r.note = "all free" if len(free) == total else f"{len(free)} free"
            except Exception:
                pass  # counts are best-effort garnish
        return results

    async def fetch_novel(self, fetcher: Fetcher, url: str) -> NovelResult:
        m = _BOOK_ID_RE.search(urlparse(url).path)
        if not m:
            raise ValueError(f"Not a recognizable webnovel.com book URL: {url}")
        book_id = m.group(1)
        book_url = f"{HOST}/book/{book_id}"

        state = _extract_js_object((await fetcher.get(book_url)).text, "g_data.book=")
        info = state.get("bookInfo", {})
        free, total = _free_chapter_items(state)

        chapters = [
            ChapterRef(
                number=ci.get("chapterIndex", i),
                url=f"{book_url}/{ci['chapterId']}",
                title=ci.get("chapterName", ""),
            )
            for i, ci in enumerate(free, start=1)
        ]

        note = ""
        if total == 0:
            note = "No chapters found on webnovel.com for this book."
        elif len(chapters) < total:
            note = (
                f"Only {len(chapters)} of {total} chapters are free on webnovel.com; "
                "the rest require an in-app purchase and are not scraped."
            )

        meta = NovelMeta(
            title=info.get("bookName") or book_id,
            source_url=book_url,
            author=info.get("authorName") or "Unknown",
            cover_url=_cover_url(book_id),
            synopsis=info.get("description", ""),
        )
        return NovelResult(meta=meta, chapters=chapters, note=note)

    async def fetch_chapter(self, fetcher: Fetcher, ref: ChapterRef) -> ChapterContent:
        state = _extract_js_object((await fetcher.get(ref.url)).text, "var chapInfo=")
        info = state.get("chapterInfo", {})

        if info.get("vipStatus") not in _FREE or info.get("price") not in _FREE:
            # Defense in depth: never scrape a chapter the source itself marks as locked,
            # even if it looked free when fetch_novel last enumerated the book.
            raise ValueError(f"Chapter {ref.number} is now locked upstream — not scraped.")

        title = info.get("chapterName") or ref.title or f"Chapter {ref.number}"
        body_html = "\n".join(c.get("content", "") for c in info.get("contents", []))
        return ChapterContent(title=title, html=clean_chapter_html(body_html))
