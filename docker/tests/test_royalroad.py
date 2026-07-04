"""Royal Road-specific regression: injected anti-theft paragraphs (a randomly-named class
declared display:none in an inline <style>) must never reach the EPUB."""
from __future__ import annotations

from app.core.adapters.base import ChapterRef
from app.core.adapters.royalroad import RoyalRoadAdapter

from support import FixtureFetcher, load_fixture


async def test_anti_theft_paragraph_is_stripped():
    adapter = RoyalRoadAdapter()
    ref = ChapterRef(
        number=1,
        url="https://www.royalroad.com/fiction/1001/test-fiction/chapter/1/chapter-1-the-beginning",
    )
    fetcher = FixtureFetcher({ref.url: load_fixture("royalroad", "chapter.html")})

    content = await adapter.fetch_chapter(fetcher, ref)

    assert "stolen" not in content.html.lower()
    assert "Amazon" not in content.html
    assert content.html.count("<p>") == 2
