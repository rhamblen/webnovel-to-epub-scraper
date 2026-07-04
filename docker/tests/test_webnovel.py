"""webnovel.com-specific regression: the free/paywall boundary (ADR 0004 — no paywalled
sources) must hold even if the source's state changes between scan and fetch."""
from __future__ import annotations

import pytest

from app.core.adapters.base import ChapterRef
from app.core.adapters.webnovel import WebnovelAdapter

from support import FixtureFetcher, load_fixture


async def test_locked_chapter_is_refused_even_if_previously_free():
    adapter = WebnovelAdapter()
    ref = ChapterRef(number=3, url="https://www.webnovel.com/book/123456/113", title="Chapter 3: Locked")
    fetcher = FixtureFetcher({ref.url: load_fixture("webnovel", "chapter_locked.html")})

    with pytest.raises(ValueError):
        await adapter.fetch_chapter(fetcher, ref)


async def test_free_prefix_note_reports_partial_availability():
    adapter = WebnovelAdapter()
    novel_url = "https://www.webnovel.com/book/123456"
    fetcher = FixtureFetcher({novel_url: load_fixture("webnovel", "novel.html")})

    result = await adapter.fetch_novel(fetcher, novel_url)

    assert len(result.chapters) == 2
    assert "2 of 3" in result.note
