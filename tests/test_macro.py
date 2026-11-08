import json
from pathlib import Path

import pytest

from src import calibration as cal
from src import macro_builder as mb
from src import save_inspector
from src.cli import main
from src.parser import split_formation_name

ROOT = Path(__file__).resolve().parents[1]
PLAYBOOK, SHEET, PROFILE = ROOT / "data" / "live_playbook.json", ROOT / "data" / "AUDIBLES_CHEAT_SHEET.md", ROOT / "data" / "macro_profile.json"


@pytest.fixture
def data():
    return mb.load_inputs(PLAYBOOK, SHEET)


@pytest.fixture
def profile():
    return mb.load_profile(PROFILE)


def model(names, plays=None, tab="MY PLAYBOOK", **assume):
    return mb.UIModel(names, plays or {}, {**cal.DEFAULT_ASSUME, **assume}, tab=tab)


def remove(m):
    """E -> modal (cursor on NO) -> NAV_UP (YES) -> CONFIRM."""
    for a in ("remove_all", "up", "confirm"):
        m.apply(a)


NAMES = ["3-4 Even", "3-4 Over", "Nickel 2-4", "Nickel 2-4 Dbl Mug", "Dime 2-3"]

# The Nickel sets shown in the real "SELECT SET" dropdown screenshot (after most fronts were pruned).
DROPDOWN_NAMES = ["3-4 Under", "Nickel 2-4 Single Mug", "Nickel 2-4 Swap Dbl Mug", "Nickel 2-4 Wide",
                  "Nickel 3-3 Odd", "Nickel 3-3 Swap Dbl Mug", "Dime 2-3"]


def pick_set(m, index):
    """LSHIFT opens SELECT SET, arrows move the dropdown cursor, SPACE selects."""
    m.apply("set_cycle")
    while m.dropdown != index:
        m.apply("down" if index > m.dropdown else "up")
    m.apply("confirm")


def removal_confirms(plan):
    """The SPACE presses that confirm a REMOVE PLAY modal (E -> UP -> SPACE), not dropdown selections."""
    ks = [s for s in plan.steps if s.kind == "key"]
    return [s for i, s in enumerate(ks) if s.action == "confirm" and i >= 2
            and ks[i - 1].action == "up" and ks[i - 2].action == "remove_all"]


def dropdown_confirms(plan):
    ks = [s for s in plan.steps if s.kind == "key"]
    out, open_ = [], False
    for s in ks:
        if s.action == "set_cycle":
            open_ = True
        elif s.action == "confirm" and open_:
            out.append(s)
            open_ = False
    return out


# ------------------------------------------------------------ name split
@pytest.mark.parametrize("name,expected", [
    ("Nickel 2-4 Dbl Mug", ("Nickel", "2-4 Dbl Mug")), ("3-4 Under", ("3-4", "Under")),
    ("4-3 Even 6-1", ("4-3", "Even 6-1")), ("Goal Line 5-3", ("Goal Line", "5-3")),
    ("Prevent 3 Deep", ("Prevent", "3 Deep")), ("2-4-5 Over Wide", ("2-4-5", "Over Wide")),
    ("3-3-5 3 High Penny", ("3-3-5", "3 High Penny")), ("Dime 1-4 Dbl Mug", ("Dime", "1-4 Dbl Mug")),
])
def test_split_formation_name(name, expected):
    assert split_formation_name(name) == expected


# ------------------------------------------------------------ UI model
def test_formation_cycle_wraps_and_resets_set():
    m = model(NAMES)
    pick_set(m, 1)
    assert m.current == ("3-4", "Over")
    for _ in range(3):
        m.apply("formation_cycle")
    assert m.current == ("3-4", "Even")                      # 3 groups wrap to the start; set reset to first


def test_lshift_opens_a_dropdown_instead_of_cycling():
    m = model(NAMES)
    m.apply("formation_cycle")                               # Nickel: sets "2-4", "2-4 Dbl Mug"
    m.apply("set_cycle")
    assert m.dropdown == 0 and m.current == ("Nickel", "2-4")   # nothing selected yet
    m.apply("down")
    assert m.dropdown == 1 and m.current == ("Nickel", "2-4")   # moving the cursor does not select either
    m.apply("confirm")
    assert m.dropdown is None and m.current == ("Nickel", "2-4 Dbl Mug")


def test_dropdown_cursor_clamps_and_back_cancels():
    m = model(NAMES)
    m.apply("formation_cycle")
    m.apply("set_cycle")
    for _ in range(5):
        m.apply("down")
    assert m.dropdown == 1                                   # no wrap past the last row
    m.apply("up")
    m.apply("up")
    assert m.dropdown == 0
    m.apply("back")
    assert m.dropdown is None and m.current == ("Nickel", "2-4")


@pytest.mark.parametrize("leak", ["remove_all", "set_cycle", "formation_cycle", "tab_left", "audible_slot_1", "left"])
def test_any_other_key_while_dropdown_is_open_is_an_error(leak):
    m = model(NAMES)
    m.apply("set_cycle")
    with pytest.raises(mb.MacroError, match="SELECT SET dropdown is open"):
        m.apply(leak)


def test_dropdown_start_position_flag():
    m = model(NAMES, dropdown_starts_on_current=False)
    m.apply("formation_cycle")
    pick_set(m, 1)                                           # cursor opened on row 0 even though row 0 is current
    m.apply("set_cycle")
    assert m.dropdown == 0
    m2 = model(NAMES)
    m2.apply("formation_cycle")
    pick_set(m2, 1)
    m2.apply("set_cycle")
    assert m2.dropdown == 1                                  # default: opens on the current set


def test_set_menu_needs_playbook_or_audibles_tab():
    with pytest.raises(mb.MacroError, match="outside MY PLAYBOOK / AUDIBLES"):
        model(NAMES, tab="ALL PLAYS").apply("set_cycle")


def test_remove_all_vanishes_and_selection_lands_on_next_set():
    m = model(NAMES)
    remove(m)
    assert m.removed == ["3-4 Even"] and m.current == ("3-4", "Over")
    remove(m)                                                # group now empty -> next group, first set
    assert m.groups == ["Nickel", "Dime"] and m.current == ("Nickel", "2-4")


def test_empty_sets_remain_flag():
    m = model(NAMES, empty_sets_remain=True)
    remove(m)
    assert m.names() == NAMES and m.current == ("3-4", "Even")


def test_tab_switch_resets_selection_unless_flagged():
    m = model(NAMES)
    m.apply("formation_cycle")
    m.apply("tab_left")
    assert (mb.TABS[m.tab], m.current) == ("AUDIBLES", ("3-4", "Even"))
    m2 = model(NAMES, tab_resets_selection=False)
    m2.apply("formation_cycle")
    m2.apply("tab_left")
    assert m2.current == ("Nickel", "2-4")


def test_remove_modal_defaults_to_no_and_needs_up_then_confirm():
    m = model(NAMES)
    m.apply("remove_all")
    assert m.modal == "NO" and m.removed == []               # E alone removes nothing
    m.apply("confirm")                                       # confirming on the default NO cancels
    assert m.modal is None and m.removed == [] and m.names() == NAMES
    m.apply("remove_all")
    m.apply("up")
    assert m.modal == "YES"
    m.apply("down")
    assert m.modal == "NO"                                   # down returns to NO
    m.apply("up")
    m.apply("confirm")
    assert m.removed == ["3-4 Even"] and m.modal is None


def test_modal_blocks_other_keys_and_back_dismisses():
    m = model(NAMES)
    m.apply("remove_all")
    with pytest.raises(mb.MacroError, match="REMOVE PLAY confirmation is open"):
        m.apply("set_cycle")
    m.apply("back")
    assert m.modal is None and m.removed == []


def test_model_rejects_wrong_tab_actions():
    with pytest.raises(mb.MacroError):
        model(NAMES, tab="AUDIBLES").apply("remove_all")
    with pytest.raises(mb.MacroError):
        model(NAMES).apply("audible_slot_1")


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
    assert set(plan.counts()) == {"key", "wait", "section"}
    assert mb.verify_plan(plan, profile, data, SHEET) == "24 audibles bound, 23 sets emptied"


def test_pruning_uses_e_and_the_cycle_keys_not_delete(data, profile):
    plan = mb.build_plan(data, profile)
    acts = [s.action for s in plan.steps if s.kind == "key"]
    assert acts.count("remove_all") == 23 and "delete" not in acts
    assert len(removal_confirms(plan)) == 23                 # one SPACE per removal modal
    assert acts.count("confirm") == 23 + acts.count("set_cycle")   # ...plus one per SELECT SET dropdown
    assert {"formation_cycle", "set_cycle"} <= set(acts)
    keys = {s.action: s.value for s in plan.steps if s.kind == "key"}
    assert (keys["remove_all"], keys["formation_cycle"], keys["set_cycle"]) == ("e", "ctrlleft", "shiftleft")
    assert keys["confirm"] == "space"
    assert acts.index("tab_left") > max(i for i, a in enumerate(acts) if a == "remove_all")    # prune first
    assert acts.count("tab_left") == 1 and "tab_right" not in acts


def test_removal_sequence_and_timing(data, profile):
    plan = mb.build_plan(data, profile, prune_limit=1)
    ks = [s for s in plan.steps if s.kind == "key"]
    assert [(s.action, s.value, s.seconds, s.exact) for s in ks] == [
        ("remove_all", "e", 0.15, False), ("up", "up", 0.10, True), ("confirm", "space", 0.60, False)]


def test_post_confirm_settle_is_600ms_scaled(data, profile):
    plan = mb.build_plan(data, profile)
    rc = removal_confirms(plan)
    assert len(rc) == 23 and {s.seconds for s in rc} == {0.6}
    sleeps = []
    mb.run_plan(mb.build_plan(data, profile, prune_limit=1), profile, mb.DryRunBackend(), sleep=sleeps.append,
                delay_scale=1.5)
    assert round(sleeps[-1], 3) == 0.9


def test_stale_saved_profile_cannot_bring_back_the_short_settles(data, profile):
    profile["delays"]["remove_wait"] = 0.3                    # what an older `calibrate` run wrote to disk
    profile["delays"]["cycle_settle"] = 0.05
    plan = mb.build_plan(data, profile)
    assert {s.seconds for s in removal_confirms(plan)} == {0.6}
    assert {s.seconds for s in plan.steps if s.kind == "key" and s.action in ("formation_cycle", "set_cycle")} == {0.2}
    profile["delays"]["remove_wait"] = 1.0                    # a slower value is honoured
    assert {s.seconds for s in removal_confirms(mb.build_plan(data, profile))} == {1.0}


def test_every_cycle_key_is_followed_by_200ms(data, profile):
    plan = mb.build_plan(data, profile)
    cycles = [s for s in plan.steps if s.kind == "key" and s.action in ("formation_cycle", "set_cycle")]
    assert len(cycles) >= 10 and all(s.seconds == 0.2 for s in cycles)
    backend, first_after = mb.DryRunBackend(), {}
    mb.run_plan(plan, profile, backend, delay_scale=2.0,
                sleep=lambda s: first_after.setdefault(len(backend.log), s))      # first sleep after the n-th key
    keys = [s for s in plan.steps if s.kind == "key"]
    after_cycle = [first_after[i + 1] for i, s in enumerate(keys) if s.action in ("formation_cycle", "set_cycle")]
    assert after_cycle and all(round(x, 3) == 0.4 for x in after_cycle)       # 200ms x 2.0


def test_no_key_follows_a_removal_sooner_than_600ms(data, profile):
    """The key right after each SPACE (next E or a cycle key) is only sent after the 600ms settle."""
    plan = mb.build_plan(data, profile)
    ks = [s for s in plan.steps if s.kind == "key"]
    rc = {id(s) for s in removal_confirms(plan)}
    for i, s in enumerate(ks[:-1]):
        if id(s) in rc:
            assert s.seconds >= 0.6 and ks[i + 1].action in ("remove_all", "formation_cycle", "set_cycle", "tab_left")


def test_each_removal_is_e_up_confirm_in_order(data, profile):
    acts = [s.action for s in mb.build_plan(data, profile).steps if s.kind == "key"]
    idx = [i for i, a in enumerate(acts) if a == "remove_all"]
    assert len(idx) == 23 and all(acts[i + 1:i + 3] == ["up", "confirm"] for i in idx)


def test_plan_without_nav_up_is_rejected(data, profile):
    plan = mb.build_plan(data, profile)
    i = next(i for i, s in enumerate(plan.steps) if s.kind == "key" and s.action == "up")
    del plan.steps[i]                                        # the modal would stay on NO and cancel
    with pytest.raises(mb.MacroError):
        mb.verify_plan(plan, profile, data, SHEET)


def test_audibles_use_slot_hotkeys_directly(data, profile):
    plan = mb.build_plan(data, profile)
    slots = [s for s in plan.steps if s.kind == "key" and s.action.startswith("audible_slot_")]
    assert len(slots) == 24
    assert {s.action: s.value for s in slots} == {"audible_slot_1": "q", "audible_slot_2": "e",
                                                  "audible_slot_3": "z", "audible_slot_4": "c"}
    assert not [s for s in plan.steps if s.action == "assign_audible"]


def test_goto_uses_group_cycle_then_set_dropdown(data, profile):
    m = model(NAMES)
    b = mb._Builder(profile, m)
    b.goto("Nickel 2-4 Dbl Mug")
    assert [s.action for s in b.plan.steps] == ["formation_cycle", "set_cycle", "down", "confirm"]
    with pytest.raises(mb.MacroError, match="not in the formation list"):
        b.goto("Nickel 9-9")


def test_goto_skips_the_dropdown_when_the_set_is_already_selected(profile):
    b = mb._Builder(profile, model(NAMES))
    b.goto("3-4 Even")
    assert b.plan.steps == []
    b.goto("Nickel 2-4")                                     # group change selects the first set: no dropdown either
    assert [s.action for s in b.plan.steps] == ["formation_cycle"]


def test_dropdown_matches_the_screenshot_list(profile):
    """SELECT SET shows 2-4 SINGLE MUG, 2-4 SWAP DBL MUG, 2-4 WIDE, 3-3 ODD, 3-3 SWAP DBL MUG: go to the last row (4 presses down)."""
    m = model(DROPDOWN_NAMES)
    b = mb._Builder(profile, m)
    b.goto("Nickel 3-3 Swap Dbl Mug")
    assert [s.action for s in b.plan.steps] == ["formation_cycle", "set_cycle"] + ["down"] * 4 + ["confirm"]
    assert m.current == ("Nickel", "3-3 Swap Dbl Mug") and m.dropdown is None
    b.goto("Nickel 2-4 Wide")                                # and back up: re-open starts on the current row
    assert [s.action for s in b.plan.steps][-4:] == ["set_cycle", "up", "up", "confirm"]


def test_dropdown_timing_open_move_confirm(profile):
    b = mb._Builder(profile, model(DROPDOWN_NAMES))
    b.goto("Nickel 2-4 Swap Dbl Mug")
    ks = [(s.action, s.seconds) for s in b.plan.steps]
    assert ks == [("formation_cycle", 0.2), ("set_cycle", 0.2), ("down", 0.15), ("confirm", 0.3)]


def test_every_set_menu_is_arrows_then_space_and_never_left_open(data, profile):
    plan = mb.build_plan(data, profile)
    acts = [s.action for s in plan.steps if s.kind == "key"]
    opens = [i for i, a in enumerate(acts) if a == "set_cycle"]
    assert opens
    for i in opens:
        j = i + 1
        while acts[j] in ("down", "up"):
            j += 1
        assert acts[j] == "confirm"                          # closed by SPACE before any other key is sent


def test_plan_that_leaves_the_dropdown_open_is_rejected(data, profile):
    plan = mb.build_plan(data, profile)
    i = next(i for i, s in enumerate(plan.steps) if s.kind == "key" and s.action == "set_cycle")
    j = next(k for k in range(i, len(plan.steps)) if plan.steps[k].action == "confirm")
    del plan.steps[j]                                        # the dropdown stays open and the next key leaks
    with pytest.raises(mb.MacroError):
        mb.verify_plan(plan, profile, data, SHEET)


def test_dropdown_start_flag_changes_the_plan_but_still_verifies(data, profile):
    default_len = mb.build_plan(data, profile).counts()["key"]
    profile["assume"]["dropdown_starts_on_current"] = False
    plan = mb.build_plan(data, profile)
    assert mb.verify_plan(plan, profile, data, SHEET).startswith("24 audibles")
    assert plan.counts()["key"] >= default_len


def test_play_scroll_is_relative():
    plays = {"Nickel 2-4": list("abcdef")}
    m = model(["Nickel 2-4"], plays, tab_resets_selection=True)
    m.apply("tab_left")
    b = mb._Builder({"keys": {k: k for k in mb.REQUIRED_KEYS}, "delays": cal.DEFAULT_DELAYS}, m)
    b.scroll_to(3)
    b.scroll_to(1)
    assert [s.action for s in b.plan.steps] == ["down"] * 3 + ["up"] * 2


def test_binding_order_is_ascending_in_list(data, profile):
    plan = mb.build_plan(data, profile)
    acts = [s.action for s in plan.steps if s.kind == "key"]
    start = acts.index("tab_left")
    assert acts[start:].count("up") < acts[start:].count("down")          # scroll mostly downward


def test_simulation_detects_a_broken_plan(data, profile):
    plan = mb.build_plan(data, profile)
    i = next(i for i, s in enumerate(plan.steps) if s.kind == "key" and s.action == "set_cycle")
    del plan.steps[i]
    with pytest.raises(mb.MacroError):
        mb.verify_plan(plan, profile, data, SHEET)


def test_prune_limit_test_plan(data, profile):
    plan = mb.build_plan(data, profile, prune_limit=2)
    assert [s.action for s in plan.steps if s.kind == "key"] == ["remove_all", "up", "confirm"] * 2
    assert "TEST PLAN" in plan.preconditions[-1]
    assert "test plan: 2 set(s) emptied" in mb.verify_plan(plan, profile, data, SHEET, prune_limit=2)


def test_empty_sets_remain_assumption_builds_and_verifies(data, profile):
    profile["assume"]["empty_sets_remain"] = True
    plan = mb.build_plan(data, profile)
    assert mb.verify_plan(plan, profile, data, SHEET).startswith("24 audibles")
    assert plan.counts()["key"] > 159                       # must cycle past emptied sets


def test_formation_order_override_with_extra_sets(data, profile):
    order = list(data["global_budget"]["base_order"])
    profile["formation_order"] = order[:3] + ["Nickel 9-9 Mystery"] + order[3:]
    plan = mb.build_plan(data, profile)
    assert mb.verify_plan(plan, profile, data, SHEET).startswith("24 audibles")
    assert "Nickel 9-9 Mystery" in mb.simulate_plan(plan, profile, data)["list"]


def test_added_front_is_inserted_at_end_of_its_group(data, profile):
    names = mb._initial_names(data, profile)
    nickel = [n for n in names if n.startswith("Nickel ")]
    assert nickel[-1] == "Nickel 3-3 Swap Dbl Mug"


def test_missing_order_data_is_a_clear_error(data, profile):
    del data["global_budget"]["base_order"]
    with pytest.raises(mb.MacroError, match="rebuild"):
        mb.build_plan(data, profile)


# ---------------------------------------------------------------- runner
def test_dry_run_sends_in_order_and_honours_delays(data, profile):
    plan, sleeps, b = mb.build_plan(data, profile), [], mb.DryRunBackend()
    n = mb.run_plan(plan, profile, b, sleep=sleeps.append, delay_scale=2.0)
    assert n == plan.counts()["key"] == len(b.log)
    assert round(max(sleeps), 3) == round(profile["delays"]["menu"] * 2.0, 3)


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


def test_shipped_profile_is_calibrated_with_no_unverified_keys(profile):
    assert profile["calibrated"] is True and profile["unverified"] == []


def test_live_refused_when_uncalibrated_or_unverified(data, profile):
    plan = mb.build_plan(data, profile)
    profile["calibrated"] = False
    with pytest.raises(mb.MacroError, match="not calibrated"):
        mb.run_plan(plan, profile, mb.DryRunBackend(), live=True, sleep=lambda s: None)
    profile["calibrated"], profile["unverified"] = True, ["audible_slot_4"]
    with pytest.raises(mb.MacroError, match="unverified keys remain: audible_slot_4"):
        mb.run_plan(plan, profile, mb.DryRunBackend(), live=True, sleep=lambda s: None)
    profile["unverified"] = []
    assert mb.run_plan(plan, profile, mb.DryRunBackend(), live=True, sleep=lambda s: None) == plan.counts()["key"]


def test_profile_ships_verified_defaults(profile):
    k = profile["keys"]
    assert (k["tab_left"], k["tab_right"], k["formation_cycle"], k["set_cycle"], k["remove_all"]) == \
        ("z", "c", "ctrlleft", "shiftleft", "e")
    assert (k["audible_slot_1"], k["audible_slot_2"], k["audible_slot_3"], k["audible_slot_4"]) == ("q", "e", "z", "c")
    assert {x: k[x] for x in cal.VERIFIED_DEFAULTS} == cal.VERIFIED_DEFAULTS and not cal.UNVERIFIED_KEYS


def test_profile_validation_is_context_aware(tmp_path):
    p = json.loads(PROFILE.read_text())
    assert mb.load_profile(PROFILE)                           # Z/C/E repeat across tabs: allowed
    p["keys"]["remove_all"] = p["keys"]["tab_left"]           # both on MY PLAYBOOK: conflict
    f = tmp_path / "p.json"
    f.write_text(json.dumps(p))
    with pytest.raises(mb.MacroError, match="same screen"):
        mb.load_profile(f)
    p = json.loads(PROFILE.read_text())
    p["keys"]["audible_slot_4"] = p["keys"]["audible_slot_1"]  # both on AUDIBLES: conflict
    f.write_text(json.dumps(p))
    with pytest.raises(mb.MacroError, match="same screen"):
        mb.load_profile(f)
    p = json.loads(PROFILE.read_text())
    p["keys"]["remove_all"] = ""
    f.write_text(json.dumps(p))
    with pytest.raises(mb.MacroError, match="not set"):
        mb.load_profile(f)
    p = json.loads(PROFILE.read_text())
    p["killswitch"] = "up"
    f.write_text(json.dumps(p))
    with pytest.raises(mb.MacroError, match="killswitch"):
        mb.load_profile(f)


# ---------------------------------------------------------------- CLI
def test_cli_inject_dry_run_writes_plan(tmp_path):
    out = tmp_path / "plan.json"
    assert main(["inject", "--plan-out", str(out), "--dry-run"]) == 0
    plan = json.loads(out.read_text())
    assert all(s["kind"] != "prompt" for s in plan["steps"]) and plan["preconditions"] and plan["assumptions"]


def test_cli_inject_prune_limit_and_exclusive_flags(tmp_path):
    out = tmp_path / "plan.json"
    assert main(["inject", "--prune-limit", "3", "--plan-out", str(out), "--dry-run"]) == 0
    assert sum(1 for s in json.loads(out.read_text())["steps"] if s["action"] == "remove_all") == 3
    with pytest.raises(SystemExit):
        main(["inject", "--run", "--dry-run"])


def test_cli_inject_live_path_with_fake_backend(monkeypatch):
    """Exercise --run end to end WITHOUT sending real input (the real backend would type into any window)."""
    made = []

    def fake_backend(killswitch, hold=0.08):
        b = mb.DryRunBackend()
        made.append(b)
        return b
    monkeypatch.setattr(mb, "DirectInputBackend", fake_backend)
    assert main(["inject", "--run", "--yes", "--start-delay", "0", "--delay-scale", "0"]) == 0
    assert len(made) == 1 and len(made[0].log) == 215 and made[0].log[:3] == [("key", "e"), ("key", "up"), ("key", "space")]


# ---------------------------------------------------------------- calibration
def asker(answers):
    it = iter(answers)
    return lambda prompt: next(it)


def reader(keys):
    it = iter(keys)
    return lambda label: next(it)


FULL = ["space", "backspace", "up", "down", "left", "right", "z", "c", "e", "q", "e", "z", "c"]
TYPED = ["n", "ctrlleft", "shiftleft"]      # 'n' = no defaults, then the two typed-only modifier keys


def test_calibrate_defaults_path_needs_no_key_presses(tmp_path):
    path = tmp_path / "p.json"
    prof = cal.run_calibration(path, read_key=reader([]), ask=asker(["y", ""]), out=lambda m: None)
    saved = json.loads(path.read_text())
    assert saved == prof and saved["calibrated"] is True and saved["unverified"] == []
    assert saved["killswitch"] == "pause"
    assert saved["keys"] == {**cal.VERIFIED_DEFAULTS}


def test_calibrate_full_capture_path(tmp_path):
    prof = cal.run_calibration(tmp_path / "p.json", read_key=reader(FULL),
                               ask=asker(TYPED + ["f12"]), out=lambda m: None)
    assert prof["keys"] == cal.VERIFIED_DEFAULTS            # same keys captured by hand
    assert prof["keys"]["remove_all"] == prof["keys"]["audible_slot_2"] == "e"   # cross-screen repeat OK
    assert prof["killswitch"] == "f12"


def test_calibrate_rejects_same_screen_conflicts_and_unknown_keys(tmp_path):
    keys = ["space", "space", "bogus-key", "backspace"] + FULL[2:12] + ["q", "c"]   # slot 4 'q' clashes with slot 1
    outs = []
    prof = cal.run_calibration(tmp_path / "p.json", read_key=reader(keys), ask=asker(TYPED + [""]), out=outs.append)
    text = "\n".join(outs)
    assert "already bound to confirm on the same screen" in text and "not a recognised key" in text
    assert "already bound to audible_slot_1 on the same screen" in text
    assert prof["keys"]["audible_slot_4"] == "c"


def test_calibrate_killswitch_rules(tmp_path):
    keys = FULL[:8] + ["f12"] + FULL[9:]                     # remove_all bound to F12
    outs = []
    prof = cal.run_calibration(tmp_path / "p.json", read_key=reader(keys),
                               ask=asker(TYPED + ["enter", "f12", "pause"]), out=outs.append)
    text = "\n".join(outs)
    assert prof["killswitch"] == "pause"
    assert "killswitch must be one of" in text and "already bound to a menu action" in text


def test_calibrate_preserves_window_title_order_and_delays(tmp_path):
    path = tmp_path / "p.json"
    path.write_text(json.dumps({"window_title": "Madden Custom", "formation_order": ["A", "B"], "delays": {"key": 0.3}}))
    prof = cal.run_calibration(path, read_key=reader([]), ask=asker(["y", ""]), out=lambda m: None)
    assert prof["window_title"] == "Madden Custom" and prof["formation_order"] == ["A", "B"]
    assert prof["delays"]["key"] == 0.3 and prof["delays"]["remove_wait"] == 0.6


def test_calibrated_profile_unlocks_live_run(tmp_path, data=None):
    path = tmp_path / "p.json"
    cal.run_calibration(path, read_key=reader([]), ask=asker(["y", ""]), out=lambda m: None)
    prof = mb.load_profile(path)
    assert prof["calibrated"] is True and prof["unverified"] == []


@pytest.mark.parametrize("seq,name", [(("\r",), "enter"), ((" ",), "space"), (("\x08",), "backspace"),
                                      (("\xe0", "H"), "up"), (("\xe0", "P"), "down"), (("\xe0", "K"), "left"),
                                      (("\xe0", "M"), "right"), (("\x00", "\x86"), "f12"), (("Q",), "q"),
                                      (("\x00", ";"), "f1")])
def test_msvcrt_translation(seq, name):
    assert cal.translate_msvcrt(*seq) == name


def test_cli_calibrate_command(tmp_path, monkeypatch):
    path = tmp_path / "p.json"
    answers = iter(["y", ""])
    monkeypatch.setattr(cal, "default_reader", lambda ask=input: (lambda label: pytest.fail("no key press expected")))
    monkeypatch.setattr("builtins.input", lambda prompt="": next(answers))
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


# ---------------------------------------------------------------- hold / gap / admin
class FakeInput:
    """Stands in for pydirectinput: records the exact call order, including sleeps."""
    def __init__(self):
        self.calls = []

    def keyDown(self, key):
        self.calls.append(("down", key))

    def keyUp(self, key):
        self.calls.append(("up", key))

    def press(self, key):                       # must never be used: it is instantaneous
        self.calls.append(("press", key))


def test_send_key_holds_between_down_and_up():
    fake, sleeps = FakeInput(), []
    b = mb.DirectInputBackend("pause", input_module=fake,
                              sleep=lambda s: (fake.calls.append(("sleep", s)), sleeps.append(s)))
    b.press("e")
    assert fake.calls == [("down", "e"), ("sleep", 0.08), ("up", "e")]
    assert not any(c[0] == "press" for c in fake.calls)


def test_hold_is_configurable_and_key_is_released_on_error():
    fake = FakeInput()

    def boom(_):
        raise RuntimeError("interrupted")
    b = mb.DirectInputBackend("pause", hold=0.12, input_module=fake, sleep=boom)
    with pytest.raises(RuntimeError):
        b.send_key("q")
    assert fake.calls == [("down", "q"), ("up", "q")]            # never left stuck down
    fake2, slept = FakeInput(), []
    mb.DirectInputBackend("pause", hold=0.12, input_module=fake2, sleep=slept.append).send_key("z")
    assert slept == [0.12]


def test_every_key_is_followed_by_at_least_150ms_times_scale(data, profile):
    plan = mb.build_plan(data, profile)
    for s in plan.steps:                                          # even a zero-delay step gets the minimum gap
        if s.kind == "key" and not s.exact:
            s.seconds = 0.0
    for scale in (1.0, 1.5):
        sleeps = []
        mb.run_plan(plan, profile, mb.DryRunBackend(), sleep=sleeps.append, delay_scale=scale)
        assert len(sleeps) >= plan.counts()["key"]
        exact = round(0.10 * scale, 9)
        assert all(x >= 0.15 * scale - 1e-9 or round(x, 9) == exact for x in sleeps)   # only the 100ms modal step is shorter
        assert sum(1 for x in sleeps if round(x, 9) == exact) == 23


def test_modal_nav_up_pause_is_exactly_100ms_scaled(data, profile):
    plan, sleeps = mb.build_plan(data, profile, prune_limit=1), []
    mb.run_plan(plan, profile, mb.DryRunBackend(), sleep=sleeps.append, delay_scale=1.5)
    assert [round(x, 3) for x in sleeps] == [0.225, 0.15, 0.9]        # 150ms, 100ms, 600ms all x1.5


def test_live_run_uses_hold_through_the_real_backend_class(data, profile):
    fake, sleeps = FakeInput(), []
    b = mb.DirectInputBackend("pause", input_module=fake, sleep=sleeps.append)
    b.foreground_title = lambda: "Madden NFL 27"
    b.abort_requested = lambda: False
    plan = mb.build_plan(data, profile, prune_limit=2)
    mb.run_plan(plan, profile, b, sleep=lambda s: None, live=True)
    assert fake.calls == [c for k in ("e", "up", "space") for c in (("down", k), ("up", k))] * 2
    assert sleeps == [0.08] * 6


def test_is_admin_is_tri_state():
    assert mb.is_admin() in (True, False, None)


@pytest.mark.parametrize("admin,expected", [(False, "not elevated"), (None, "Administrator PowerShell")])
def test_cli_warns_when_not_elevated(monkeypatch, capsys, admin, expected):
    monkeypatch.setattr(mb, "is_admin", lambda: admin)
    monkeypatch.setattr(mb, "DirectInputBackend", lambda ks, hold=0.08: mb.DryRunBackend())
    assert main(["inject", "--run", "--yes", "--start-delay", "0", "--delay-scale", "0", "--prune-limit", "1"]) == 0
    assert expected in " ".join(capsys.readouterr().out.split())


def test_cli_does_not_warn_when_elevated(monkeypatch, capsys):
    monkeypatch.setattr(mb, "is_admin", lambda: True)
    monkeypatch.setattr(mb, "DirectInputBackend", lambda ks, hold=0.08: mb.DryRunBackend())
    assert main(["inject", "--run", "--yes", "--start-delay", "0", "--delay-scale", "0", "--prune-limit", "1"]) == 0
    out = " ".join(capsys.readouterr().out.split())
    assert "not elevated" not in out and "Administrator" not in out


def test_cli_passes_hold_to_backend(monkeypatch):
    seen = {}

    def fake(ks, hold=0.08):
        seen["hold"] = hold
        return mb.DryRunBackend()
    monkeypatch.setattr(mb, "DirectInputBackend", fake)
    main(["inject", "--run", "--yes", "--start-delay", "0", "--delay-scale", "0", "--prune-limit", "1", "--hold", "0.12"])
    assert seen["hold"] == 0.12
