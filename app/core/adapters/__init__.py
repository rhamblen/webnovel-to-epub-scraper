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
