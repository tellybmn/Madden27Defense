"""Option A (read-only): list Madden 27 PC profile/save files so their format can be assessed.

This tool NEVER writes. Direct injection into Madden's playbook/profile data is intentionally not implemented:
the format is proprietary and undocumented, a wrong byte can corrupt a profile, and modifying game data
may conflict with EA's terms and anti-cheat. Run this on the PC and share the output if you want the file
route investigated further.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path


def candidate_dirs(home: Path | None = None) -> list[Path]:
    home = home or Path(os.environ.get("USERPROFILE", Path.home()))
    docs = home / "Documents"
    return [docs / "Madden NFL 27", docs / "Madden NFL 27" / "settings", docs / "Madden NFL 27" / "save"]


def inspect(dirs: list[Path] | None = None, max_files: int = 200) -> list[dict]:
    rows: list[dict] = []
    for d in dirs or candidate_dirs():
        if not d.is_dir():
            continue
        for p in sorted(d.rglob("*"))[:max_files]:
            if p.is_file():
                with p.open("rb") as fh:
                    head = fh.read(16)
                rows.append({"path": str(p), "bytes": p.stat().st_size, "magic": head.hex(),
                             "sha256_16": hashlib.sha256(p.read_bytes()).hexdigest()[:16]})
    return rows
