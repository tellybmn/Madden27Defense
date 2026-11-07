"""Keyboard macro that applies the built playbook through Madden's Creation Center menus.

The plan is fully automatic (zero prompts). It rests on this model of the UI, which could NOT be verified
against the real game from the build environment, so every assumption is listed in ``ASSUMPTIONS`` and printed
before a live run:
  * the formation list is a vertical list; one NAV_DOWN moves to the next row;
  * the in-game order is the huddle.gg order (override with ``formation_order`` in the profile);
  * deleting = DELETE, wait 200 ms, CONFIRM, wait 300 ms; the cursor then rests on the row that slid up;
  * a formation's play list is alphabetical; the cursor starts on the first play when it is opened;
  * an audible is set by highlighting the play, pressing ASSIGN_AUDIBLE, then the slot's face-button key
    (slot 1 top / 2 left / 3 right / 4 bottom).
``simulate_plan`` replays the plan against exactly this model and ``verify_plan`` proves it reproduces the
cheat sheet, so the plan is internally consistent even though the model itself is unverified.
Only keyboard input is sent (pydirectinput); no game memory or files are touched.
"""
from __future__ import annotations

import json
import re
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Callable

from .calibration import KILLSWITCH_VK, PROMPTS

SLOT_TYPES = ("man_pressure", "sim_pressure", "two_high", "split_match")   # slots 1..4
SLOT_POSITION = {1: "top", 2: "left", 3: "right", 4: "bottom"}
SLOT_BUTTON = {1: "Y", 2: "X", 3: "B", 4: "A"}
REQUIRED_KEYS = [k for k, _, _ in PROMPTS]
DEFAULT_DELAYS = {"key": 0.15, "menu": 0.8, "section": 1.5, "delete_wait": 0.2, "confirm_wait": 0.3}

ASSUMPTIONS = [
    "Formation list is vertical: 1x NAV_DOWN moves to the next row; the cursor starts on the FIRST row.",
    "In-game formation order matches huddle.gg (or the profile's formation_order).",
    "Delete = DELETE, wait 200ms, CONFIRM, wait 300ms; afterwards the cursor rests on the row that slid up.",
    "A formation's plays are listed alphabetically; the play cursor starts on the first play.",
    "Audible = highlight play, ASSIGN_AUDIBLE, then slot key (1 top, 2 left, 3 right, 4 bottom).",
    "An added formation is appended at the end of the list.",
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
    names = [p["keys"][k] for k in REQUIRED_KEYS]
    if len(set(names)) != len(names):
        raise MacroError("two actions share the same key; re-run `python cli.py calibrate`")
    p["delays"] = {**DEFAULT_DELAYS, **p.get("delays", {})}
    p.setdefault("killswitch", "pause")
    p.setdefault("calibrated", False)
    if p["killswitch"] not in KILLSWITCH_VK:
        raise MacroError(f"killswitch '{p['killswitch']}' unsupported; use one of {', '.join(sorted(KILLSWITCH_VK))}")
    if p["killswitch"] in names:
        raise MacroError("killswitch key is also bound to a menu action; re-run calibrate")
    return p


# --------------------------------------------------------------------- plan
@dataclass
class Step:
    kind: str                  # key | wait | section
    value: str = ""            # key name (key) / label (section)
    seconds: float = 0.0
    action: str = ""           # logical action for key steps (confirm, down, delete, ...)


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
    def __init__(self, profile: dict):
        self.plan, self.keys, self.d = Plan(), profile["keys"], profile["delays"]
        self.profile = profile

    def key(self, action: str, wait: float | None = None) -> None:
        self.plan.steps.append(Step("key", self.keys[action], self.d["key"] if wait is None else wait, action))

    def wait(self, seconds: float) -> None:
        self.plan.steps.append(Step("wait", seconds=seconds))

    def section(self, label: str) -> None:
        self.plan.steps.append(Step("section", label))

    def move(self, cur: int, target: int) -> int:
        """Relative grid navigation: |delta| presses of NAV_DOWN (or NAV_UP)."""
        for _ in range(abs(target - cur)):
            self.key("down" if target > cur else "up")
        return target

    def delete_row(self) -> None:
        """The fixed delete loop: DELETE -> 200ms -> CONFIRM -> 300ms."""
        self.key("delete", wait=0.0)
        self.wait(self.d["delete_wait"])
        self.key("confirm", wait=0.0)
        self.wait(self.d["confirm_wait"])

    def custom_or(self, name: str, default: Callable[[], None]) -> None:
        seq = self.profile.get("sequences", {}).get(name)
        if not seq:
            default()
            return
        for item in seq:
            if item.startswith("wait:"):
                self.wait(float(item[5:]))
            else:
                self.key(item)

    def enter_formation(self) -> None:
        self.key("confirm", wait=0.0)
        self.wait(self.d["menu"])

    def exit_formation(self) -> None:
        self.key("back", wait=0.0)
        self.wait(self.d["menu"])


def build_plan(data: dict, profile: dict) -> Plan:
    """Compile the zero-prompt plan: prune the unneeded fronts, then bind 4 audibles per kept front."""
    gb = data.get("global_budget")
    if not gb or "base_order" not in gb or any("in_game_plays" not in f for f in data["formations"]):
        raise MacroError("playbook JSON lacks list-order data; rebuild with `build --base vikings`")
    order = list(profile.get("formation_order") or gb["base_order"])
    pruned = list(gb["pruned"])
    added = [x["name"] for x in gb["added_fronts"]]
    unknown = [n for n in pruned if n not in order]
    if unknown:
        raise MacroError(f"formations to prune not in the formation order: {unknown}")

    b = _Builder(profile)
    b.plan.preconditions = [
        *[f"Add '{x['name']}' (from {', '.join(x['from'])}) to the playbook before the run." for x in gb["added_fronts"]],
        "Open the Creation Center defensive formation list with the cursor on the FIRST formation.",
        f"The macro will DELETE {len(pruned)} formations: " + ", ".join(pruned),
    ]

    b.section(f"prune {len(pruned)} formation(s)")
    rows, cur = list(order) + added, 0      # the added front is already appended when the run starts
    for name in order:                     # ascending: each delete only shifts rows that are still ahead
        if name in pruned:
            idx = rows.index(name)
            cur = b.move(cur, idx)
            b.delete_row()
            rows.pop(idx)                  # cursor stays on this index (the next row slid up)
            cur = min(idx, len(rows) - 1)  # ...or the new last row if the deleted one was last

    b.section("bind audibles")
    order_idx = {n: i for i, n in enumerate(rows)}
    for f in sorted(data["formations"], key=lambda f: order_idx[f["name"]]):
        cur = b.move(cur, order_idx[f["name"]])
        b.custom_or("enter_formation", b.enter_formation)
        pcur = 0
        for slot, t in enumerate(SLOT_TYPES, start=1):
            play = f["audibles"][t]
            if play not in f["in_game_plays"]:
                raise MacroError(f"{f['name']}: audible play '{play}' is not in the in-game play list")
            pcur = b.move(pcur, f["in_game_plays"].index(play))
            b.key("assign_audible")
            b.key(f"audible_slot_{slot}", wait=b.d["menu"])
        b.custom_or("exit_formation", b.exit_formation)
        b.wait(b.d["section"] / 3)
    return b.plan


# ---------------------------------------------------------------- simulation
def simulate_plan(plan: Plan, profile: dict, data: dict) -> dict:
    """Replay the plan against the documented UI model; returns final list and audible bindings."""
    gb = data["global_budget"]
    rows = list(profile.get("formation_order") or gb["base_order"]) + [x["name"] for x in gb["added_fronts"]]
    plays = {f["name"]: f["in_game_plays"] for f in data["formations"]}
    cursor, inside, pcur, pending_delete, pending_assign = 0, None, 0, False, None
    bindings: dict[str, dict[int, str]] = {}
    for s in (s for s in plan.steps if s.kind == "key"):
        a = s.action
        n = len(plays.get(inside, [])) if inside else len(rows)
        if n == 0:
            raise MacroError(f"plan navigates an empty list ('{inside or 'formations'}')")
        if a in ("down", "up"):
            delta = 1 if a == "down" else -1
            if inside:
                pcur = max(0, min(pcur + delta, n - 1))
            else:
                cursor = max(0, min(cursor + delta, n - 1))
        elif a == "delete":
            pending_delete = True
        elif a == "confirm":
            if pending_delete:
                rows.pop(cursor)
                cursor = min(cursor, len(rows) - 1)
                pending_delete = False
            elif inside is None:
                inside, pcur = rows[cursor], 0
        elif a == "back":
            inside = None
        elif a == "assign_audible":
            pending_assign = True
        elif a.startswith("audible_slot_") and pending_assign:
            if inside is None or inside not in plays:
                raise MacroError("plan assigns an audible outside a kept formation")
            bindings.setdefault(inside, {})[int(a[-1])] = plays[inside][pcur]
            pending_assign = False
    return {"list": rows, "bindings": bindings}


def verify_plan(plan: Plan, profile: dict, data: dict, sheet_path: Path | None = None) -> str:
    """Prove the plan yields exactly the cheat-sheet audibles and the intended formation list."""
    gb = data["global_budget"]
    sim = simulate_plan(plan, profile, data)
    keep = [n for n in (profile.get("formation_order") or gb["base_order"]) if n not in gb["pruned"]] \
        + [x["name"] for x in gb["added_fronts"]]
    if sim["list"] != keep:
        raise MacroError(f"plan leaves the wrong formation list: {sim['list']}")
    want = expected_bindings(data)
    if sim["bindings"] != want:
        raise MacroError("plan binds different audibles than the playbook JSON")
    if sheet_path is not None:
        sheet = parse_cheat_sheet(Path(sheet_path).read_text())
        if {n: {s: p for s, (_, p) in v.items()} for n, v in sheet.items()} != sim["bindings"]:
            raise MacroError("plan does not match the cheat sheet")
    return f"{sum(len(v) for v in sim['bindings'].values())} audibles bound, {len(gb['pruned'])} deleted, {len(sim['list'])} kept"


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


class DirectInputBackend(Backend):
    """Windows-only. Not exercised by the test-suite (needs Windows + pydirectinput + the game)."""

    def __init__(self, killswitch: str = "pause"):
        try:
            import ctypes
            import pydirectinput
        except ImportError as e:   # pragma: no cover
            raise MacroError("pydirectinput is required for live runs: pip install pydirectinput (Windows)") from e
        if not hasattr(ctypes, "windll"):   # pragma: no cover
            raise MacroError("live runs are Windows-only")
        self._ct, self._pdi = ctypes, pydirectinput
        self._vk = KILLSWITCH_VK[killswitch]
        pydirectinput.PAUSE = 0.0

    def press(self, key):   # pragma: no cover
        self._pdi.press(key)

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
    title, presses = profile["window_title"], 0
    for step in plan.steps:
        if backend.abort_requested():
            raise Aborted("killswitch pressed")
        if step.kind == "key":
            if title.lower() not in backend.foreground_title().lower():
                raise FocusLost(f"foreground window is not '{title}'")
            backend.press(step.value)
            presses += 1
            sleep(step.seconds * delay_scale)
        elif step.kind == "wait":
            sleep(step.seconds * delay_scale)
    return presses
