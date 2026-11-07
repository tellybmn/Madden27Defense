import json
from pathlib import Path

import pytest

from src import macro_builder as mb
from src import save_inspector

ROOT = Path(__file__).resolve().parents[1]
PLAYBOOK, SHEET = ROOT / "data" / "live_playbook.json", ROOT / "data" / "AUDIBLES_CHEAT_SHEET.md"


@pytest.fixture
def data():
    return mb.load_inputs(PLAYBOOK, SHEET)


@pytest.fixture
def profile():
    p = mb.load_profile(ROOT / "data" / "macro_profile.json")
    p["sequences"].update(open_editor=["confirm", "wait:0.5"], open_audible_editor=["right"],
                          delete_formation=["delete_key", "confirm"], add_formation=["confirm"],
                          bind_audible=["confirm", "{button_key}"])
    return p


def test_cheat_sheet_matches_playbook(data):
    sheet = mb.parse_cheat_sheet(SHEET.read_text())
    assert len(sheet) == 6 and all(set(v) == {1, 2, 3, 4} for v in sheet.values())
    assert {v[1][0] for v in sheet.values()} == {"Y"}


def test_mismatch_detected(tmp_path, data):
    bad = SHEET.read_text().replace("**MID BLITZ 0**", "**SOMETHING ELSE**")
    f = tmp_path / "sheet.md"
    f.write_text(bad)
    with pytest.raises(mb.MacroError, match="disagree"):
        mb.load_inputs(PLAYBOOK, f)


def test_plan_counts(data, profile):
    plan = mb.build_plan(data, profile)
    c = plan.counts()
    assert c["section"] == 4
    binds = [s for s in plan.steps if s.kind == "key" and s.value in ("y", "x", "b", "a")]
    assert len(binds) == 24                                   # 6 formations x 4 audibles
    assert [s.value for s in binds[:4]] == ["y", "x", "b", "a"]
    assert sum(1 for s in plan.steps if s.kind == "key" and s.value == "delete_key") == 23
    adds = [s for s in plan.steps if s.kind == "prompt" and s.value.startswith("Open the pool") and "Nickel 3-3 Swap Dbl Mug" in s.value]
    assert len(adds) == 1 and "Jacksonville Jaguars" in adds[0].value


def test_uncalibrated_positions_become_prompts_not_guesses(data, profile):
    plan = mb.build_plan(data, profile)
    assert not [s for s in plan.steps if s.kind == "key" and s.value in ("up", "down")]
    assert sum(1 for s in plan.steps if s.kind == "prompt") >= 6 + 23 + 24


def test_calibrated_indices_emit_relative_navigation(data, profile):
    f = data["formations"][0]
    profile["play_index"] = {f["name"]: {f["audibles"][t]: i * 2 for i, t in enumerate(mb.SLOT_TYPES)}}
    profile["formation_index"] = {n: i for i, n in enumerate(data["global_budget"]["pruned"])}
    plan = mb.build_plan(data, profile)
    downs = [s for s in plan.steps if s.kind == "key" and s.value == "down"]
    assert downs and not any("Highlight formation '%s' then" % data["global_budget"]["pruned"][0] in s.value
                             for s in plan.steps if s.kind == "prompt")


def test_dry_run_sends_in_order_and_honours_delays(data, profile):
    plan, sleeps = mb.build_plan(data, profile), []
    b = mb.DryRunBackend()
    n = mb.run_plan(plan, profile, b, sleep=sleeps.append, delay_scale=2.0)
    assert n == plan.counts()["key"] and n == len([e for e in b.log if e[0] == "key"])
    assert max(sleeps) == pytest.approx(profile["delays"]["section"] * 2.0)


def test_killswitch_aborts_mid_run(data, profile):
    b = mb.DryRunBackend(abort_after=5)
    with pytest.raises(mb.Aborted):
        mb.run_plan(mb.build_plan(data, profile), profile, b, sleep=lambda s: None)
    assert len(b.log) <= 7                                        # stopped almost immediately


def test_focus_loss_aborts(data, profile):
    b = mb.DryRunBackend(title_after=(3, "Some Other App"))
    with pytest.raises(mb.FocusLost):
        mb.run_plan(mb.build_plan(data, profile), profile, b, sleep=lambda s: None)
    assert len([e for e in b.log if e[0] == "key"]) <= 4


def test_live_refused_when_uncalibrated(data):
    prof = mb.load_profile(ROOT / "data" / "macro_profile.json")
    assert prof["calibrated"] is False
    with pytest.raises(mb.MacroError, match="not calibrated"):
        mb.run_plan(mb.build_plan(data, prof), prof, mb.DryRunBackend(), live=True, sleep=lambda s: None)


def test_inspector_is_read_only(tmp_path):
    (tmp_path / "Documents" / "Madden NFL 27").mkdir(parents=True)
    f = tmp_path / "Documents" / "Madden NFL 27" / "x.bin"
    f.write_bytes(b"\x00\x01abc")
    before = f.read_bytes()
    rows = save_inspector.inspect(save_inspector.candidate_dirs(tmp_path))
    assert rows[0]["bytes"] == 5 and f.read_bytes() == before
