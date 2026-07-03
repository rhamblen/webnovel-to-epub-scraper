"""Curated adapter for the freewebnovel family of sites.

The public `.com` host sits behind a Cloudflare JS challenge that blocks plain HTTP,
but the `.vip` mirror serves the same catalogue as static HTML. This adapter normalizes
any freewebnovel host + path to `https://freewebnovel.vip/freenovel/<slug>` and scrapes
there.

Structure (freewebnovel.vip), confirmed 2026-07:
  novel page    /freenovel/<slug>          title=h1.tit, author=a[href^="/author/"],
                                            cover=.m-imgtxt img, chapters=/chapter-<N>
  chapter page  /freenovel/<slug>/chapter-N  body=#article (<p>), title=h1.tit
The chapter list on the novel page is paginated, so chapters are enumerated 1..N where
N is the highest /chapter-<N> link found on the page.
"""
from __future__ import annotations

import re
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from ..clean import clean_chapter_html
from ..fetch import Fetcher
from .base import Adapter, ChapterContent, ChapterRef, NovelMeta, NovelResult

HOST = "https://freewebnovel.vip"
_HOST_RE = re.compile(r"(^|\.)freewebnovel\.", re.I)
_SLUG_RE = re.compile(r"/(?:free)?novel/([^/?#]+)")
_CHAP_RE = re.compile(r"/chapter-(\d+)\b")


class FreeWebNovelAdapter(Adapter):
    name = "freewebnovel"
    needs_render = False

    @classmethod
    def matches(cls, url: str) -> bool:
        return bool(_HOST_RE.search(urlparse(url).netloc))

    def _slug(self, url: str) -> str:
        m = _SLUG_RE.search(urlparse(url).path)
        if not m:
            raise ValueError(f"Not a recognizable freewebnovel novel URL: {url}")
        return m.group(1)

    def _novel_url(self, slug: str) -> str:
        return f"{HOST}/freenovel/{slug}"

    async def fetch_novel(self, fetcher: Fetcher, url: str) -> NovelResult:
        slug = self._slug(url)
        novel_url = self._novel_url(slug)
        soup = BeautifulSoup((await fetcher.get(novel_url)).text, "html.parser")

        title_el = soup.select_one("h1.tit") or soup.select_one("h1")
        title = title_el.get_text(strip=True) if title_el else slug

        author_el = soup.select_one('a[href^="/author/"], a[href*="/authors/"]')
        author = author_el.get_text(strip=True) if author_el else "Unknown"

        cover_el = soup.select_one(".m-imgtxt img, .pic img")
        cover = None
        if cover_el:
            src = cover_el.get("src") or cover_el.get("data-src")
            cover = urljoin(HOST, src) if src else None

        desc_el = soup.select_one(".m-desc .txt, .inner, meta[name='description']")
        synopsis = ""
        if desc_el:
            synopsis = desc_el.get("content") if desc_el.name == "meta" else desc_el.get_text(" ", strip=True)

        # Enumerate chapters 1..N from the highest /chapter-<N> link on the page.
        max_n = 0
        for a in soup.select('a[href*="/chapter-"]'):
            m = _CHAP_RE.search(a.get("href", ""))
            if m:
                max_n = max(max_n, int(m.group(1)))
        chapters = [
            ChapterRef(number=n, url=f"{novel_url}/chapter-{n}")
            for n in range(1, max_n + 1)
        ]

        meta = NovelMeta(
            title=title, source_url=novel_url, author=author,
            cover_url=cover, synopsis=synopsis,
        )
        return NovelResult(meta=meta, chapters=chapters)

    async def fetch_chapter(self, fetcher: Fetcher, ref: ChapterRef) -> ChapterContent:
        soup = BeautifulSoup((await fetcher.get(ref.url)).text, "html.parser")

        # h1.tit is the *book* title on chapter pages; the chapter heading is span.chapter / h4.
        title_el = soup.select_one("span.chapter") or soup.select_one(".m-read h4, h4")
        title = title_el.get_text(strip=True) if title_el else f"Chapter {ref.number}"

        body_el = soup.select_one("#article") or soup.select_one(".txt")
        html = clean_chapter_html(body_el) if body_el else ""
        return ChapterContent(title=title, html=html)
