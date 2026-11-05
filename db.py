"""SQLite access layer: WAL, foreign keys, idempotent upserts."""
from __future__ import annotations

import sqlite3
from pathlib import Path

from parser import ScrapedPlaybook

SCHEMA_PATH = Path(__file__).with_name("schema.sql")
DEFAULT_DB = "madden_defense.db"


def connect(path: str | Path = DEFAULT_DB) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA_PATH.read_text())
    return conn


def _upsert_playbook(conn, name: str, ptype: str) -> int:
    conn.execute(
        "INSERT INTO playbooks(name, playbook_type) VALUES(?, ?) "
        "ON CONFLICT(name) DO UPDATE SET playbook_type = excluded.playbook_type", (name, ptype))
    return conn.execute("SELECT playbook_id FROM playbooks WHERE name = ?", (name,)).fetchone()[0]


def ingest_playbook(conn: sqlite3.Connection, sp: ScrapedPlaybook) -> dict[str, int]:
    """Upsert one scraped playbook in a single transaction. Safe to repeat."""
    with conn:
        pid = _upsert_playbook(conn, sp.name, sp.playbook_type)
        n_plays = 0
        for sf in sp.formations:
            i = sf.info
            conn.execute(
                "INSERT INTO formations(playbook_id, formation_name, set_name, front_type, box_count) "
                "VALUES(?,?,?,?,?) ON CONFLICT(playbook_id, formation_name) DO UPDATE SET "
                "set_name=excluded.set_name, front_type=excluded.front_type, box_count=excluded.box_count",
                (pid, i.formation_name, i.set_name, i.front_type, i.box_count))
            fid = conn.execute(
                "SELECT formation_id FROM formations WHERE playbook_id=? AND formation_name=?",
                (pid, i.formation_name)).fetchone()[0]
            for p in sf.plays:
                conn.execute(
                    "INSERT INTO plays(formation_id, play_name, coverage_family, rush_count, "
                    "is_sim_pressure, is_blitz, is_run_plug) VALUES(?,?,?,?,?,?,?) "
                    "ON CONFLICT(formation_id, play_name) DO UPDATE SET "
                    "coverage_family=excluded.coverage_family, rush_count=excluded.rush_count, "
                    "is_sim_pressure=excluded.is_sim_pressure, is_blitz=excluded.is_blitz, "
                    "is_run_plug=excluded.is_run_plug",
                    (fid, p.play_name, p.coverage_family, p.rush_count,
                     int(p.is_sim_pressure), int(p.is_blitz), int(p.is_run_plug)))
                n_plays += 1
    return {"formations": len(sp.formations), "plays": n_plays}


def counts(conn: sqlite3.Connection) -> dict[str, int]:
    return {t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
            for t in ("playbooks", "formations", "plays")}
