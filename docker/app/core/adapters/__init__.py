"""Adapter registry.

Curated adapters are tried in order; the generic readability fallback (Phase 4) will be
appended last so `get_adapter` always returns something.
"""
from __future__ import annotations

from .base import Adapter
from .freewebnovel import FreeWebNovelAdapter

ADAPTERS: list[type[Adapter]] = [
    FreeWebNovelAdapter,
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
