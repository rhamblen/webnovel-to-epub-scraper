"""Shared test support for adapter self-tests.

``FixtureFetcher`` stands in for ``core.fetch.Fetcher``: instead of hitting the network,
it serves HTML that was saved from a real page (see ``fixtures/<adapter>/``). Adapters
only ever call ``fetcher.get(url)`` / ``fetcher.post(url, data=...)`` / (for JS-heavy
pages) ``fetcher.get_rendered(url)`` and read ``.text`` off the result, so that's all the
fake needs to reproduce. Static and rendered content are registered separately, since a
real Fetcher would return different content for the two (a JS shell vs. its rendered DOM).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def load_fixture(adapter: str, filename: str) -> str:
    return (FIXTURES_DIR / adapter / filename).read_text(encoding="utf-8")


@dataclass
class FakeResponse:
    text: str


@dataclass
class FixtureFetcher:
    routes: dict[str, str] = field(default_factory=dict)
    rendered_routes: dict[str, str] = field(default_factory=dict)

    def register(self, url: str, html: str) -> "FixtureFetcher":
        self.routes[url] = html
        return self

    def register_rendered(self, url: str, html: str) -> "FixtureFetcher":
        self.rendered_routes[url] = html
        return self

    async def get(self, url: str) -> FakeResponse:
        return self._resolve(url, self.routes)

    async def post(self, url: str, data: dict | None = None) -> FakeResponse:
        return self._resolve(url, self.routes)

    async def get_rendered(self, url: str, wait_selector: str | None = None) -> FakeResponse:
        return self._resolve(url, self.rendered_routes)

    def _resolve(self, url: str, routes: dict[str, str]) -> FakeResponse:
        if url not in routes:
            raise AssertionError(f"no fixture registered for {url!r} (have: {list(routes)})")
        return FakeResponse(text=routes[url])
