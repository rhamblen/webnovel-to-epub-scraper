"""freewebnovel-specific regression: libread.* URLs are the same catalogue, normalized
to the freewebnovel.vip slug (its chapter links redirect there; see adapter docstring)."""
from __future__ import annotations

from app.core.adapters.freewebnovel import FreeWebNovelAdapter

from support import FixtureFetcher, load_fixture


async def test_libread_url_resolves_to_freewebnovel_novel():
    adapter = FreeWebNovelAdapter()
    canonical_url = "https://freewebnovel.vip/freenovel/test-novel"
    libread_url = "https://libread.com/libread/test-novel-98765"

    assert adapter.matches(libread_url) is True

    fetcher = FixtureFetcher({canonical_url: load_fixture("freewebnovel", "novel.html")})
    result = await adapter.fetch_novel(fetcher, libread_url)

    assert result.meta.title == "Test Novel"
    assert result.meta.source_url == canonical_url
