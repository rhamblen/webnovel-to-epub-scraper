"""Playwright-backed rendering for JS-heavy sites (Phase 4, ADR 0001/0003).

Kept separate from ``fetch.py`` so the common case (plain httpx) never imports
Playwright at all. A ``Renderer`` launches headless Chromium lazily on first use and
keeps it running for reuse across an entire scrape (`Fetcher` owns one instance and
closes it in `aclose()`) — launching a fresh browser per page would be far too slow for
a multi-hundred-chapter book.
"""
from __future__ import annotations

from playwright.async_api import Browser, Playwright, async_playwright


class Renderer:
    def __init__(self, user_agent: str, timeout: float = 30.0):
        self._user_agent = user_agent
        self._timeout_ms = timeout * 1000
        self._pw: Playwright | None = None
        self._browser: Browser | None = None

    async def _ensure_browser(self) -> Browser:
        if self._browser is None:
            self._pw = await async_playwright().start()
            # --disable-dev-shm-usage: Docker's default /dev/shm (64MB) is too small for
            # Chromium and causes crashes; this makes it use /tmp instead.
            self._browser = await self._pw.chromium.launch(
                headless=True, args=["--disable-dev-shm-usage"]
            )
        return self._browser

    async def render(self, url: str, wait_selector: str | None = None) -> str:
        """Navigate to ``url`` and return the fully rendered HTML."""
        browser = await self._ensure_browser()
        page = await browser.new_page(user_agent=self._user_agent)
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=self._timeout_ms)
            if wait_selector:
                try:
                    await page.wait_for_selector(wait_selector, timeout=self._timeout_ms)
                except Exception:
                    pass  # best-effort: return whatever rendered rather than fail outright
            else:
                try:
                    await page.wait_for_load_state("networkidle", timeout=self._timeout_ms)
                except Exception:
                    pass
            return await page.content()
        finally:
            await page.close()

    async def aclose(self) -> None:
        if self._browser is not None:
            await self._browser.close()
            self._browser = None
        if self._pw is not None:
            await self._pw.stop()
            self._pw = None
