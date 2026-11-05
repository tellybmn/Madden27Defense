import httpx
import pytest

import db
from mock_site import build_site
from scraper import FetchError, HttpxLoader, MockLoader, Scraper, USER_AGENTS, resolve_slugs
from seed_catalog import CATALOG
from tests.fixtures.mock_playbook_pages import FORMATION_HTML, INDEX_HTML, PAGES


def test_resolve_slugs():
    assert resolve_slugs("vikings, seahawks,jaguars,ravens,vikings") == [
        "minnesota-vikings", "seattle-seahawks", "jacksonville-jaguars", "baltimore-ravens"]
    assert resolve_slugs("multiple-d") == ["multiple-d"]
    with pytest.raises(ValueError):
        resolve_slugs("packers")


async def test_scrape_playbook_from_fixtures():
    loader = MockLoader({**PAGES, "https://huddle.gg/playbooks/minnesota-vikings/dollar-3-2": FORMATION_HTML})
    sp = await Scraper(loader).scrape_playbook("minnesota-vikings")
    names = [f.info.formation_name for f in sp.formations]
    assert names == ["Nickel 2-4 Dbl Mug", "Dollar 3-2"]        # 3-4 Bear / Swap Mug pages missing -> errors
    assert len(sp.errors) == 2 and all("404" not in e or "mock" in e for e in sp.errors)
    assert len(sp.formations[0].plays) == 9


async def test_source_fallback_to_second_site():
    pages = {k.replace("huddle.gg", "madden.tools"): v for k, v in PAGES.items()}
    sp = await Scraper(MockLoader(pages)).scrape_playbook("minnesota-vikings")
    assert sp.formations and sp.formations[0].url.startswith("https://madden.tools")
    assert any("huddle.gg" in e for e in sp.errors)


async def test_fallback_loader_used_for_js_pages():
    shell = "<html><body><div id='app'></div></body></html>"
    primary = MockLoader({u: shell for u in PAGES})        # every page is an empty JS shell
    fb = MockLoader(PAGES)
    sp = await Scraper(primary, fallback_loader=fb).scrape_playbook("minnesota-vikings")
    assert sp.formations and len(sp.formations[0].plays) == 9


async def test_full_offline_scrape_ingest_is_idempotent():
    site = MockLoader(build_site(CATALOG))
    scraper = Scraper(site)
    conn = db.connect(":memory:")
    for _ in range(2):
        for sp in await scraper.scrape_many(list(CATALOG)):
            assert not sp.errors
            db.ingest_playbook(conn, sp)
    assert db.counts(conn)["playbooks"] == 6
    assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
    total = sum(len(p) for f in CATALOG.values() for p in f.values())
    assert db.counts(conn)["plays"] == total


# ---- live loader behaviour, driven through httpx.MockTransport (no sockets)
def _loader(handler, **kw):
    sleeps = []

    async def fake_sleep(s):
        sleeps.append(s)
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return HttpxLoader(client=client, sleep=fake_sleep, **kw), sleeps


async def test_retry_with_exponential_backoff_then_success():
    calls = []

    def handler(req):
        calls.append(req.headers["user-agent"])
        return httpx.Response(503) if len(calls) < 3 else httpx.Response(200, text="ok")
    loader, sleeps = _loader(handler, min_interval=0, backoff_base=1.0)
    assert await loader.fetch("https://huddle.gg/x") == "ok"
    assert len(calls) == 3
    assert 1.0 <= sleeps[0] <= 1.25 and 2.0 <= sleeps[1] <= 2.5     # 1s, 2s (+jitter)
    assert len(set(calls)) == 3                                      # UA rotated every attempt
    assert set(calls) <= set(USER_AGENTS)


async def test_gives_up_after_max_retries():
    loader, _ = _loader(lambda r: httpx.Response(500), min_interval=0, max_retries=2)
    with pytest.raises(FetchError, match="gave up after 3 attempts"):
        await loader.fetch("https://huddle.gg/x")


async def test_404_not_retried():
    n = []
    loader, _ = _loader(lambda r: (n.append(1), httpx.Response(404))[1], min_interval=0)
    with pytest.raises(FetchError) as e:
        await loader.fetch("https://huddle.gg/x")
    assert e.value.status == 404 and len(n) == 1


async def test_retry_after_header_honoured():
    seq = iter([httpx.Response(429, headers={"Retry-After": "30"}), httpx.Response(200, text="ok")])
    loader, sleeps = _loader(lambda r: next(seq), min_interval=0, backoff_base=1.0)
    assert await loader.fetch("https://huddle.gg/x") == "ok"
    assert sleeps[0] >= 30


async def test_transport_error_retried():
    state = {"n": 0}

    def handler(req):
        state["n"] += 1
        if state["n"] == 1:
            raise httpx.ConnectError("boom")
        return httpx.Response(200, text="ok")
    loader, _ = _loader(handler, min_interval=0)
    assert await loader.fetch("https://huddle.gg/x") == "ok"


async def test_rate_limit_spacing():
    t = {"now": 0.0}
    loader, sleeps = _loader(lambda r: httpx.Response(200, text="ok"), min_interval=2.0)
    loader._clock = lambda: t["now"]
    await loader.fetch("https://huddle.gg/a")
    t["now"] = 0.5
    await loader.fetch("https://huddle.gg/b")
    assert sleeps == [pytest.approx(1.5)]
