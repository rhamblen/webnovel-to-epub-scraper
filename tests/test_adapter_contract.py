"""Contract tests run against every curated adapter's saved-HTML fixtures.

These guard against *our own* parsing regressions, not live site changes — the fixtures
are frozen snapshots. When a real import starts failing, the fix is: save the new page
HTML over the fixture in `fixtures/<adapter>/`, rerun, and the failing assertion below
points straight at the selector that needs updating (see ADR 0003).
"""
from __future__ import annotations

from dataclasses import dataclass

import pytest

from app.core.adapters.freewebnovel import FreeWebNovelAdapter
from app.core.adapters.royalroad import RoyalRoadAdapter
from app.core.adapters.webnovel import WebnovelAdapter

from support import FixtureFetcher, load_fixture


@dataclass
class AdapterCase:
    id: str
    adapter_cls: type
    fixture_dir: str
    novel_url: str
    expected_title: str
    expected_author: str
    expected_chapters: int
    search_url: str


CASES = [
    AdapterCase(
        id="freewebnovel",
        adapter_cls=FreeWebNovelAdapter,
        fixture_dir="freewebnovel",
        novel_url="https://freewebnovel.vip/freenovel/test-novel",
        expected_title="Test Novel",
        expected_author="Jane Doe",
        expected_chapters=3,
        search_url="https://freewebnovel.vip/search",
    ),
    AdapterCase(
        id="royalroad",
        adapter_cls=RoyalRoadAdapter,
        fixture_dir="royalroad",
        novel_url="https://www.royalroad.com/fiction/1001/test-fiction",
        expected_title="Test Fiction",
        expected_author="Jane Doe",
        expected_chapters=2,
        search_url="https://www.royalroad.com/fictions/search?title=Test",
    ),
    AdapterCase(
        id="webnovel",
        adapter_cls=WebnovelAdapter,
        fixture_dir="webnovel",
        novel_url="https://www.webnovel.com/book/123456",
        expected_title="Test Novel",
        expected_author="Jane Doe",
        expected_chapters=2,  # 2 of 3 chapters are free in the fixture
        search_url="https://www.webnovel.com/search?keywords=Test",
    ),
]
CASE_IDS = [c.id for c in CASES]


@pytest.mark.parametrize("case", CASES, ids=CASE_IDS)
def test_matches_accepts_own_urls_and_rejects_others(case: AdapterCase):
    assert case.adapter_cls.matches(case.novel_url) is True
    assert case.adapter_cls.matches("https://example.com/") is False


@pytest.mark.parametrize("case", CASES, ids=CASE_IDS)
async def test_fetch_novel_parses_expected_fields(case: AdapterCase):
    fetcher = FixtureFetcher({case.novel_url: load_fixture(case.fixture_dir, "novel.html")})
    adapter = case.adapter_cls()

    result = await adapter.fetch_novel(fetcher, case.novel_url)

    assert result.meta.title == case.expected_title
    assert result.meta.author == case.expected_author
    assert result.meta.cover_url
    assert len(result.chapters) == case.expected_chapters


@pytest.mark.parametrize("case", CASES, ids=CASE_IDS)
async def test_fetch_chapter_parses_body(case: AdapterCase):
    fetcher = FixtureFetcher({case.novel_url: load_fixture(case.fixture_dir, "novel.html")})
    adapter = case.adapter_cls()
    novel = await adapter.fetch_novel(fetcher, case.novel_url)
    first = novel.chapters[0]

    fetcher.register(first.url, load_fixture(case.fixture_dir, "chapter.html"))
    content = await adapter.fetch_chapter(fetcher, first)

    assert content.title
    assert "<p>" in content.html


@pytest.mark.parametrize("case", CASES, ids=CASE_IDS)
async def test_search_returns_expected_result(case: AdapterCase):
    fetcher = FixtureFetcher({case.search_url: load_fixture(case.fixture_dir, "search.html")})
    adapter = case.adapter_cls()

    results = await adapter.search(fetcher, "Test")

    assert results
    assert results[0].title == case.expected_title
    assert results[0].source == adapter.name
