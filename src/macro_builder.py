"""Keyboard macro that applies the built playbook through Madden 27's Creation Center (PC).

UI model (from the on-screen control hints; see ASSUMPTIONS for the parts still inferred):
  * Tabs, left to right: AUDIBLES, MY PLAYBOOK, ALL PLAYS, MY GAMEPLAN; Z / C switch tabs.
  * MY PLAYBOOK / AUDIBLES select a formation GROUP with LCTRL (Nickel, Dime, 3-4, 4-3 ...). LSHIFT does NOT
    step through sets: it opens a "SELECT SET" dropdown listing the group's sets vertically, which must be
    navigated with the arrow keys and confirmed with SPACE; any other key while it is open leaks into the screen
    behind it (the model treats that as an error).
  * Prune: on MY PLAYBOOK, select the set and press E; a "REMOVE PLAY" modal opens with the cursor on NO, so
    NAV_UP (to YES) and CONFIRM (SPACE) are needed to remove all of its plays; an empty set is gone.
  * Audibles: on AUDIBLES, arrow to the play and press the slot hotkey (top Q, left E, right Z, bottom C).
The plan is built closed-loop against ``UIModel`` (every key press is applied to the model while planning) and
``verify_plan`` replays it on a fresh model and checks the result against the cheat sheet. That proves the plan is
consistent with the model, not that the model matches the game; every inference is listed in ``ASSUMPTIONS`` and
printed before a live run. Only keyboard input is sent (pydirectinput); no game memory or files are touched.
"""
from __future__ import annotations

import json
import re
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Callable

from .calibration import (CONTEXTS, DEFAULT_ASSUME, DEFAULT_DELAYS, KILLSWITCH_VK, PROMPTS, conflict)
from .parser import split_formation_name

SLOT_TYPES = ("man_pressure", "sim_pressure", "two_high", "split_match")   # slots 1..4
SLOT_POSITION = {1: "top", 2: "left", 3: "right", 4: "bottom"}
SLOT_BUTTON = {1: "Y", 2: "X", 3: "B", 4: "A"}
REQUIRED_KEYS = [k for k, _, _ in PROMPTS]
TABS = ("AUDIBLES", "MY PLAYBOOK", "ALL PLAYS", "MY GAMEPLAN")

# Measured on the real game: the REMOVE PLAY modal takes ~500 ms to fade out and rebuild the list, and the
# group/set header needs a moment after each cycle key. These are floors, so an older saved profile that still
# holds the previous (shorter) values cannot bring the desync back.
MIN_REMOVE_SETTLE = 0.6
MIN_CYCLE_SETTLE = 0.2
MIN_SET_OPEN = 0.2        # SELECT SET dropdown render time after LSHIFT (chosen, not measured)
MIN_SET_CONFIRM = 0.3     # dropdown close + header update after SPACE (chosen, not measured)

ASSUMPTIONS = [
    "Start on the MY PLAYBOOK tab with the FIRST formation group and its FIRST set selected.",
    "LCTRL cycles to the next formation group (forward, wrapping) and selects that group's first set.",
    "LSHIFT opens the SELECT SET dropdown on the current set (assume.dropdown_starts_on_current); the arrow keys "
    "move its cursor (no wrap) and SPACE selects. The dropdown lists only the sets still in the playbook.",
    "E opens a REMOVE PLAY confirmation (cursor starts on NO); NAV_UP moves it to YES and CONFIRM (SPACE) removes "
    "every play of the set. The emptied set leaves the cycle and selection lands on the next set (wrapping) - "
    "unless assume.empty_sets_remain is true.",
    "In-game group/set order matches huddle.gg (or the profile's formation_order).",
    "Switching tabs resets the selection to the first group/set - unless assume.tab_resets_selection is false.",
    "On AUDIBLES a set's plays are listed alphabetically, the play cursor starts on the first play and "
    "stays on a play after its slot key is pressed.",
    "The added formation is appended to the end of its group's sets.",
]


class MacroError(Exception):
    pass


class Aborted(MacroError):
    """Killswitch pressed."""


class FocusLost(MacroError):
    """Game window is not the foreground window."""


# ------------------------------------------------------------------- inputs
def parse_cheat_sheet(text: str) -> dict[str, dict[int, tuple[str, str]]]:
    """{formation: {slot: (button, play)}} from AUDIBLES_CHEAT_SHEET.md."""
    out: dict[str, dict[int, tuple[str, str]]] = {}
    cur = None
    for line in text.splitlines():
        h = re.match(r"^##\s+(.+?)\s{2}\(", line)
        if h:
            cur = h.group(1).strip()
            out[cur] = {}
            continue
        m = re.match(r"^\|\s*([1-4])\s*\|\s*([A-Z])\b[^|]*\|[^|]*\|\s*\*\*(.+?)\*\*\s*\|", line)
        if m and cur:
            out[cur][int(m.group(1))] = (m.group(2), m.group(3))
    return out


def expected_bindings(data: dict) -> dict[str, dict[int, str]]:
    return {f["name"]: {i + 1: f["audibles"][t] for i, t in enumerate(SLOT_TYPES)} for f in data["formations"]}


def load_inputs(playbook: Path, cheat_sheet: Path | None = None) -> dict:
    data = json.loads(Path(playbook).read_text())
    if cheat_sheet is not None:
        sheet = parse_cheat_sheet(Path(cheat_sheet).read_text())
        want = expected_bindings(data)
        for name, slots in want.items():
            got = {s: (b, p) for s, (b, p) in sheet.get(name, {}).items()}
            exp = {s: (SLOT_BUTTON[s], p) for s, p in slots.items()}
            if got != exp:
                raise MacroError(f"cheat sheet and playbook JSON disagree for {name}: {got} != {exp}; "
                                 "rebuild both from the same build")
    return data


def load_profile(path: Path) -> dict:
    p = json.loads(Path(path).read_text())
    for key in ("window_title", "keys"):
        if key not in p:
            raise MacroError(f"profile missing '{key}'")
    missing = [k for k in REQUIRED_KEYS if not p["keys"].get(k)]
    if missing:
        raise MacroError(f"profile keys not set: {', '.join(missing)} (run `python cli.py calibrate`)")
    for action in REQUIRED_KEYS:
        other = conflict(p["keys"], action, p["keys"][action])
        if other:
            raise MacroError(f"{action} and {other} share key '{p['keys'][action]}' on the same screen; "
                             "re-run `python cli.py calibrate`")
    p["delays"] = {**DEFAULT_DELAYS, **p.get("delays", {})}
    p["assume"] = {**DEFAULT_ASSUME, **p.get("assume", {})}
    p.setdefault("killswitch", "pause")
    p.setdefault("calibrated", False)
    p.setdefault("unverified", [])
    if p["killswitch"] not in KILLSWITCH_VK:
        raise MacroError(f"killswitch '{p['killswitch']}' unsupported; use one of {', '.join(sorted(KILLSWITCH_VK))}")
    if p["killswitch"] in p["keys"].values():
        raise MacroError("killswitch key is also bound to a menu action; re-run calibrate")
    return p


# ------------------------------------------------------------------ UI model
class UIModel:
    """Minimal model of the Creation Center selection state: tab, formation group, set, play cursor."""

    def __init__(self, names: list[str], plays: dict[str, list[str]], assume: dict, tab: str = "MY PLAYBOOK"):
        self.groups: list[str] = []
        self.sets: dict[str, list[str]] = {}
        for n in names:
            g, s = split_formation_name(n)
            if g not in self.sets:
                self.groups.append(g)
                self.sets[g] = []
            self.sets[g].append(s)
        self.plays, self.assume = plays, assume
        self.tab, self.g, self.s, self.pcur = TABS.index(tab), 0, 0, 0
        self.removed: list[str] = []
        self.bindings: dict[str, dict[int, str]] = {}
        self.modal: str | None = None          # None, or the modal cursor: "NO" (default) / "YES"
        self.dropdown: int | None = None       # None, or the cursor row inside the SELECT SET dropdown

    @property
    def current(self) -> tuple[str, str]:
        return self.groups[self.g], self.sets[self.groups[self.g]][self.s]

    def names(self) -> list[str]:
        return [f"{g} {s}" for g in self.groups for s in self.sets[g]]

    def locate(self, name: str) -> tuple[str, str]:
        g, s = split_formation_name(name)
        if g not in self.sets or s not in self.sets[g]:
            raise MacroError(f"'{name}' is not in the formation list the macro expects")
        return g, s

    def _remove_current(self) -> None:
        g, s = self.current
        self.removed.append(f"{g} {s}")
        if not self.assume["empty_sets_remain"]:
            self.sets[g].pop(self.s)
            if not self.sets[g]:
                del self.sets[g]
                self.groups.pop(self.g)
                self.g, self.s = (self.g % len(self.groups) if self.groups else 0), 0
            else:
                self.s %= len(self.sets[g])

    def apply(self, action: str) -> None:
        if self.modal is not None:                 # REMOVE PLAY confirmation is open: only these keys act
            if action == "up":
                self.modal = "YES"
            elif action == "down":
                self.modal = "NO"
            elif action == "confirm":
                if self.modal == "YES":
                    self._remove_current()
                self.modal = None                  # NO (the default) just dismisses it
            elif action == "back":
                self.modal = None
            else:
                raise MacroError(f"'{action}' pressed while the REMOVE PLAY confirmation is open")
            return
        if self.dropdown is not None:              # SELECT SET dropdown is open: it owns the keyboard
            n = len(self.sets[self.groups[self.g]])
            if action == "down":
                self.dropdown = min(self.dropdown + 1, n - 1)
            elif action == "up":
                self.dropdown = max(self.dropdown - 1, 0)
            elif action == "confirm":
                self.s, self.pcur, self.dropdown = self.dropdown, 0, None
            elif action == "back":
                self.dropdown = None
            else:
                raise MacroError(f"'{action}' pressed while the SELECT SET dropdown is open")
            return
        if action in ("tab_left", "tab_right"):
            self.tab = max(0, min(self.tab + (-1 if action == "tab_left" else 1), len(TABS) - 1))
            self.pcur = 0
            if self.assume["tab_resets_selection"]:
                self.g = self.s = 0
        elif action == "formation_cycle":
            self.g, self.s, self.pcur = (self.g + 1) % len(self.groups), 0, 0
        elif action == "set_cycle":                # LSHIFT: opens the SELECT SET dropdown
            if TABS[self.tab] not in ("AUDIBLES", "MY PLAYBOOK"):
                raise MacroError("set menu opened outside MY PLAYBOOK / AUDIBLES")
            self.dropdown = self.s if self.assume["dropdown_starts_on_current"] else 0
        elif action == "remove_all":
            if TABS[self.tab] != "MY PLAYBOOK":
                raise MacroError("remove_all pressed outside MY PLAYBOOK")
            self.modal = "NO"                      # opens the confirmation; nothing is removed yet
        elif action in ("up", "down"):
            if TABS[self.tab] == "AUDIBLES":
                n = len(self.plays.get(" ".join(self.current), []))
                self.pcur = max(0, min(self.pcur + (1 if action == "down" else -1), max(n - 1, 0)))
        elif action.startswith("audible_slot_"):
            if TABS[self.tab] != "AUDIBLES":
                raise MacroError("audible slot pressed outside AUDIBLES")
            name = " ".join(self.current)
            plist = self.plays.get(name)
            if not plist:
                raise MacroError(f"audible bound inside '{name}', which is not a kept formation")
            self.bindings.setdefault(name, {})[int(action[-1])] = plist[self.pcur]


def _initial_names(data: dict, profile: dict) -> list[str]:
    """In-game set list: base order (or the profile override) with added fronts appended to their group."""
    gb = data["global_budget"]
    names = list(profile.get("formation_order") or gb["base_order"])
    for x in gb["added_fronts"]:
        g = split_formation_name(x["name"])[0]
        idx = max((i for i, n in enumerate(names) if split_formation_name(n)[0] == g), default=len(names) - 1)
        names.insert(idx + 1, x["name"])
    return names


# --------------------------------------------------------------------- plan
@dataclass
class Step:
    kind: str                  # key | wait | section
    value: str = ""            # key name (key) / label (section)
    seconds: float = 0.0
    action: str = ""           # logical action for key steps
    exact: bool = False        # True: pause exactly `seconds` (x delay_scale), without the minimum key gap


@dataclass
class Plan:
    steps: list[Step] = field(default_factory=list)
    preconditions: list[str] = field(default_factory=list)

    def counts(self) -> dict[str, int]:
        c: dict[str, int] = {}
        for s in self.steps:
            c[s.kind] = c.get(s.kind, 0) + 1
        return c

    def to_json(self) -> str:
        return json.dumps({"preconditions": self.preconditions, "assumptions": ASSUMPTIONS,
                           "steps": [asdict(s) for s in self.steps]}, indent=1)


class _Builder:
    """Records steps while applying every key to the model (closed-loop planning)."""

    def __init__(self, profile: dict, model: UIModel):
        self.plan, self.keys, self.d, self.model = Plan(), profile["keys"], profile["delays"], model

    def press(self, action: str, wait: float | None = None, exact: bool = False) -> None:
        self.plan.steps.append(Step("key", self.keys[action], self.d["key"] if wait is None else wait, action, exact))
        self.model.apply(action)

    def remove_set(self) -> None:
        """E -> 150ms -> NAV_UP (NO -> YES) -> 100ms -> CONFIRM -> 600ms (modal fades out, list rebuilds)."""
        self.press("remove_all", wait=self.d["remove_open"])
        self.press("up", wait=self.d["remove_move"], exact=True)
        self.press("confirm", wait=max(self.d["remove_wait"], MIN_REMOVE_SETTLE))   # modal fade-out + list rebuild

    def wait(self, seconds: float) -> None:
        self.plan.steps.append(Step("wait", seconds=seconds))

    def section(self, label: str) -> None:
        self.plan.steps.append(Step("section", label))

    def goto(self, name: str) -> None:
        """LCTRL to the target group; then, if needed, LSHIFT -> arrows down/up the dropdown -> SPACE."""
        g, s = self.model.locate(name)
        settle = max(self.d.get("cycle_settle", MIN_CYCLE_SETTLE), MIN_CYCLE_SETTLE)   # header updates after LCTRL
        for _ in range(len(self.model.groups)):
            if self.model.groups[self.model.g] == g:
                break
            self.press("formation_cycle", wait=settle)
        if self.model.sets[g][self.model.s] != s:
            self.select_set(self.model.sets[g].index(s))
        if self.model.current != (g, s):
            raise MacroError(f"could not reach '{name}'")

    def select_set(self, index: int) -> None:
        """Open SELECT SET, move the dropdown cursor to `index` with the arrow keys, confirm with SPACE."""
        self.press("set_cycle", wait=max(self.d.get("set_open", MIN_SET_OPEN), MIN_SET_OPEN))
        for _ in range(len(self.model.sets[self.model.groups[self.model.g]])):
            if self.model.dropdown == index:
                break
            self.press("down" if index > self.model.dropdown else "up")
        if self.model.dropdown != index:
            raise MacroError("could not position the SELECT SET dropdown")
        self.press("confirm", wait=max(self.d.get("set_confirm", MIN_SET_CONFIRM), MIN_SET_CONFIRM))

    def scroll_to(self, index: int) -> None:
        """Relative play-list navigation."""
        while self.model.pcur != index:
            self.press("down" if index > self.model.pcur else "up")


def build_plan(data: dict, profile: dict, prune_limit: int | None = None) -> Plan:
    """Compile the zero-prompt plan: prune the unneeded sets on MY PLAYBOOK, then bind 4 audibles per kept set.

    ``prune_limit=N`` builds a short test plan that only removes the first N sets (no audibles), to check the
    UI model against the real game before the full run."""
    gb = data.get("global_budget")
    if not gb or "base_order" not in gb or any("in_game_plays" not in f for f in data["formations"]):
        raise MacroError("playbook JSON lacks list-order data; rebuild with `build --base vikings`")
    names = _initial_names(data, profile)
    pruned = list(gb["pruned"])
    unknown = [n for n in pruned if n not in names]
    if unknown:
        raise MacroError(f"formations to prune not in the formation order: {unknown}")
    plays = {f["name"]: f["in_game_plays"] for f in data["formations"]}
    model = UIModel(names, plays, profile["assume"])
    b = _Builder(profile, model)
    b.plan.preconditions = [
        *[f"Add '{x['name']}' (from {', '.join(x['from'])}) to the playbook before the run." for x in gb["added_fronts"]],
        "Open Creation Center > MY PLAYBOOK with the FIRST formation group and its FIRST set selected.",
        f"The macro will REMOVE ALL PLAYS from {len(pruned)} sets: " + ", ".join(pruned),
    ]

    order = {n: i for i, n in enumerate(names)}
    targets = sorted(pruned, key=order.get)[:prune_limit]
    if prune_limit is not None:
        b.plan.preconditions.append(f"TEST PLAN: only the first {len(targets)} removal(s); no audibles are bound.")
    b.section(f"prune {len(targets)} set(s) on MY PLAYBOOK")
    for name in targets:
        b.goto(name)
        b.remove_set()
    if prune_limit is not None:
        return b.plan

    b.section("bind audibles on AUDIBLES")
    b.press("tab_left", wait=b.d["menu"])             # MY PLAYBOOK -> AUDIBLES
    kept = [n for n in model.names() if n in plays]
    for f in kept:
        b.goto(f)
        fm = next(x for x in data["formations"] if x["name"] == f)
        todo = []
        for slot, t in enumerate(SLOT_TYPES, start=1):
            play = fm["audibles"][t]
            if play not in fm["in_game_plays"]:
                raise MacroError(f"{f}: audible play '{play}' is not in the in-game play list")
            todo.append((fm["in_game_plays"].index(play), slot))
        for idx, slot in sorted(todo):               # ascending list position = fewest scroll presses
            b.scroll_to(idx)
            b.press(f"audible_slot_{slot}", wait=b.d["menu"])
        b.wait(b.d["section"] / 3)
    return b.plan


def simulate_plan(plan: Plan, profile: dict, data: dict) -> dict:
    """Replay the plan on a fresh model; returns the final set list, removed sets and audible bindings."""
    model = UIModel(_initial_names(data, profile), {f["name"]: f["in_game_plays"] for f in data["formations"]},
                    profile["assume"])
    for s in plan.steps:
        if s.kind == "key":
            model.apply(s.action)
    return {"list": model.names(), "removed": model.removed, "bindings": model.bindings}


def verify_plan(plan: Plan, profile: dict, data: dict, sheet_path: Path | None = None,
                prune_limit: int | None = None) -> str:
    """Prove the plan removes exactly the pruned sets and yields exactly the cheat-sheet audibles."""
    gb = data["global_budget"]
    sim = simulate_plan(plan, profile, data)
    if prune_limit is not None:
        names = _initial_names(data, profile)
        want = sorted(gb["pruned"], key=names.index)[:prune_limit]
        if sim["removed"] != want or sim["bindings"]:
            raise MacroError("test plan does not remove exactly the first sets")
        return f"test plan: {len(want)} set(s) emptied, no audibles"
    if sorted(sim["removed"]) != sorted(gb["pruned"]):
        raise MacroError(f"plan removes the wrong sets: {sorted(set(sim['removed']) ^ set(gb['pruned']))}")
    if sim["bindings"] != expected_bindings(data):
        raise MacroError("plan binds different audibles than the playbook JSON")
    if sheet_path is not None:
        sheet = parse_cheat_sheet(Path(sheet_path).read_text())
        if {n: {s: p for s, (_, p) in v.items()} for n, v in sheet.items()} != sim["bindings"]:
            raise MacroError("plan does not match the cheat sheet")
    return f"{sum(len(v) for v in sim['bindings'].values())} audibles bound, {len(sim['removed'])} sets emptied"


# ------------------------------------------------------------------- runner
class Backend:
    """Interface; DryRunBackend and DirectInputBackend implement it."""
    def press(self, key: str) -> None: ...
    def foreground_title(self) -> str: ...
    def abort_requested(self) -> bool: ...


class DryRunBackend(Backend):
    def __init__(self, title: str = "Madden NFL 27", abort_after: int | None = None,
                 title_after: tuple[int, str] | None = None):
        self.title, self.log, self.abort_after, self.title_after = title, [], abort_after, title_after

    def press(self, key):
        self.log.append(("key", key))

    def foreground_title(self):
        if self.title_after and len(self.log) >= self.title_after[0]:
            return self.title_after[1]
        return self.title

    def abort_requested(self):
        return self.abort_after is not None and len(self.log) >= self.abort_after


HOLD_SECONDS = 0.08       # DirectX games sample input per frame: a tap shorter than a frame is dropped
MIN_KEY_GAP = 0.15        # minimum pause after every key press (scaled by --delay-scale)


def is_admin() -> bool | None:
    """True/False on Windows (process elevation); None elsewhere."""
    try:
        import ctypes
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except (AttributeError, OSError, ImportError):
        return None


class DirectInputBackend(Backend):
    """Windows-only. Sends real key presses: keyDown, hold ~80 ms, keyUp (an instant press() is dropped by
    the game's per-frame input sampling). The Windows polling methods are not exercised by the test-suite."""

    def __init__(self, killswitch: str = "pause", hold: float = HOLD_SECONDS, *, input_module=None,
                 sleep: Callable[[float], None] = time.sleep):
        self._ct = None
        if input_module is None:   # pragma: no cover
            try:
                import ctypes
                import pydirectinput as input_module
            except ImportError as e:
                raise MacroError("pydirectinput is required for live runs: pip install pydirectinput (Windows)") from e
            if not hasattr(ctypes, "windll"):
                raise MacroError("live runs are Windows-only")
            self._ct = ctypes
            input_module.PAUSE = 0.0
        self._pdi, self.hold, self._sleep = input_module, hold, sleep
        self._vk = KILLSWITCH_VK[killswitch]

    def send_key(self, key: str) -> None:
        """keyDown, hold, keyUp. keyUp always runs so a key is never left stuck down."""
        self._pdi.keyDown(key)
        try:
            self._sleep(self.hold)
        finally:
            self._pdi.keyUp(key)

    def press(self, key):
        self.send_key(key)

    def foreground_title(self):   # pragma: no cover
        u = self._ct.windll.user32
        buf = self._ct.create_unicode_buffer(256)
        u.GetWindowTextW(u.GetForegroundWindow(), buf, 256)
        return buf.value

    def abort_requested(self):   # pragma: no cover
        return bool(self._ct.windll.user32.GetAsyncKeyState(self._vk) & 0x8000)


def run_plan(plan: Plan, profile: dict, backend: Backend, *, delay_scale: float = 1.0,
             sleep: Callable[[float], None] = time.sleep, live: bool = False) -> int:
    """Execute the plan. Raises Aborted / FocusLost; returns number of key presses."""
    if live and not profile.get("calibrated"):
        raise MacroError("profile is not calibrated; run `python cli.py calibrate`")
    if live and profile.get("unverified"):
        raise MacroError(f"unverified keys remain: {', '.join(profile['unverified'])}; run `python cli.py calibrate`")
    title, presses = profile["window_title"], 0
    for step in plan.steps:
        if backend.abort_requested():
            raise Aborted("killswitch pressed")
        if step.kind == "key":
            if title.lower() not in backend.foreground_title().lower():
                raise FocusLost(f"foreground window is not '{title}'")
            backend.press(step.value)
            presses += 1
            # never fire the next key inside the animation (the REMOVE PLAY modal steps use their exact timing)
            sleep((step.seconds if step.exact else max(step.seconds, MIN_KEY_GAP)) * delay_scale)
        elif step.kind == "wait":
            sleep(step.seconds * delay_scale)
    return presses
