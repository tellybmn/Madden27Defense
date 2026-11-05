"""Async scraper: live (httpx) or offline (mock) page loaders -> normalised schema objects."""
from __future__ import annotations

import asyncio
import logging
import random
import time
from typing import Awaitable, Callable, Protocol

import httpx

from .parser import (
    ScrapedFormation, ScrapedPlaybook, classify_play, infer_formation, parse_formation_page,
    parse_index, playbook_display_name,
)

log = logging.getLogger("madden.scraper")

SOURCES = ("https://huddle.gg", "https://madden.tools")

TEAM_ALIASES = {
    "vikings": "minnesota-vikings", "dolphins": "miami-dolphins", "seahawks": "seattle-seahawks",
    "ravens": "baltimore-ravens", "jaguars": "jacksonville-jaguars",
    "multiple-d": "multiple-d", "multipled": "multiple-d", "multiple": "multiple-d",
}
KNOWN_SLUGS = frozenset(TEAM_ALIASES.values())

USER_AGENTS = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64; rv:125.0) Gecko/20100101 Firefox/125.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36 Edg/123.0.0.0",
)


def resolve_slugs(teams: str | list[str]) -> list[str]:
    items = teams.split(",") if isinstance(teams, str) else teams
    out: list[str] = []
    for t in (x.strip().lower() for x in items):
        if not t:
            continue
        slug = TEAM_ALIASES.get(t, t if t in KNOWN_SLUGS else None)
        if slug is None:
            raise ValueError(f"unknown playbook {t!r}; known: {', '.join(sorted(TEAM_ALIASES))}")
        if slug not in out:
            out.append(slug)
    return out


class FetchError(Exception):
    def __init__(self, url: str, reason: str, status: int | None = None):
        super().__init__(f"{url}: {reason}")
        self.url, self.reason, self.status = url, reason, status


class PageLoader(Protocol):
    async def fetch(self, url: str) -> str: ...


class MockLoader:
    """Offline loader serving pre-baked HTML keyed by URL (zero network)."""

    def __init__(self, pages: dict[str, str]):
        self.pages = dict(pages)
        self.requests: list[str] = []

    async def fetch(self, url: str) -> str:
        self.requests.append(url)
        try:
            return self.pages[url]
        except KeyError:
            raise FetchError(url, "not in mock site", 404) from None


class HttpxLoader:
    """Live loader: min-interval rate limiting, exponential backoff + jitter, UA rotation."""

    RETRY_STATUS = frozenset({408, 425, 429, 500, 502, 503, 504})

    def __init__(self, *, min_interval: float = 1.5, max_retries: int = 4, backoff_base: float = 1.0,
                 backoff_cap: float = 60.0, timeout: float = 20.0, client: httpx.AsyncClient | None = None,
                 sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
                 clock: Callable[[], float] = time.monotonic, rng: random.Random | None = None,
                 user_agents: tuple[str, ...] = USER_AGENTS):
        self.min_interval, self.max_retries = min_interval, max_retries
        self.backoff_base, self.backoff_cap = backoff_base, backoff_cap
        self._client = client or httpx.AsyncClient(timeout=timeout, follow_redirects=True)
        self._own_client = client is None
        self._sleep, self._clock = sleep, clock
        self._rng = rng or random.Random()
        self._uas = user_agents
        self._ua_i = 0
        self._last = float("-inf")
        self._lock = asyncio.Lock()
        self.user_agents_used: list[str] = []

    async def _throttle(self) -> None:
        async with self._lock:
            wait = self._last + self.min_interval - self._clock()
            if wait > 0:
                await self._sleep(wait)
            self._last = self._clock()

    def _backoff(self, attempt: int, retry_after: float | None) -> float:
        delay = min(self.backoff_base * 2 ** attempt, self.backoff_cap)
        delay += self._rng.uniform(0, delay * 0.25)
        return max(delay, retry_after or 0.0)

    async def fetch(self, url: str) -> str:
        last_reason, status = "unknown", None
        for attempt in range(self.max_retries + 1):
            await self._throttle()
            ua = self._uas[self._ua_i % len(self._uas)]
            self._ua_i += 1
            self.user_agents_used.append(ua)
            retry_after = None
            try:
                r = await self._client.get(url, headers={
                    "User-Agent": ua, "Accept": "text/html,application/xhtml+xml",
                    "Accept-Language": "en-US,en;q=0.9"})
            except httpx.TransportError as e:
                last_reason, status = f"transport error: {e.__class__.__name__}", None
            else:
                status = r.status_code
                if r.status_code == 200:
                    return r.text
                if r.status_code not in self.RETRY_STATUS:
                    raise FetchError(url, f"HTTP {r.status_code}", r.status_code)
                last_reason = f"HTTP {r.status_code}"
                ra = r.headers.get("Retry-After", "")
                retry_after = float(ra) if ra.replace(".", "", 1).isdigit() else None
            if attempt < self.max_retries:
                await self._sleep(self._backoff(attempt, retry_after))
        raise FetchError(url, f"gave up after {self.max_retries + 1} attempts ({last_reason})", status)

    async def aclose(self) -> None:
        if self._own_client:
            await self._client.aclose()


class PlaywrightLoader:
    """Optional fallback for client-side rendered pages (requires `pip install playwright`)."""

    def __init__(self, timeout_ms: int = 30000):
        self.timeout_ms = timeout_ms

    async def fetch(self, url: str) -> str:
        try:
            from playwright.async_api import async_playwright
        except ImportError as e:
            raise FetchError(url, "playwright not installed") from e
        async with async_playwright() as pw:
            browser = await pw.chromium.launch()
            try:
                page = await browser.new_page()
                await page.goto(url, wait_until="networkidle", timeout=self.timeout_ms)
                return await page.content()
            finally:
                await browser.close()


class Scraper:
    def __init__(self, loader: PageLoader, *, sources: tuple[str, ...] = SOURCES,
                 fallback_loader: PageLoader | None = None, concurrency: int = 2):
        self.loader, self.sources, self.fallback_loader = loader, sources, fallback_loader
        self._sem = asyncio.Semaphore(concurrency)

    async def _index(self, source: str, slug: str):
        url = f"{source}/playbooks/{slug}"
        html = await self.loader.fetch(url)
        links = parse_index(html, url)
        if not links and self.fallback_loader:
            log.info("no cards in static HTML for %s; trying rendered fallback", url)
            links = parse_index(await self.fallback_loader.fetch(url), url)
        return links

    async def _formation(self, link, sp: ScrapedPlaybook) -> ScrapedFormation | None:
        async with self._sem:
            try:
                html = await self.loader.fetch(link.url)
                titles = parse_formation_page(html)
                if not titles and self.fallback_loader:
                    titles = parse_formation_page(await self.fallback_loader.fetch(link.url))
            except FetchError as e:
                sp.errors.append(str(e))
                return None
        return ScrapedFormation(infer_formation(link.name), link.url, [classify_play(t) for t in titles])

    async def scrape_playbook(self, slug: str) -> ScrapedPlaybook:
        sp = ScrapedPlaybook(slug, playbook_display_name(slug),
                             "generic" if slug == "multiple-d" else "team")
        links = []
        for source in self.sources:
            try:
                links = await self._index(source, slug)
            except FetchError as e:
                sp.errors.append(str(e))
                continue
            if links:
                break
        results = await asyncio.gather(*(self._formation(l, sp) for l in links))
        sp.formations = [f for f in results if f]  # gather preserves index order
        return sp

    async def scrape_many(self, slugs: list[str]) -> list[ScrapedPlaybook]:
        return [await self.scrape_playbook(s) for s in slugs]
