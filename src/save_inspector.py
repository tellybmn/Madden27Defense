"""Option A (read-only): list Madden 27 PC profile/save files so their format can be assessed.

This tool NEVER writes. Direct injection into Madden's playbook/profile data is intentionally not implemented:
the format is proprietary and undocumented, a wrong byte can corrupt a profile, and modifying game data
may conflict with EA's terms and anti-cheat.
"""
from __future__ import annotations

import os
from pathlib import Path

SAMPLE = 4096


def candidate_dirs(home: Path | None = None, env: dict | None = None) -> list[Path]:
    """Common Madden NFL 27 locations (%USERPROFILE% resolved dynamically, OneDrive-redirected Documents too)."""
    env = os.environ if env is None else env
    home = home or Path(env.get("USERPROFILE") or Path.home())
    docs = [home / "Documents"]
    for var in ("OneDrive", "OneDriveConsumer", "OneDriveCommercial"):
        if env.get(var):
            docs.append(Path(env[var]) / "Documents")
    docs.append(home / "OneDrive" / "Documents")
    out: list[Path] = []
    for d in docs:
        out += [d / "Madden NFL 27" / "settings", d / "Madden NFL 27"]
    out.append(home / "Saved Games" / "Madden NFL 27")
    return list(dict.fromkeys(out))


def classify(sample: bytes) -> str:
    """Rough content kind from the first bytes: json / text / binary / empty."""
    if not sample:
        return "empty"
    try:
        text = sample.decode("utf-8")
    except UnicodeDecodeError:
        return "binary"
    if text.lstrip("﻿ \t\r\n")[:1] in ("{", "["):
        return "json?"
    printable = sum(c.isprintable() or c in "\r\n\t" for c in text) / len(text)
    return "text" if printable > 0.95 else "binary"


def inspect(dirs: list[Path] | None = None) -> tuple[list[Path], list[dict]]:
    """Return (directories that exist, file rows). Files are only read (first 4 KiB), never modified."""
    found, rows, seen = [], [], set()
    for d in dirs or candidate_dirs():
        if not d.is_dir():
            continue
        found.append(d)
        for p in sorted(d.rglob("*")):
            if p.is_file() and p not in seen:
                seen.add(p)
                with p.open("rb") as fh:
                    head = fh.read(SAMPLE)
                rows.append({"path": str(p), "ext": p.suffix.lower() or "(none)", "bytes": p.stat().st_size,
                             "kind": classify(head), "magic": head[:8].hex()})
    return found, rows
