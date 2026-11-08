"""Interactive key calibration: records keys and writes data/macro_profile.json.

Madden 27 PC defaults taken from the on-screen Creation Center hints are built in (VERIFIED_DEFAULTS).
Any key without a verified default is never guessed: it goes in UNVERIFIED_KEYS and a profile that still has
unverified keys cannot be used for a live run (currently none).

Keys legitimately repeat across tabs (Z/C switch tabs on MY PLAYBOOK but are audible slots on AUDIBLES;
E removes all plays on MY PLAYBOOK but is the left audible slot on AUDIBLES), so duplicate checks are per context.
"""
from __future__ import annotations

import json
import string
from pathlib import Path
from typing import Callable

# (profile key, label shown to the user, hint)
PROMPTS: list[tuple[str, str, str]] = [
    ("confirm", "SELECT / CONFIRM", "SPACE (the bottom bar shows [SPACE] SELECT)"),
    ("back", "BACK / CANCEL", "Backspace (ESC pops warning prompts)"),
    ("up", "NAV_UP", "Up arrow or W"),
    ("down", "NAV_DOWN", "Down arrow or S"),
    ("left", "NAV_LEFT", "Left arrow or A"),
    ("right", "NAV_RIGHT", "Right arrow or D"),
    ("tab_left", "TAB_LEFT (AUDIBLES <- MY PLAYBOOK <- ALL PLAYS)", "Z"),
    ("tab_right", "TAB_RIGHT", "C"),
    ("formation_cycle", "FORMATION CYCLE (Nickel, Dime, 3-4, 4-3 ...)", "LCTRL"),
    ("set_cycle", "SET CYCLE (2-4, 2-4 Dbl Mug, Over Wide ...)", "LSHIFT"),
    ("remove_all", "ACTIVATE/REMOVE ALL PLAYS in the selected set (MY PLAYBOOK)", "E"),
    ("audible_slot_1", "AUDIBLE SLOT 1 - TOP (AUDIBLES tab)", "Q"),
    ("audible_slot_2", "AUDIBLE SLOT 2 - LEFT (AUDIBLES tab)", "E"),
    ("audible_slot_3", "AUDIBLE SLOT 3 - RIGHT (AUDIBLES tab)", "Z"),
    ("audible_slot_4", "AUDIBLE SLOT 4 - BOTTOM (AUDIBLES tab)", "C"),
]

VERIFIED_DEFAULTS: dict[str, str] = {
    "confirm": "space", "back": "backspace",
    "up": "up", "down": "down", "left": "left", "right": "right",
    "tab_left": "z", "tab_right": "c",
    "formation_cycle": "ctrlleft", "set_cycle": "shiftleft", "remove_all": "e",
    "audible_slot_1": "q", "audible_slot_2": "e", "audible_slot_3": "z", "audible_slot_4": "c",
}
# Keys without a verified default: the profile is marked unverified and live runs are refused until the wizard
# has captured them. Empty now that all four audible slot keys are confirmed.
UNVERIFIED_KEYS: tuple[str, ...] = ()
PROVISIONAL: dict[str, str] = {}
TYPED_ONLY = ("formation_cycle", "set_cycle")      # modifier keys cannot be captured by a console read

# Keys that can be pressed at the same time in the same screen must differ.
CONTEXTS: dict[str, tuple[str, ...]] = {
    "MY PLAYBOOK": ("confirm", "back", "up", "down", "left", "right", "tab_left", "tab_right",
                    "formation_cycle", "set_cycle", "remove_all"),
    "AUDIBLES": ("confirm", "back", "up", "down", "left", "right", "formation_cycle", "set_cycle",
                 "audible_slot_1", "audible_slot_2", "audible_slot_3", "audible_slot_4"),
}

KNOWN_KEYS = frozenset(
    set(string.ascii_lowercase) | set(string.digits) | {f"f{i}" for i in range(1, 13)} |
    {"enter", "space", "esc", "backspace", "tab", "up", "down", "left", "right", "delete", "insert", "home",
     "end", "pageup", "pagedown", "pause", "shiftleft", "shiftright", "ctrlleft", "ctrlright", "altleft",
     "capslock", ",", ".", "/", ";", "'", "[", "]", "-", "=", "\\", "`"})

# Killswitch keys the live backend can poll (Windows virtual-key codes).
KILLSWITCH_VK = {"esc": 0x1B, "pause": 0x13, **{f"f{i}": 0x6F + i for i in range(1, 13)}}
DEFAULT_KILLSWITCH = "pause"

_MSVCRT_PLAIN = {"\r": "enter", " ": "space", "\x08": "backspace", "\x1b": "esc", "\t": "tab"}
_MSVCRT_E0 = {"H": "up", "P": "down", "K": "left", "M": "right", "S": "delete", "R": "insert",
              "G": "home", "O": "end", "I": "pageup", "Q": "pagedown"}
_MSVCRT_00 = {chr(59 + i): f"f{i + 1}" for i in range(10)} | {chr(133): "f11", chr(134): "f12"}

DEFAULT_DELAYS = {"key": 0.15, "menu": 0.8, "section": 1.5, "remove_open": 0.15, "remove_move": 0.10,
                  "remove_wait": 0.3}
DEFAULT_ASSUME = {"empty_sets_remain": False, "tab_resets_selection": True}


def translate_msvcrt(first: str, second: str | None = None) -> str | None:
    """Translate msvcrt.getwch() output (one or two chars) into a pydirectinput key name."""
    if first == "\xe0":
        return _MSVCRT_E0.get(second or "")
    if first == "\x00":
        return _MSVCRT_00.get(second or "")
    if first in _MSVCRT_PLAIN:
        return _MSVCRT_PLAIN[first]
    low = first.lower()
    return low if low in KNOWN_KEYS else None


def default_reader(ask: Callable[[str], str] = input) -> Callable[[str], str]:
    """Capture one key press on Windows; otherwise ask for the key name."""
    try:
        import msvcrt
    except ImportError:
        msvcrt = None

    def read(label: str) -> str:
        if msvcrt is not None:
            first = msvcrt.getwch()
            second = msvcrt.getwch() if first in ("\x00", "\xe0") else None
            name = translate_msvcrt(first, second)
            if name:
                return name
            return ask("  Could not read that key - type its name: ").strip().lower()
        return ask("  Type the key name: ").strip().lower()
    return read


def conflict(keys: dict[str, str], action: str, name: str) -> str | None:
    """Another action bound to `name` in a screen where `action` is also active, if any."""
    for members in CONTEXTS.values():
        if action in members:
            for other in members:
                if other != action and keys.get(other) == name:
                    return other
    return None


def default_profile() -> dict:
    keys = {**VERIFIED_DEFAULTS, **PROVISIONAL}
    return {
        "_readme": "Verified Madden 27 PC defaults (audible slots: top Q, left E, right Z, bottom C).",
        "calibrated": not UNVERIFIED_KEYS,
        "unverified": list(UNVERIFIED_KEYS),
        "window_title": "Madden NFL 27",
        "killswitch": DEFAULT_KILLSWITCH,
        "keys": keys,
        "delays": dict(DEFAULT_DELAYS),
        "assume": dict(DEFAULT_ASSUME),
        "formation_order": [],
    }


def _capture(action: str, label: str, hint: str, keys: dict[str, str], read_key, ask, out) -> str:
    while True:
        default = VERIFIED_DEFAULTS.get(action, "")
        if action in TYPED_ONLY:
            name = ask(f"Type the key name for {label} [{default}]: ").strip().lower() or default
        else:
            out(f"Press the key for {label}  ({hint})")
            name = read_key(label)
        other = conflict(keys, action, name)
        if name not in KNOWN_KEYS:
            out(f"  '{name}' is not a recognised key name; try again.")
        elif other:
            out(f"  '{name}' is already bound to {other} on the same screen; choose a different key.")
        else:
            out(f"  {label} = {name}")
            return name


def run_calibration(profile_path: Path, *, read_key: Callable[[str], str], ask: Callable[[str], str] = input,
                    out: Callable[[str], None] = print) -> dict:
    """Use the verified defaults (confirming the unverified keys) or capture every key; write calibrated=true."""
    path = Path(profile_path)
    profile = default_profile()
    if path.exists():
        old = json.loads(path.read_text())
        for k in ("window_title", "formation_order"):
            if k in old:
                profile[k] = old[k]
        profile["delays"] |= old.get("delays", {})
        profile["assume"] |= old.get("assume", {})
    labels = {k: (lab, hint) for k, lab, hint in PROMPTS}
    use_defaults = ask("Use the verified Madden 27 PC defaults (Z/C tabs, LCTRL/LSHIFT, E, slots Q/E/Z/C)? [Y/n]: "
                       ).strip().lower() not in ("n", "no")
    keys: dict[str, str] = {}
    for action, label, hint in PROMPTS:
        if use_defaults and action in VERIFIED_DEFAULTS:
            keys[action] = VERIFIED_DEFAULTS[action]
        else:
            keys[action] = _capture(action, label, hint, keys, read_key, ask, out)
    profile["keys"] = keys
    while True:
        ks = ask(f"KILLSWITCH key [{DEFAULT_KILLSWITCH}] (not ESC: the game uses it for back-out warnings): "
                 ).strip().lower() or DEFAULT_KILLSWITCH
        if ks not in KILLSWITCH_VK:
            out(f"  killswitch must be one of: {', '.join(sorted(KILLSWITCH_VK))}")
        elif ks in keys.values():
            out(f"  '{ks}' is already bound to a menu action; the killswitch must be a different key.")
        else:
            profile["killswitch"] = ks
            break
    profile["calibrated"] = True
    profile["unverified"] = []
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(profile, indent=2))
    tmp.replace(path)
    out(f"Saved {path} (calibrated=true, killswitch={profile['killswitch']}).")
    return profile
