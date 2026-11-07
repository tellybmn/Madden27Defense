"""Option B: UI-input macro that applies the built playbook through Madden's Creation Center menus.

Design
  * The macro *plan* (what to press, in order) is generated deterministically from the playbook JSON and
    cross-checked against the markdown cheat sheet. It is fully testable with no game and no Windows.
  * Menu geometry (key sequences, list positions) lives in a user-calibrated profile
    (data/macro_profile.json). This module does not hard-code the game's menu layout, because it could not
    be verified. Where the profile lacks a position, the plan emits a PROMPT step (assist mode) instead of
    guessing: you place the cursor, press ENTER in the console, and the macro continues.
  * A live run is refused unless the profile says ``calibrated: true``.
  * Only keyboard input is sent (pydirectinput). No game memory or game files are touched.
Safety: ESC (configurable) aborts between every step; focus is asserted before every key press.
"""
from __future__ import annotations

import json
import re
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Callable

SLOT_TYPES = ("man_pressure", "sim_pressure", "two_high", "split_match")   # slots 1..4
SLOT_BUTTONS = {1: "Y", 2: "X", 3: "B", 4: "A"}


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


def load_inputs(playbook: Path, cheat_sheet: Path | None = None) -> dict:
    data = json.loads(Path(playbook).read_text())
    if cheat_sheet is not None:
        sheet = parse_cheat_sheet(Path(cheat_sheet).read_text())
        for f in data["formations"]:
            expect = {i + 1: (SLOT_BUTTONS[i + 1], f["audibles"][t]) for i, t in enumerate(SLOT_TYPES)}
            if sheet.get(f["name"]) != expect:
                raise MacroError(f"cheat sheet and playbook JSON disagree for {f['name']}: "
                                 f"{sheet.get(f['name'])} != {expect}; rebuild both from the same build")
    return data


# --------------------------------------------------------------------- plan
@dataclass
class Step:
    kind: str                  # key | wait | prompt | section
    value: str = ""            # key name / message
    seconds: float = 0.0
    note: str = ""


@dataclass
class Plan:
    steps: list[Step] = field(default_factory=list)

    def add(self, kind, value="", seconds=0.0, note=""):
        self.steps.append(Step(kind, value, seconds, note))

    def counts(self) -> dict[str, int]:
        c: dict[str, int] = {}
        for s in self.steps:
            c[s.kind] = c.get(s.kind, 0) + 1
        return c

    def to_json(self) -> str:
        return json.dumps([asdict(s) for s in self.steps], indent=1)


class _Cursor:
    """Tracks the list cursor so navigation can be emitted as relative up/down presses."""

    def __init__(self):
        self.pos: int | None = 0

    def move_to(self, plan: Plan, idx: int, delay: float, keys: dict) -> None:
        if self.pos is None:
            raise MacroError("cursor position unknown")
        d = idx - self.pos
        for _ in range(abs(d)):
            plan.add("key", keys["down" if d > 0 else "up"], delay)
        self.pos = idx


def _seq(plan: Plan, profile: dict, name: str, delay: float, **fmt) -> None:
    for item in profile["sequences"].get(name, []):
        item = item.format(**fmt)
        if item.startswith("wait:"):
            plan.add("wait", seconds=float(item[5:]))
        else:
            plan.add("key", profile["keys"].get(item, item), delay)


def build_plan(data: dict, profile: dict) -> Plan:
    """Compile the macro plan: add hybrid fronts, prune the rest, bind 4 audibles per kept formation."""
    gb = data.get("global_budget")
    if not gb:
        raise MacroError("playbook JSON has no global_budget (rebuild with --base vikings)")
    d, k = profile["delays"], profile["keys"]
    plan = Plan()
    findex, pindex = profile.get("formation_index", {}), profile.get("play_index", {})

    def locate(name: str, cur: _Cursor) -> None:
        if name in findex:
            cur.move_to(plan, findex[name], d["key"], k)
        else:
            plan.add("prompt", f"Highlight formation '{name}' then press ENTER here")
            cur.pos = None

    plan.add("section", note="open editor")
    _seq(plan, profile, "open_editor", d["menu"])
    plan.add("wait", seconds=d["section"])

    plan.add("section", note=f"add {len(gb['added_fronts'])} hybrid front(s)")
    for fr in gb["added_fronts"]:
        plan.add("prompt", f"Open the pool for {', '.join(fr['from'])} and highlight '{fr['name']}', then press ENTER here")
        _seq(plan, profile, "add_formation", d["menu"])
        plan.add("wait", seconds=d["menu"])

    plan.add("section", note=f"prune {len(gb['pruned'])} formation(s)")
    # Known positions are deleted high-to-low so a delete never shifts a position still to be visited.
    known = sorted((n for n in gb["pruned"] if n in findex), key=lambda n: -findex[n])
    cur = _Cursor()
    for name in known:
        cur.move_to(plan, findex[name], d["key"], k)
        _seq(plan, profile, "delete_formation", d["menu"])
    for name in (n for n in gb["pruned"] if n not in findex):
        plan.add("prompt", f"Highlight formation '{name}' then press ENTER here")
        _seq(plan, profile, "delete_formation", d["menu"])

    plan.add("section", note="bind audibles")
    for f in data["formations"]:
        plan.add("prompt", f"Highlight formation '{f['name']}' then press ENTER here")
        _seq(plan, profile, "open_audible_editor", d["menu"])
        cur = _Cursor()
        for i, t in enumerate(SLOT_TYPES, start=1):
            play, button = f["audibles"][t], SLOT_BUTTONS[i]
            idx = pindex.get(f["name"], {}).get(play)
            if idx is None:
                plan.add("prompt", f"[{f['name']}] highlight play '{play}' (slot {i} -> {button}) then press ENTER here")
                cur.pos = None
            else:
                if cur.pos is None:
                    cur.pos = 0
                cur.move_to(plan, idx, d["key"], k)
            _seq(plan, profile, "bind_audible", d["key"], button_key=profile["button_keys"][button])
            plan.add("wait", seconds=d["menu"], note=f"{f['name']} slot {i}={play}")
    return plan


# ------------------------------------------------------------------- runner
class Backend:
    """Interface; DryRunBackend and DirectInputBackend implement it."""
    def press(self, key: str) -> None: ...
    def foreground_title(self) -> str: ...
    def abort_requested(self) -> bool: ...
    def prompt(self, message: str) -> None: ...


class DryRunBackend(Backend):
    def __init__(self, title: str = "Madden NFL 27", abort_after: int | None = None, title_after: tuple[int, str] | None = None):
        self.title, self.log, self.abort_after, self.title_after = title, [], abort_after, title_after

    def press(self, key):
        self.log.append(("key", key))

    def foreground_title(self):
        if self.title_after and len(self.log) >= self.title_after[0]:
            return self.title_after[1]
        return self.title

    def abort_requested(self):
        return self.abort_after is not None and len(self.log) >= self.abort_after

    def prompt(self, message):
        self.log.append(("prompt", message))


class DirectInputBackend(Backend):
    """Windows-only. Not exercised by the test-suite (needs Windows + pydirectinput + the game)."""
    VK = {"esc": 0x1B}

    def __init__(self, killswitch: str = "esc"):
        try:
            import ctypes
            import pydirectinput
        except ImportError as e:   # pragma: no cover
            raise MacroError("pydirectinput is required for live runs: pip install pydirectinput (Windows)") from e
        if not hasattr(ctypes, "windll"):   # pragma: no cover
            raise MacroError("live runs are Windows-only")
        self._ct, self._pdi = ctypes, pydirectinput
        self._vk = self.VK[killswitch]
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

    def prompt(self, message):   # pragma: no cover
        input(f"\n>> {message}\n   (click back into the game window first if needed) ")


def run_plan(plan: Plan, profile: dict, backend: Backend, *, delay_scale: float = 1.0,
             sleep: Callable[[float], None] = time.sleep, live: bool = False) -> int:
    """Execute the plan. Raises Aborted / FocusLost; returns number of key presses."""
    if live and not profile.get("calibrated"):
        raise MacroError("profile is not calibrated (set calibrated=true in data/macro_profile.json after filling it in)")
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
        elif step.kind == "prompt":
            backend.prompt(step.value)
            if title.lower() not in backend.foreground_title().lower():
                raise FocusLost(f"foreground window is not '{title}' after prompt")
    return presses


def load_profile(path: Path) -> dict:
    p = json.loads(Path(path).read_text())
    for key in ("window_title", "keys", "button_keys", "delays", "sequences"):
        if key not in p:
            raise MacroError(f"profile missing '{key}'")
    return p
