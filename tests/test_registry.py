"""Registry-level tests. Mainly: adding the catch-all GenericAdapter must never turn
`cover_url_allowed` (the /cover proxy's only gate — see routes/pages.py) into an open
proxy for arbitrary URLs."""
from __future__ import annotations

from app.core.adapters import cover_url_allowed, get_adapter
from app.core.adapters.generic import GenericAdapter


def test_generic_adapter_is_the_catch_all():
    assert get_adapter("https://some-random-webnovel-site.example/novel/1") is not None
    assert isinstance(get_adapter("https://some-random-webnovel-site.example/novel/1"), GenericAdapter)


def test_cover_proxy_rejects_arbitrary_hosts_matched_only_by_the_fallback():
    assert cover_url_allowed("https://some-random-webnovel-site.example/cover.jpg") is False
    assert cover_url_allowed("http://169.254.169.254/latest/meta-data/") is False


def test_cover_proxy_still_allows_curated_adapter_hosts():
    assert cover_url_allowed("https://freewebnovel.vip/static/covers/x.jpg") is True
    # royalroad.com's own matches() requires "/fiction" in the path
    assert cover_url_allowed("https://www.royalroad.com/fiction/1/x/cover.jpg") is True
    # real Royal Road covers live on this declared CDN, not the main domain
    assert cover_url_allowed("https://cdn.royalroadcdn.com/covers/x.jpg") is True
