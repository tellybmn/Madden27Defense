"""Interactive key calibration: records the keys you press and writes data/macro_profile.json.

On Windows the wizard captures a single physical key press (msvcrt). Elsewhere, or if capture fails, it
falls back to typing the key name (pydirectinput names such as ``enter``, ``up``, ``f12``, ``pause``).
"""
from __future__ import annotations

import json
import string
from pathlib import Path
from typing import Callable

# (profile key, label shown to the user, hint)
PROMPTS: list[tuple[str, str, str]] = [
    ("confirm", "SELECT / CONFIRM", "e.g. ENTER or Space"),
    ("back", "BACK / CANCEL", "e.g. Backspace (avoid the killswitch key)"),
    ("up", "NAV_UP", "e.g. Up arrow or W"),
    ("down", "NAV_DOWN", "e.g. Down arrow or S"),
    ("left", "NAV_LEFT", "e.g. Left arrow or A"),
    ("right", "NAV_RIGHT", "e.g. Right arrow or D"),
    ("tab_left", "TAB_LEFT (left shoulder)", "e.g. Q"),
    ("tab_right", "TAB_RIGHT (right shoulder)", "e.g. E"),
    ("delete", "DELETE / REMOVE FORMATION", "the Creation Center delete button"),
    ("assign_audible", "ASSIGN AUDIBLE", "the Creation Center audible trigger button"),
    ("audible_slot_1", "AUDIBLE SLOT 1 - TOP (Y / triangle)", "key that triggers the top face button"),
    ("audible_slot_2", "AUDIBLE SLOT 2 - LEFT (X / square)", "key that triggers the left face button"),
    ("audible_slot_3", "AUDIBLE SLOT 3 - RIGHT (B / circle)", "key that triggers the right face button"),
    ("audible_slot_4", "AUDIBLE SLOT 4 - BOTTOM (A / cross)", "key that triggers the bottom face button"),
]

KNOWN_KEYS = frozenset(
    set(string.ascii_lowercase) | set(string.digits) | {f"f{i}" for i in range(1, 13)} |
    {"enter", "space", "esc", "backspace", "tab", "up", "down", "left", "right", "delete", "insert", "home",
     "end", "pageup", "pagedown", "pause", "shiftleft", "ctrlleft", "altleft", "capslock",
     ",", ".", "/", ";", "'", "[", "]", "-", "=", "\\", "`"})

# Killswitch keys the live backend can poll (Windows virtual-key codes).
KILLSWITCH_VK = {"esc": 0x1B, "pause": 0x13, **{f"f{i}": 0x6F + i for i in range(1, 13)}}
DEFAULT_KILLSWITCH = "pause"

_MSVCRT_PLAIN = {"\r": "enter", " ": "space", "\x08": "backspace", "\x1b": "esc", "\t": "tab"}
_MSVCRT_E0 = {"H": "up", "P": "down", "K": "left", "M": "right", "S": "delete", "R": "insert",
              "G": "home", "O": "end", "I": "pageup", "Q": "pagedown"}
_MSVCRT_00 = {chr(59 + i): f"f{i + 1}" for i in range(10)} | {chr(133): "f11", chr(134): "f12"}


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


def default_profile() -> dict:
    return {
        "_readme": "Written by `python cli.py calibrate`. Keys are pydirectinput key names.",
        "calibrated": False,
        "window_title": "Madden NFL 27",
        "killswitch": DEFAULT_KILLSWITCH,
        "keys": {k: "" for k, _, _ in PROMPTS},
        "delays": {"key": 0.15, "menu": 0.8, "section": 1.5, "delete_wait": 0.2, "confirm_wait": 0.3},
        "sequences": {},
        "formation_order": [],
    }


def run_calibration(profile_path: Path, *, read_key: Callable[[str], str], ask: Callable[[str], str] = input,
                    out: Callable[[str], None] = print) -> dict:
    """Prompt for every key, validate (known, no duplicates), write the profile with calibrated=true."""
    path = Path(profile_path)
    profile = default_profile()
    if path.exists():
        old = json.loads(path.read_text())
        for k in ("window_title", "formation_order", "sequences"):
            if k in old:
                profile[k] = old[k]
        profile["delays"] |= old.get("delays", {})
    used: dict[str, str] = {}
    for key, label, hint in PROMPTS:
        while True:
            out(f"Press the key for {label}  ({hint})")
            name = read_key(label)
            if name not in KNOWN_KEYS:
                out(f"  '{name}' is not a recognised key name; try again.")
            elif name in used:
                out(f"  '{name}' is already bound to {used[name]}; choose a different key.")
            else:
                used[name] = label
                profile["keys"][key] = name
                out(f"  {label} = {name}")
                break
    while True:
        ks = ask(f"KILLSWITCH key [{DEFAULT_KILLSWITCH}] (not ESC if the game uses ESC to back out): ").strip().lower() \
            or DEFAULT_KILLSWITCH
        if ks not in KILLSWITCH_VK:
            out(f"  killswitch must be one of: {', '.join(sorted(KILLSWITCH_VK))}")
        elif ks in used:
            out(f"  '{ks}' is already bound to {used[ks]}; the killswitch must be a different key.")
        else:
            profile["killswitch"] = ks
            break
    profile["calibrated"] = True
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(profile, indent=2))
    tmp.replace(path)
    out(f"Saved {path} (calibrated=true, killswitch={profile['killswitch']}).")
    return profile
