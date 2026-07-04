"""Adapter registry.

Curated adapters are tried in order; the generic readability fallback (Phase 4) will be
appended last so `get_adapter` always returns something.
"""
from __future__ import annotations

from .base import Adapter
from .freewebnovel import FreeWebNovelAdapter
from .royalroad import RoyalRoadAdapter
from .webnovel import WebnovelAdapter

ADAPTERS: list[type[Adapter]] = [
    FreeWebNovelAdapter,
    RoyalRoadAdapter,
    WebnovelAdapter,
]


def get_adapter(url: str) -> Adapter | None:
    for cls in ADAPTERS:
        if cls.matches(url):
            return cls()
    return None


def get_adapter_by_name(name: str) -> Adapter | None:
    for cls in ADAPTERS:
        if cls.name == name:
            return cls()
    return None


def searchable_names() -> list[str]:
    """Names of adapters that implement search — drives the Discover site list."""
    return [cls.name for cls in ADAPTERS if getattr(cls, "searchable", False)]


def cover_url_allowed(url: str) -> bool:
    """Whether the cover proxy may fetch this URL: a recognized novel host, or a
    cover CDN one of the adapters has declared. Keeps /cover from being an open proxy."""
    from urllib.parse import urlparse

    if get_adapter(url) is not None:
        return True
    host = urlparse(url).netloc.lower()
    for cls in ADAPTERS:
        for allowed in cls.cover_hosts:
            if host == allowed or host.endswith("." + allowed):
                return True
    return False
