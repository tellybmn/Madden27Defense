-- madden_defense.db schema. Foreign keys + WAL are enabled by db.connect().
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS playbooks (
    playbook_id   INTEGER PRIMARY KEY,
    name          TEXT NOT NULL UNIQUE,
    playbook_type TEXT NOT NULL DEFAULT 'team' CHECK (playbook_type IN ('team', 'generic'))
);

CREATE TABLE IF NOT EXISTS formations (
    formation_id   INTEGER PRIMARY KEY,
    playbook_id    INTEGER NOT NULL REFERENCES playbooks(playbook_id) ON DELETE CASCADE,
    formation_name TEXT NOT NULL,
    set_name       TEXT NOT NULL,      -- Base / Nickel / Dime / Dollar / Quarter / Goal Line
    front_type     TEXT NOT NULL,      -- e.g. '2-4', '3-4 Bear', '4-2-5 Over G'
    box_count      INTEGER NOT NULL CHECK (box_count BETWEEN 0 AND 11),
    UNIQUE (playbook_id, formation_name)
);

CREATE TABLE IF NOT EXISTS plays (
    play_id         INTEGER PRIMARY KEY,
    formation_id    INTEGER NOT NULL REFERENCES formations(formation_id) ON DELETE CASCADE,
    play_name       TEXT NOT NULL,
    coverage_family TEXT NOT NULL CHECK (coverage_family IN (
        'Cover 0', 'Cover 1', 'Cover 2 Man', 'Tampa 2',
        'Cover 3 Sky/Buzz/Cloud', 'Cover 4 Match/Palms', 'Cover 6/9', 'Unknown')),
    rush_count      INTEGER NOT NULL CHECK (rush_count IN (3, 4, 5, 6)),  -- 3 = "3 or fewer", 6 = "6+"
    is_sim_pressure INTEGER NOT NULL DEFAULT 0 CHECK (is_sim_pressure IN (0, 1)),
    is_blitz        INTEGER NOT NULL DEFAULT 0 CHECK (is_blitz IN (0, 1)),
    is_run_plug     INTEGER NOT NULL DEFAULT 0 CHECK (is_run_plug IN (0, 1)),
    UNIQUE (formation_id, play_name),
    CHECK (NOT (is_sim_pressure = 1 AND is_blitz = 1))     -- strictly differentiated
);

CREATE INDEX IF NOT EXISTS idx_formations_playbook ON formations(playbook_id);
CREATE INDEX IF NOT EXISTS idx_formations_set_front ON formations(set_name, front_type);
CREATE INDEX IF NOT EXISTS idx_plays_formation ON plays(formation_id);
CREATE INDEX IF NOT EXISTS idx_plays_coverage ON plays(coverage_family);
CREATE INDEX IF NOT EXISTS idx_plays_flags ON plays(is_sim_pressure, is_blitz, is_run_plug);
