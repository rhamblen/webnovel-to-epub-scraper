"""Polite async HTTP fetch layer.

Every adapter goes through this, so rate limiting, per-host concurrency, retries with
backoff, an honest-but-browser-like User-Agent, and robots.txt checks are inherited by
all of them (see ADR 0004).
"""
from __future__ import annotations

import asyncio
import time
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import httpx

DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)


class Fetcher:
    def __init__(
        self,
        user_agent: str = DEFAULT_UA,
        delay: float = 1.0,
        concurrency: int = 2,
        retries: int = 3,
        timeout: float = 30.0,
        respect_robots: bool = True,
    ):
        self.delay = max(0.0, delay)
        self.retries = max(0, retries)
        self.respect_robots = respect_robots
        self._sem = asyncio.Semaphore(max(1, concurrency))
        self._client = httpx.AsyncClient(
            headers={"User-Agent": user_agent, "Accept-Language": "en-US,en;q=0.9"},
            timeout=timeout,
            follow_redirects=True,
        )
        self._last: dict[str, float] = {}
        self._robots: dict[str, RobotFileParser | None] = {}
        self._host_locks: dict[str, asyncio.Lock] = {}
        self._ua = user_agent

    def _host(self, url: str) -> str:
        return urlparse(url).netloc

    def _lock_for(self, host: str) -> asyncio.Lock:
        if host not in self._host_locks:
            self._host_locks[host] = asyncio.Lock()
        return self._host_locks[host]

    async def _pace(self, host: str) -> None:
        """Enforce a minimum delay between requests to the same host."""
        async with self._lock_for(host):
            last = self._last.get(host)
            if last is not None:
                wait = self.delay - (time.monotonic() - last)
                if wait > 0:
                    await asyncio.sleep(wait)
            self._last[host] = time.monotonic()

    async def _load_robots(self, host: str) -> RobotFileParser | None:
        if host in self._robots:
            return self._robots[host]
        rp = RobotFileParser()
        try:
            r = await self._client.get(f"https://{host}/robots.txt")
            if r.status_code == 200:
                rp.parse(r.text.splitlines())
            else:
                rp = None  # no usable robots.txt -> allow
        except Exception:
            rp = None
        self._robots[host] = rp
        return rp

    async def allowed(self, url: str) -> bool:
        if not self.respect_robots:
            return True
        rp = await self._load_robots(self._host(url))
        return True if rp is None else rp.can_fetch(self._ua, url)

    async def get(self, url: str) -> httpx.Response:
        return await self._request("GET", url)

    async def post(self, url: str, data: dict | None = None) -> httpx.Response:
        return await self._request("POST", url, data=data)

    async def _request(self, method: str, url: str, data: dict | None = None) -> httpx.Response:
        host = self._host(url)
        if not await self.allowed(url):
            raise PermissionError(f"Blocked by robots.txt: {url}")
        last_exc: Exception | None = None
        async with self._sem:
            for attempt in range(self.retries + 1):
                await self._pace(host)
                try:
                    if method == "POST":
                        r = await self._client.post(url, data=data)
                    else:
                        r = await self._client.get(url)
                    if r.status_code in (429, 500, 502, 503, 504):
                        raise httpx.HTTPStatusError(
                            f"retryable {r.status_code}", request=r.request, response=r
                        )
                    if r.encoding is None:
                        r.encoding = "utf-8"
                    return r
                except (httpx.HTTPError, httpx.HTTPStatusError) as e:
                    last_exc = e
                    if attempt < self.retries:
                        await asyncio.sleep(min(2 ** attempt, 8))
        raise last_exc if last_exc else RuntimeError(f"fetch failed: {url}")

    async def aclose(self) -> None:
        await self._client.aclose()
