import pytest

from src import database as db
from src import optimizer as opt
from src.offline_data import CATALOG, build_site
from src.parser import infer_formation
from src.scraper import MockLoader, Scraper


@pytest.fixture(scope="module")
def conn():
    import asyncio
    c = db.connect(":memory:")
    for sp in asyncio.run(Scraper(MockLoader(build_site(CATALOG))).scrape_many(list(CATALOG))):
        db.ingest_playbook(c, sp)
    return c


@pytest.fixture(scope="module")
def clusters(conn):
    return opt.load_clusters(conn)


def test_isomorphism_clustering_merges_across_playbooks(clusters):
    by = {c.key: c for c in clusters}
    nick = by["nickel-2-4-dbl-mug"]
    assert len(nick.sources) == 4
    assert len(nick.plays) > 20            # union of plays, deduped by name
    assert len(clusters) == len({c.key for c in clusters})


def test_solution_satisfies_all_constraints(clusters):
    r = opt.solve(clusters, base="Minnesota Vikings")
    assert all(ok for _, ok, _ in r.constraints), r.constraints
    keys = {f.key for f in r.formations}
    assert len(r.formations) <= 6 and r.total_plays <= 350
    assert set(opt.BASE_REQUIRED) <= keys
    assert any(infer_formation(f.name).is_five_front for f in r.formations)
    assert keys & set(opt.SPREAD_OPTIONS)
    for f in r.formations:
        assert set(f.audibles) == set(opt.AUDIBLE_TYPES)
        for t, p in f.audibles.items():
            assert p.ptype == t


def test_incomplete_formation_never_selected(clusters):
    goal = next(c for c in clusters if c.info.set_name == "Goal Line")
    assert not goal.has_all_audibles
    r = opt.solve(clusters)
    assert goal.key not in {f.key for f in r.formations}


def test_play_cap_enforced(clusters):
    r = opt.solve(clusters, max_plays=60)
    assert r.total_plays <= 60 and all(ok for _, ok, _ in r.constraints)


def test_infeasible_when_play_budget_too_small(clusters):
    with pytest.raises(opt.InfeasibleError):
        opt.solve(clusters, max_plays=10)


def test_infeasible_when_required_formation_missing(clusters):
    without = [c for c in clusters if c.key != "nickel-3-3-swap-mug"]
    with pytest.raises(opt.InfeasibleError, match="swap-mug"):
        opt.solve(without)


def test_infeasible_without_five_front(clusters):
    without = [c for c in clusters if not c.info.is_five_front]
    with pytest.raises(opt.InfeasibleError, match="5-front"):
        opt.solve(without)


def test_entropy_threshold_excludes_flat_formations(clusters):
    by = {c.key: c for c in clusters}
    assert by["nickel-2-4-dbl-mug"].entropy > by["dollar-3-2"].entropy > 0.45   # mug > plain
    with pytest.raises(opt.InfeasibleError):
        opt.solve(clusters, entropy_min=0.999)


def test_base_and_style_change_objective(clusters):
    a = opt.solve(clusters, base="Minnesota Vikings", style="flores-macdonald")
    b = opt.solve(clusters, base=None, style="flores-macdonald")
    c = opt.solve(clusters, base="Minnesota Vikings", style="campanile")
    assert a.objective > b.objective
    assert a.objective != c.objective
    with pytest.raises(opt.InfeasibleError):
        opt.solve(clusters, style="nope")


def test_deterministic(clusters):
    assert opt.solve(clusters).to_dict() == opt.solve(clusters).to_dict()


def test_optimality_vs_brute_force(clusters):
    """Solver result must equal exhaustive best over all valid 6-subsets."""
    from itertools import combinations
    r = opt.solve(clusters, base="Minnesota Vikings")
    w = opt.STYLES["flores-macdonald"]
    cands = {c.cluster.key: c for c in opt._candidates(clusters, w, "Minnesota Vikings", 58)}
    elig = {k: c for k, c in cands.items() if c.cluster.has_all_audibles and (
        c.cluster.info.set_name not in opt.SUB_SETS or opt.disguise_entropy(c.cluster.info, c.plays) >= opt.ENTROPY_MIN)}
    best = 0
    for combo in combinations(elig.values(), 6):
        ks = {c.cluster.key for c in combo}
        if (set(opt.BASE_REQUIRED) <= ks and any(c.cluster.info.is_five_front for c in combo)
                and ks & set(opt.SPREAD_OPTIONS) and sum(len(c.plays) for c in combo) <= 350):
            best = max(best, opt._score(list(combo)))
    assert r.objective == pytest.approx(best)
