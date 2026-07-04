"""Generic fallback adapter for sites without a curated adapter (Phase 4).

Heuristic and best-effort by design (ADR 0003) — no site-specific selectors, so it never
needs touching when a *particular* site changes; quality just varies. It's appended last
in the registry and matches any absolute http(s) URL, so `get_adapter` always returns
something. That "matches anything" property means it must never participate in the
`/cover` proxy allowlist (see `Adapter.is_fallback` / `adapters.cover_url_allowed`) — doing
so would turn that route into an open proxy for arbitrary URLs. Its cover guesses (from
`og:image`) still reach the built EPUB fine, since EPUB cover embedding fetches
`Book.cover_path` directly server-side rather than through that route.

Three heuristics, matching ADR 0003's "heuristic TOC discovery + main-content extraction"
plus its "Playwright invoked... when the generic path flags a site as JS-required":

- **TOC discovery:** group every `<a href>` on the page by its parent element. A real
  chapter list is reliably the single largest cluster of sibling links on the page, so
  take the biggest group — filtered to ones that are either largely chapter-shaped
  (text/href matching "chapter 12", "ch. 12", or a bare number) or just very large, since
  some sites title chapters with no chapter marker at all (e.g. "The Awakening").
  Chapters are numbered in DOM order, which is usually oldest-first; a newest-first TOC
  will come out reversed — a known best-effort limitation surfaced via `NovelResult.note`.
- **Chapter body:** readability-lxml's `Document.summary()` scores blocks by text density
  (nav/ads/footers score low) and returns the best one — exactly the generic "main
  content" heuristic the ADR calls for.
- **JS-rendered sites:** unlike a curated adapter (which knows upfront whether its one
  site needs a browser, via the static `needs_render` flag), the generic path handles
  arbitrary unknown sites, so it detects this at runtime instead. The two page kinds need
  different checks, since a real TOC page is link-dense but often prose-*sparse* (short
  chapter titles, little else) while a real chapter page is prose-dense:
  - Chapter body: fetch statically first; if the page's visible text is suspiciously
    short — an empty `<div id="root">`-style shell whose real content hasn't run yet —
    retry the same URL through `Fetcher.get_rendered` (Playwright) before extracting.
  - TOC/novel page: extract chapter links from the static HTML *first*; only if that
    comes up empty *and* the page looks shell-like does it retry via rendering. Checking
    text length up front (like the chapter case) would misfire on any real, fully-loaded
    TOC page whose content is mostly short links rather than prose.
  Either way, cheap static sites never pay the browser-launch cost; JS-heavy ones still
  come out readable.
"""
from __future__ import annotations

import re
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup, Tag
from readability import Document

from ..clean import clean_chapter_html
from ..fetch import Fetcher
from .base import Adapter, ChapterContent, ChapterRef, NovelMeta, NovelResult

# "Chapter 12", "Ch. 12", "ch12", or a bare/hash-prefixed number like "12" / "#12".
_CHAPTER_WORD_RE = re.compile(r"\bch(?:apter|\.)?\s*\d+\b|^#?\d+\b", re.I)
_MIN_CHAPTER_LINKS = 5  # a group smaller than this isn't trustworthy as a TOC
_LARGE_CLUSTER = 10  # a cluster at least this big is trusted even with no keyword match
_JS_SHELL_MIN_TEXT = 200  # visible text shorter than this looks like an unrendered JS shell

_NO_TOC_NOTE = "Generic fallback found no chapter list on this page; nothing to import."
_BEST_EFFORT_NOTE = (
    "Generic fallback: no dedicated adapter for this site. Chapter order and text "
    "quality are best-effort — check that the first and last chapter look right."
)


class GenericAdapter(Adapter):
    name = "generic"
    needs_render = False  # decided dynamically per-page instead — see _get_html
    searchable = False
    is_fallback = True

    @classmethod
    def matches(cls, url: str) -> bool:
        parts = urlparse(url)
        return parts.scheme in ("http", "https") and bool(parts.netloc)

    async def _get_html(self, fetcher: Fetcher, url: str) -> str:
        """Static fetch first; only pay for a real browser if the page looks unrendered."""
        html = (await fetcher.get(url)).text
        if self._looks_like_js_shell(html):
            html = (await fetcher.get_rendered(url)).text
        return html

    @staticmethod
    def _looks_like_js_shell(html: str) -> bool:
        text = BeautifulSoup(html, "html.parser").get_text(strip=True)
        return len(text) < _JS_SHELL_MIN_TEXT

    async def fetch_novel(self, fetcher: Fetcher, url: str) -> NovelResult:
        html = (await fetcher.get(url)).text
        soup = BeautifulSoup(html, "html.parser")
        chapters = self._find_chapter_links(soup, url)

        if not chapters and self._looks_like_js_shell(html):
            # Found nothing and the page looks unrendered - try a real browser once
            # before concluding this novel genuinely has no chapter list.
            html = (await fetcher.get_rendered(url)).text
            soup = BeautifulSoup(html, "html.parser")
            chapters = self._find_chapter_links(soup, url)

        title_el = soup.select_one("h1") or soup.select_one("title")
        title = title_el.get_text(strip=True) if title_el else url

        author = "Unknown"
        author_meta = soup.select_one('meta[name="author"]')
        if author_meta and author_meta.get("content"):
            author = author_meta["content"].strip()

        cover = None
        cover_el = soup.select_one('meta[property="og:image"]') or soup.select_one('link[rel="image_src"]')
        if cover_el:
            src = cover_el.get("content") or cover_el.get("href")
            if src:
                cover = urljoin(url, src)

        synopsis = ""
        desc_el = soup.select_one('meta[name="description"]') or soup.select_one('meta[property="og:description"]')
        if desc_el and desc_el.get("content"):
            synopsis = desc_el["content"].strip()

        note = _BEST_EFFORT_NOTE if chapters else _NO_TOC_NOTE
        meta = NovelMeta(title=title, source_url=url, author=author, cover_url=cover, synopsis=synopsis)
        return NovelResult(meta=meta, chapters=chapters, note=note)

    def _find_chapter_links(self, soup: BeautifulSoup, base_url: str) -> list[ChapterRef]:
        groups: dict[int, list[Tag]] = {}
        for a in soup.find_all("a", href=True):
            if not a.get_text(strip=True):
                continue
            groups.setdefault(id(a.parent), []).append(a)

        candidates = []
        for members in groups.values():
            if len(members) < _MIN_CHAPTER_LINKS:
                continue
            keyword_hits = sum(
                1 for a in members
                if _CHAPTER_WORD_RE.search(a.get_text(strip=True)) or _CHAPTER_WORD_RE.search(a["href"])
            )
            if keyword_hits >= len(members) / 2 or len(members) >= _LARGE_CLUSTER:
                candidates.append(members)
        if not candidates:
            return []

        chapters: list[ChapterRef] = []
        seen: set[str] = set()
        for a in max(candidates, key=len):
            href = urljoin(base_url, a["href"])
            if href in seen:
                continue
            seen.add(href)
            chapters.append(ChapterRef(number=len(chapters) + 1, url=href, title=a.get_text(strip=True)))
        return chapters

    async def fetch_chapter(self, fetcher: Fetcher, ref: ChapterRef) -> ChapterContent:
        html = await self._get_html(fetcher, ref.url)
        doc = Document(html)
        summary = BeautifulSoup(doc.summary(html_partial=True), "html.parser")

        heading = summary.find(["h1", "h2"])
        title = (
            ref.title
            or (heading.get_text(strip=True) if heading else "")
            or doc.short_title()
            or f"Chapter {ref.number}"
        )
        return ChapterContent(title=title, html=clean_chapter_html(summary))
