"""Adapter interface + shared data types.

An adapter knows how to turn a novel URL into (metadata + ordered chapter list) and a
chapter URL into (title + body). Fetching/politeness is handled by the ``Fetcher`` that
is passed in, so adapters stay thin.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from ..fetch import Fetcher


@dataclass
class NovelMeta:
    title: str
    source_url: str
    author: str = "Unknown"
    cover_url: str | None = None
    synopsis: str = ""
    language: str = "en"


@dataclass
class ChapterRef:
    number: int
    url: str
    title: str = ""


@dataclass
class ChapterContent:
    title: str
    html: str  # cleaned <p>...</p> markup


@dataclass
class NovelResult:
    meta: NovelMeta
    chapters: list[ChapterRef] = field(default_factory=list)
    note: str = ""  # surfaced on the Book, e.g. when only some chapters are scrapeable


@dataclass
class SearchResult:
    title: str
    url: str  # the novel page URL to import
    source: str  # adapter name that produced it
    cover_url: str | None = None
    chapters: int | None = None
    author: str = ""
    note: str = ""  # short caveat shown next to the result, e.g. "25 free"


class Adapter(ABC):
    name: str = "base"
    needs_render: bool = False  # True if the site requires a real browser (Playwright)
    searchable: bool = False  # True if the adapter implements search()
    cover_hosts: tuple[str, ...] = ()  # extra hosts cover images may live on (CDNs)
    site_terms: tuple[str, ...] = ()  # brand tokens that may appear as an injected watermark

    @classmethod
    @abstractmethod
    def matches(cls, url: str) -> bool:
        ...

    @abstractmethod
    async def fetch_novel(self, fetcher: Fetcher, url: str) -> NovelResult:
        ...

    @abstractmethod
    async def fetch_chapter(self, fetcher: Fetcher, ref: ChapterRef) -> ChapterContent:
        ...

    async def search(self, fetcher: Fetcher, query: str) -> list[SearchResult]:
        """Search the site by title. Override in adapters that set ``searchable = True``."""
        raise NotImplementedError
