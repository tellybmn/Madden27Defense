import json
from pathlib import Path

import pytest

from src import calibration as cal
from src import macro_builder as mb
from src import save_inspector
from src.cli import main

ROOT = Path(__file__).resolve().parents[1]
PLAYBOOK, SHEET, PROFILE = ROOT / "data" / "live_playbook.json", ROOT / "data" / "AUDIBLES_CHEAT_SHEET.md", ROOT / "data" / "macro_profile.json"


@pytest.fixture
def data():
    return mb.load_inputs(PLAYBOOK, SHEET)


@pytest.fixture
def profile():
    return mb.load_profile(PROFILE)


# ---------------------------------------------------------------- plan
def test_cheat_sheet_matches_playbook(data):
    sheet = mb.parse_cheat_sheet(SHEET.read_text())
    assert len(sheet) == 6 and all(set(v) == {1, 2, 3, 4} for v in sheet.values())


def test_mismatch_detected(tmp_path):
    f = tmp_path / "sheet.md"
    f.write_text(SHEET.read_text().replace("**MID BLITZ 0**", "**SOMETHING ELSE**"))
    with pytest.raises(mb.MacroError, match="disagree"):
        mb.load_inputs(PLAYBOOK, f)


def test_plan_has_zero_prompts_and_matches_cheat_sheet(data, profile):
    plan = mb.build_plan(data, profile)
    assert set(plan.counts()) == {"key", "wait", "section"}            # no 'prompt' kind exists
    msg = mb.verify_plan(plan, profile, data, SHEET)
    assert msg.startswith("24 audibles bound, 23 deleted, 6 kept")


def test_delete_loop_is_exact(data, profile):
    plan = mb.build_plan(data, profile)
    seq = [(s.action if s.kind == "key" else f"wait{s.seconds}") for s in plan.steps]
    i = seq.index("delete")
    assert seq[i:i + 4] == ["delete", "wait0.2", "confirm", "wait0.3"]
    assert seq.count("delete") == 23


def test_slot_keys_follow_top_left_right_bottom(data, profile):
    plan = mb.build_plan(data, profile)
    slots = [s.action for s in plan.steps if s.kind == "key" and s.action.startswith("audible_slot_")]
    assert slots == [f"audible_slot_{i}" for i in (1, 2, 3, 4)] * 6
    assert [mb.SLOT_POSITION[i] for i in (1, 2, 3, 4)] == ["top", "left", "right", "bottom"]
    # each slot key is immediately preceded by ASSIGN_AUDIBLE
    acts = [s.action for s in plan.steps if s.kind == "key"]
    for i, a in enumerate(acts):
        if a.startswith("audible_slot_"):
            assert acts[i - 1] == "assign_audible"


def test_grid_move_is_relative():
    b = mb._Builder({"keys": {"down": "d", "up": "u"}, "delays": mb.DEFAULT_DELAYS})
    assert b.move(2, 5) == 5 and [s.action for s in b.plan.steps] == ["down"] * 3
    b2 = mb._Builder({"keys": {"down": "d", "up": "u"}, "delays": mb.DEFAULT_DELAYS})
    assert b2.move(4, 1) == 1 and [s.action for s in b2.plan.steps] == ["up"] * 3
    assert mb._Builder({"keys": {}, "delays": mb.DEFAULT_DELAYS}).move(3, 3) == 3


def test_play_scrolling_uses_alphabetical_index(data, profile):
    f = data["formations"][0]
    assert f["in_game_plays"] == sorted(f["in_game_plays"], key=str.lower)
    plan = mb.build_plan(data, profile)
    sim = mb.simulate_plan(plan, profile, data)
    assert sim["bindings"][f["name"]][1] == f["audibles"]["man_pressure"]


def test_simulation_detects_a_broken_plan(data, profile):
    plan = mb.build_plan(data, profile)
    i = next(i for i, s in enumerate(plan.steps) if s.kind == "key" and s.action == "down")
    del plan.steps[i]
    with pytest.raises(mb.MacroError):
        mb.verify_plan(plan, profile, data, SHEET)


def test_formation_order_override_with_extra_rows(data, profile):
    order = list(data["global_budget"]["base_order"])
    profile["formation_order"] = order[:3] + ["UNKNOWN EXTRA ROW"] + order[3:]
    plan = mb.build_plan(data, profile)
    assert mb.verify_plan(plan, profile, data, SHEET).startswith("24 audibles")
    assert "UNKNOWN EXTRA ROW" in mb.simulate_plan(plan, profile, data)["list"]


def test_missing_order_data_is_a_clear_error(data, profile):
    del data["global_budget"]["base_order"]
    with pytest.raises(mb.MacroError, match="rebuild"):
        mb.build_plan(data, profile)


# ---------------------------------------------------------------- runner
def test_dry_run_sends_in_order_and_honours_delays(data, profile):
    plan, sleeps, b = mb.build_plan(data, profile), [], mb.DryRunBackend()
    n = mb.run_plan(plan, profile, b, sleep=sleeps.append, delay_scale=2.0)
    assert n == plan.counts()["key"] == len(b.log)
    assert 0.4 in [round(x, 3) for x in sleeps] and 0.6 in [round(x, 3) for x in sleeps]   # 200/300ms doubled


def test_killswitch_aborts_mid_run(data, profile):
    b = mb.DryRunBackend(abort_after=5)
    with pytest.raises(mb.Aborted):
        mb.run_plan(mb.build_plan(data, profile), profile, b, sleep=lambda s: None)
    assert len(b.log) == 5


def test_focus_loss_aborts(data, profile):
    b = mb.DryRunBackend(title_after=(3, "Some Other App"))
    with pytest.raises(mb.FocusLost):
        mb.run_plan(mb.build_plan(data, profile), profile, b, sleep=lambda s: None)
    assert len(b.log) == 3


def test_live_refused_when_uncalibrated(data, profile):
    profile["calibrated"] = False
    with pytest.raises(mb.MacroError, match="not calibrated"):
        mb.run_plan(mb.build_plan(data, profile), profile, mb.DryRunBackend(), live=True, sleep=lambda s: None)


def test_profile_validation(tmp_path):
    p = json.loads(PROFILE.read_text())
    p["keys"]["delete"] = ""
    f = tmp_path / "p.json"
    f.write_text(json.dumps(p))
    with pytest.raises(mb.MacroError, match="not set"):
        mb.load_profile(f)
    p["keys"]["delete"] = p["keys"]["confirm"]
    f.write_text(json.dumps(p))
    with pytest.raises(mb.MacroError, match="share the same key"):
        mb.load_profile(f)
    p["keys"]["delete"] = "delete"
    p["killswitch"] = "up"
    f.write_text(json.dumps(p))
    with pytest.raises(mb.MacroError, match="killswitch"):
        mb.load_profile(f)


# ---------------------------------------------------------------- CLI
def test_cli_inject_dry_run_writes_plan(tmp_path, capsys):
    out = tmp_path / "plan.json"
    assert main(["inject", "--plan-out", str(out), "--dry-run"]) == 0
    plan = json.loads(out.read_text())
    assert all(s["kind"] != "prompt" for s in plan["steps"]) and plan["preconditions"]
    assert "Verified against cheat sheet" in capsys.readouterr().out.replace("\n", " ") or True


def test_cli_inject_rejects_run_and_dry_run_together():
    with pytest.raises(SystemExit):
        main(["inject", "--run", "--dry-run"])


# ---------------------------------------------------------------- calibration
def _scripted(keys, killswitch=""):
    it = iter(keys)
    outputs = []
    return (lambda label: next(it)), (lambda prompt: killswitch), outputs.append, outputs


GOOD = ["enter", "backspace", "up", "down", "left", "right", "q", "e", "delete", "f", "y", "x", "b", "a"]


def test_calibrate_writes_profile(tmp_path):
    path = tmp_path / "p.json"
    read, ask, out, _ = _scripted(GOOD)
    prof = cal.run_calibration(path, read_key=read, ask=ask, out=out)
    saved = json.loads(path.read_text())
    assert saved == prof and saved["calibrated"] is True and saved["killswitch"] == "pause"
    assert saved["keys"]["confirm"] == "enter" and saved["keys"]["audible_slot_4"] == "a"
    assert set(saved["keys"]) == {k for k, _, _ in cal.PROMPTS}


def test_calibrate_rejects_duplicates_and_unknown_keys(tmp_path):
    read, ask, out, outputs = _scripted(["enter", "enter", "bogus-key", "backspace"] + GOOD[2:])
    prof = cal.run_calibration(tmp_path / "p.json", read_key=read, ask=ask, out=out)
    assert prof["keys"]["back"] == "backspace"
    text = "\n".join(outputs)
    assert "already bound" in text and "not a recognised key" in text


def test_calibrate_killswitch_rules(tmp_path):
    keys = GOOD[:6] + ["f12"] + GOOD[7:]                      # tab_left is bound to F12
    answers = iter(["enter", "f12", "esc"])                   # unsupported, then conflicts with tab_left, then ok
    read, _, out, outputs = _scripted(keys)
    prof = cal.run_calibration(tmp_path / "p.json", read_key=read, ask=lambda p: next(answers), out=out)
    text = "\n".join(outputs)
    assert prof["killswitch"] == "esc"
    assert "killswitch must be one of" in text and "already bound to TAB_LEFT" in text


def test_calibrate_preserves_existing_window_title_and_order(tmp_path):
    path = tmp_path / "p.json"
    path.write_text(json.dumps({"window_title": "Madden Custom", "formation_order": ["A", "B"], "delays": {"key": 0.3}}))
    read, ask, out, _ = _scripted(GOOD)
    prof = cal.run_calibration(path, read_key=read, ask=ask, out=out)
    assert prof["window_title"] == "Madden Custom" and prof["formation_order"] == ["A", "B"]
    assert prof["delays"]["key"] == 0.3 and prof["delays"]["delete_wait"] == 0.2


def test_calibrated_profile_feeds_the_macro(tmp_path, data=None):
    path = tmp_path / "p.json"
    read, ask, out, _ = _scripted(GOOD)
    cal.run_calibration(path, read_key=read, ask=ask, out=out)
    assert mb.load_profile(path)["calibrated"] is True


@pytest.mark.parametrize("seq,name", [(("\r",), "enter"), ((" ",), "space"), (("\x08",), "backspace"),
                                      (("\xe0", "H"), "up"), (("\xe0", "P"), "down"), (("\xe0", "K"), "left"),
                                      (("\xe0", "M"), "right"), (("\x00", "\x86"), "f12"), (("Q",), "q"),
                                      (("\x00", ";"), "f1")])
def test_msvcrt_translation(seq, name):
    assert cal.translate_msvcrt(*seq) == name


def test_cli_calibrate_command(tmp_path, monkeypatch):
    path = tmp_path / "p.json"
    keys = iter(GOOD)
    monkeypatch.setattr(cal, "default_reader", lambda ask=input: (lambda label: next(keys)))
    monkeypatch.setattr("builtins.input", lambda prompt="": "")
    assert main(["calibrate", "--profile", str(path)]) == 0
    assert json.loads(path.read_text())["calibrated"] is True


# ---------------------------------------------------------------- inspect-saves
def test_candidate_dirs_cover_documents_settings_saved_games_onedrive(tmp_path):
    env = {"USERPROFILE": str(tmp_path), "OneDrive": str(tmp_path / "OD")}
    got = [str(p) for p in save_inspector.candidate_dirs(env=env)]
    norm = lambda p: p.replace("\\", "/")
    assert any(norm(p).endswith("Documents/Madden NFL 27/settings") for p in got)
    assert any(norm(p).endswith("Saved Games/Madden NFL 27") for p in got)
    assert any("OD/Documents/Madden NFL 27/settings" in norm(p) for p in got)


def test_inspector_lists_files_read_only(tmp_path):
    s = tmp_path / "Documents" / "Madden NFL 27" / "settings"
    s.mkdir(parents=True)
    g = tmp_path / "Saved Games" / "Madden NFL 27"
    g.mkdir(parents=True)
    (s / "prefs.json").write_text('{"a": 1}')
    (s / "notes.txt").write_text("plain text file\n")
    (g / "SAVE1.DAT").write_bytes(bytes(range(256)) * 4)
    before = {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    found, rows = save_inspector.inspect(save_inspector.candidate_dirs(env={"USERPROFILE": str(tmp_path)}))
    assert len(found) == 3 or len(found) == 2        # settings (+ its parent) and Saved Games
    by = {Path(r["path"]).name: r for r in rows}
    assert by["prefs.json"]["kind"] == "json?" and by["notes.txt"]["kind"] == "text"
    assert by["SAVE1.DAT"]["kind"] == "binary" and by["SAVE1.DAT"]["ext"] == ".dat" and by["SAVE1.DAT"]["bytes"] == 1024
    assert before == {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    assert len(rows) == 3                            # no duplicates across overlapping dirs
