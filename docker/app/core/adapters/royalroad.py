"""Curated adapter for Royal Road (royalroad.com).

Royal Road hosts original fiction published free by its authors, so it is the most
clearly legitimate source we scrape (ADR 0004 still applies: personal use, rate-limited,
robots-aware — robots.txt only disallows vote/review paths for generic agents).

Structure, confirmed 2026-07:
  search        GET /fictions/search?title=<q>   rows=.fiction-list-item,
                                                  title=h2.fiction-title a,
                                                  cover=img[data-type=cover],
                                                  "<N> Chapters" in the row's stats
  fiction page  /fiction/<id>/<slug>             title=h1, author=meta[property=books:author],
                                                  cover=img[data-type=cover],
                                                  synopsis=.description,
                                                  TOC=tr.chapter-row[data-url] (full, unpaginated)
  chapter page  /fiction/<id>/<slug>/chapter/<cid>/<cslug>  body=.chapter-inner.chapter-content

Chapter pages sometimes carry an injected anti-theft paragraph hidden with a
randomly-named CSS class declared ``display: none`` in an inline <style> block; those
elements are stripped before the generic cleaner runs.
"""
from __future__ import annotations

import re
from urllib.parse import quote_plus, urljoin, urlparse

from bs4 import BeautifulSoup

from ..clean import clean_chapter_html
from ..fetch import Fetcher
from .base import Adapter, ChapterContent, ChapterRef, NovelMeta, NovelResult, SearchResult

HOST = "https://www.royalroad.com"
_HOST_RE = re.compile(r"(^|\.)royalroad\.com$", re.I)
_FICTION_RE = re.compile(r"/fiction/(\d+)(?:/([^/?#]+))?")
_CHAPTERS_STAT_RE = re.compile(r"([\d,]+)\s+Chapters", re.I)
_HIDDEN_CLASS_RE = re.compile(r"\.([\w-]+)\s*\{[^}]*display\s*:\s*none", re.I)


class RoyalRoadAdapter(Adapter):
    name = "royalroad"
    needs_render = False
    searchable = True
    cover_hosts = ("royalroadcdn.com",)

    @classmethod
    def matches(cls, url: str) -> bool:
        return bool(_HOST_RE.search(urlparse(url).netloc)) and "/fiction" in urlparse(url).path

    async def search(self, fetcher: Fetcher, query: str) -> list[SearchResult]:
        resp = await fetcher.get(f"{HOST}/fictions/search?title={quote_plus(query)}")
        soup = BeautifulSoup(resp.text, "html.parser")
        results: list[SearchResult] = []
        for row in soup.select(".fiction-list-item"):
            link = row.select_one("h2.fiction-title a[href*='/fiction/']")
            if link is None:
                continue
            title = link.get_text(strip=True)
            href = link.get("href", "")
            if not title or not href:
                continue

            cover = None
            img = row.select_one("img[data-type=cover]")
            if img is not None and img.get("src"):
                cover = urljoin(HOST, img["src"])

            chapters = None
            m = _CHAPTERS_STAT_RE.search(row.get_text(" ", strip=True))
            if m:
                chapters = int(m.group(1).replace(",", ""))

            results.append(
                SearchResult(
                    title=title, url=urljoin(HOST, href), source=self.name,
                    cover_url=cover, chapters=chapters,
                )
            )
            if len(results) >= 25:
                break
        return results

    async def fetch_novel(self, fetcher: Fetcher, url: str) -> NovelResult:
        m = _FICTION_RE.search(urlparse(url).path)
        if not m:
            raise ValueError(f"Not a recognizable Royal Road fiction URL: {url}")
        soup = BeautifulSoup((await fetcher.get(url)).text, "html.parser")

        title_el = soup.select_one(".fic-header h1") or soup.select_one("h1")
        title = title_el.get_text(strip=True) if title_el else m.group(2) or f"fiction-{m.group(1)}"

        author_meta = soup.select_one('meta[property="books:author"]')
        author = author_meta["content"].strip() if author_meta and author_meta.get("content") else "Unknown"

        cover = None
        img = soup.select_one("img[data-type=cover]")
        if img is not None and img.get("src"):
            cover = urljoin(HOST, img["src"])

        desc_el = soup.select_one(".description") or soup.select_one('meta[property="og:description"]')
        synopsis = ""
        if desc_el:
            synopsis = desc_el.get("content") if desc_el.name == "meta" else desc_el.get_text(" ", strip=True)

        # The fiction page carries the complete TOC as table rows — no pagination.
        chapters: list[ChapterRef] = []
        for i, tr in enumerate(soup.select("tr.chapter-row[data-url]"), start=1):
            ch_link = tr.select_one("a[href*='/chapter/']")
            chapters.append(
                ChapterRef(
                    number=i,
                    url=urljoin(HOST, tr["data-url"]),
                    title=ch_link.get_text(strip=True) if ch_link else "",
                )
            )

        meta = NovelMeta(
            title=title, source_url=urljoin(HOST, f"/fiction/{m.group(1)}/{m.group(2) or ''}"),
            author=author, cover_url=cover, synopsis=synopsis,
        )
        return NovelResult(meta=meta, chapters=chapters)

    async def fetch_chapter(self, fetcher: Fetcher, ref: ChapterRef) -> ChapterContent:
        soup = BeautifulSoup((await fetcher.get(ref.url)).text, "html.parser")

        title_el = soup.select_one(".fic-header h1") or soup.select_one("h1")
        title = title_el.get_text(strip=True) if title_el else (ref.title or f"Chapter {ref.number}")

        body_el = soup.select_one(".chapter-inner.chapter-content") or soup.select_one(".chapter-content")
        if body_el is None:
            return ChapterContent(title=title, html="")

        # Strip anti-theft paragraphs: classes declared display:none in inline styles.
        hidden = set()
        for st in soup.find_all("style"):
            hidden.update(_HIDDEN_CLASS_RE.findall(st.get_text() or ""))
        if hidden:
            for el in body_el.find_all(True):
                # attrs is None once an ancestor was decomposed earlier in this loop
                if el.attrs and hidden.intersection(el.get("class") or []):
                    el.decompose()

        return ChapterContent(title=title, html=clean_chapter_html(body_el))
