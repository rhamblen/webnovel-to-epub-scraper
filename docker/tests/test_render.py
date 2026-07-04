"""Fetcher.get_rendered() wiring, using a fake Renderer so this suite never needs a real
downloaded browser to run. The real Playwright/Chromium path was verified separately by
hand (see CHANGELOG v0.5.0) against an actual JS-only test page."""
from __future__ import annotations

import pytest

from app.core.fetch import Fetcher


class FakeRenderer:
    """Stands in for core.render.Renderer: no Playwright/browser involved."""

    def __init__(self, user_agent: str, timeout: float = 30.0):
        self.user_agent = user_agent
        self.pages: dict[str, str] = {}
        self.calls: list[str] = []
        self.fail_times = 0

    async def render(self, url: str, wait_selector: str | None = None) -> str:
        self.calls.append(url)
        if self.fail_times > 0:
            self.fail_times -= 1
            raise RuntimeError("simulated navigation failure")
        return self.pages.get(url, "<html></html>")

    async def aclose(self) -> None:
        pass


def _patch_renderer(monkeypatch, fake: FakeRenderer) -> None:
    monkeypatch.setattr("app.core.render.Renderer", lambda user_agent, timeout=30.0: fake)


async def test_get_rendered_returns_renderer_output(monkeypatch):
    fake = FakeRenderer("test-ua")
    fake.pages["https://example.test/x"] = "<html><body>rendered</body></html>"
    _patch_renderer(monkeypatch, fake)

    fetcher = Fetcher(respect_robots=False, delay=0.0, retries=0)
    resp = await fetcher.get_rendered("https://example.test/x")

    assert resp.text == "<html><body>rendered</body></html>"
    assert fake.calls == ["https://example.test/x"]


async def test_get_rendered_respects_robots_txt(monkeypatch):
    fake = FakeRenderer("test-ua")
    _patch_renderer(monkeypatch, fake)

    fetcher = Fetcher(respect_robots=True, delay=0.0, retries=0)

    async def _blocked(url):
        return False

    monkeypatch.setattr(fetcher, "allowed", _blocked)

    with pytest.raises(PermissionError):
        await fetcher.get_rendered("https://example.test/blocked")
    assert fake.calls == []  # never launched the browser for a disallowed URL


async def test_get_rendered_retries_then_succeeds(monkeypatch):
    fake = FakeRenderer("test-ua")
    fake.pages["https://example.test/flaky"] = "<html>ok</html>"
    fake.fail_times = 1  # first attempt raises, second should succeed
    _patch_renderer(monkeypatch, fake)

    fetcher = Fetcher(respect_robots=False, delay=0.0, retries=1)
    resp = await fetcher.get_rendered("https://example.test/flaky")

    assert resp.text == "<html>ok</html>"
    assert len(fake.calls) == 2


async def test_get_rendered_reuses_the_same_renderer_across_calls(monkeypatch):
    fake = FakeRenderer("test-ua")
    fake.pages["https://example.test/a"] = "<html>a</html>"
    fake.pages["https://example.test/b"] = "<html>b</html>"

    build_count = 0

    def _factory(user_agent, timeout=30.0):
        nonlocal build_count
        build_count += 1
        return fake

    monkeypatch.setattr("app.core.render.Renderer", _factory)

    fetcher = Fetcher(respect_robots=False, delay=0.0, retries=0)
    await fetcher.get_rendered("https://example.test/a")
    await fetcher.get_rendered("https://example.test/b")

    assert build_count == 1  # the browser is launched once, not per page
