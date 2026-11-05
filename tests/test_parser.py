import sqlite3

import pytest

import db
from parser import (
    ScrapedFormation, ScrapedPlaybook, canonical_formation_key, classify_play, infer_formation,
    parse_formation_page, parse_index, play_type, slugify,
)
from tests.fixtures.mock_playbook_pages import BASE, EXPECTED, FORMATION_HTML, INDEX_HTML


# ---------------------------------------------------------------- extraction
def test_index_link_extraction():
    links = parse_index(INDEX_HTML, BASE)
    assert [l.name for l in links] == ["Nickel 2-4 Dbl Mug", "Dollar 3-2", "3-4 Bear", "Nickel 3-3 Swap Mug"]
    assert links[0].url == "https://huddle.gg/playbooks/minnesota-vikings/nickel-2-4-dbl-mug"
    assert links[3].url == "https://huddle.gg/playbooks/minnesota-vikings/nickel-3-3-swap-mug"


def test_index_skips_dupes_js_and_missing_href():
    names = [l.name for l in parse_index(INDEX_HTML, BASE)]
    assert names.count("Dollar 3-2") == 1
    assert "Broken Card" not in names and "No Href" not in names


def test_index_empty_or_garbage_html():
    assert parse_index("", BASE) == []
    assert parse_index("<html><body><p>JS required</p></body></html>", BASE) == []


def test_formation_page_titles_deduped_and_cleaned():
    titles = parse_formation_page(FORMATION_HTML)
    assert titles.count("Tampa 2") == 1          # whitespace-variant dupe collapsed
    assert "" not in titles
    assert titles[0] == "Mid Blitz 0" and len(titles) == 9


@pytest.mark.parametrize("raw,slug", [
    ("Nickel 2-4 Dbl Mug", "nickel-2-4-dbl-mug"),
    ("3-4 Bear", "3-4-bear"),
    ("  Nickel 3-3   Swap Mug ", "nickel-3-3-swap-mug"),
    ("Dbl. Mug / A-Gap", "dbl-mug-a-gap"),
    ("Nickel 2–4 Dbl Mug", "nickel-2-4-dbl-mug"),       # en dash
    ("Fangio's 4-3 Even 6-1", "fangios-4-3-even-6-1"),
    ("Cover 2 & Man", "cover-2-and-man"),
    ("", ""),
])
def test_slugify(raw, slug):
    assert slugify(raw) == slug


def test_canonical_key_collapses_aliases():
    assert canonical_formation_key("Nickel 2-4 Double Mug") == canonical_formation_key("Nickel 2-4 Dbl. Mug")


# ------------------------------------------------------------ classification
@pytest.mark.parametrize("title,exp", EXPECTED.items())
def test_fixture_play_classification(title, exp):
    p = classify_play(title)
    assert (p.coverage_family, p.rush_count, p.is_sim_pressure, p.is_blitz, p.is_run_plug) == exp


@pytest.mark.parametrize("title,family", [
    ("Cover 0 Blitz", "Cover 0"), ("Cross Dog", "Cover 0"),
    ("Cover 1 Hole", "Cover 1"), ("Man Free", "Cover 1"),
    ("Cover 2", "Tampa 2"), ("Cover 2 Invert", "Tampa 2"), ("Tampa 2", "Tampa 2"),
    ("Cover 2 Man Under", "Cover 2 Man"),
    ("Cover 3 Sky", "Cover 3 Sky/Buzz/Cloud"), ("Cover 3 Cloud", "Cover 3 Sky/Buzz/Cloud"),
    ("Cover 4 Match", "Cover 4 Match/Palms"), ("Cover 4 Quarters", "Cover 4 Match/Palms"),
    ("Cover 6", "Cover 6/9"), ("Cover 9", "Cover 6/9"), ("Split-Field (6/9)", "Cover 6/9"),
    ("Quarter-Quarter-Half", "Cover 6/9"), ("Mystery Play", "Unknown"),
])
def test_coverage_families(title, family):
    assert classify_play(title).coverage_family == family


def test_sim_pressure_is_not_blitz():
    sim = classify_play("Nickel Dog 3 Buzz")
    assert sim.is_sim_pressure and not sim.is_blitz and sim.rush_count == 4
    assert sim.play_type == "sim_pressure"


def test_blitz_is_not_sim():
    for t in ("Mid Blitz 0", "Cross Dog 0", "Fire Zone 3", "Overload Blitz Cover 3 Sky", "Dog 3 Buzz (5 man)"):
        p = classify_play(t)
        assert p.is_blitz and not p.is_sim_pressure and p.rush_count >= 5, t


def test_sim_and_blitz_never_both():
    from seed_catalog import CATALOG
    for fm in CATALOG.values():
        for plays in fm.values():
            for t in plays:
                p = classify_play(t)
                assert not (p.is_sim_pressure and p.is_blitz), t


def test_run_plug_and_rush_hints():
    assert classify_play("Pinch Dog 2").is_run_plug
    assert not classify_play("Pinch Dog 2").is_sim_pressure
    assert classify_play("Cover 3 Sky (3 man rush)").rush_count == 3
    assert classify_play("Prevent Cover 4").rush_count == 3
    assert classify_play("Cover 3 Sky (4 man)").rush_count == 4
    assert classify_play("Cover 2 Man Under").rush_count == 4        # '2 man' is not a rush hint
    assert classify_play("Cover 0 Blitz 7 man").rush_count == 6      # capped at 6+


def test_play_types():
    assert play_type(classify_play("Cover 0 Blitz")) == "man_pressure"
    assert play_type(classify_play("Safety Blitz Cover 1")) == "blitz"
    assert play_type(classify_play("Cover 6")) == "split_match"
    assert play_type(classify_play("Tampa 2")) == "two_high"


@pytest.mark.parametrize("name,set_name,front,box,mug", [
    ("Nickel 2-4 Dbl Mug", "Nickel", "2-4", 6, "dbl_mug"),
    ("Dime 1-4 Dbl Mug", "Dime", "1-4", 5, "dbl_mug"),
    ("Dollar 3-2", "Dollar", "3-2", 5, None),
    ("3-4 Bear", "Base", "3-4 Bear", 7, None),
    ("Nickel 3-3 Swap Mug", "Nickel", "3-3", 6, "swap_mug"),
    ("4-2-5 Over G", "Nickel", "4-2-5 Over G", 6, None),
    ("4-3 Even 6-1", "Base", "4-3 Even 6-1", 7, None),
    ("5-2", "Base", "5-2", 7, None),
])
def test_infer_formation(name, set_name, front, box, mug):
    f = infer_formation(name)
    assert (f.set_name, f.front_type, f.box_count, f.mug_style) == (set_name, front, box, mug)


# ------------------------------------------------------------------ database
def _playbook():
    forms = []
    for name in ("Nickel 2-4 Dbl Mug", "3-4 Bear"):
        titles = parse_formation_page(FORMATION_HTML)
        forms.append(ScrapedFormation(infer_formation(name), "u", [classify_play(t) for t in titles]))
    return ScrapedPlaybook("minnesota-vikings", "Minnesota Vikings", "team", forms)


def test_ingest_idempotent(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
    assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    first = None
    for _ in range(3):
        db.ingest_playbook(conn, _playbook())
        c = db.counts(conn)
        first = first or c
        assert c == first
    assert first == {"playbooks": 1, "formations": 2, "plays": 18}
    assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
    assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"


def test_ingest_updates_changed_classification():
    conn = db.connect(":memory:")
    db.ingest_playbook(conn, _playbook())
    conn.execute("UPDATE plays SET rush_count = 5, is_blitz = 1 WHERE play_name = 'Tampa 2'")
    db.ingest_playbook(conn, _playbook())
    assert conn.execute("SELECT rush_count FROM plays WHERE play_name='Tampa 2' LIMIT 1").fetchone()[0] == 4


def test_foreign_keys_and_checks_enforced():
    conn = db.connect(":memory:")
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO plays(formation_id, play_name, coverage_family, rush_count) VALUES(999,'x','Cover 0',6)")
    db.ingest_playbook(conn, _playbook())
    with pytest.raises(sqlite3.IntegrityError):  # sim and blitz are mutually exclusive
        conn.execute("UPDATE plays SET is_sim_pressure=1, is_blitz=1 WHERE play_id=1")
