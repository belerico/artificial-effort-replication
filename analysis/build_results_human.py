#!/usr/bin/env python3
"""Build data/results_human.db from the anonymized oTree trial exports.

Input: data/raw/human/day-{1,2}/<game>_custom_export_<date>.csv, one row per
trial, exactly as exported by oTree except that participant emails were replaced
by anonymized ids ("001", "002", ...).

Output: an SQLite database with the same three-table layout as results_llm.db,
so the same queries work on both (participant_id plays the role of model):

    experiments  one row per oTree session (a day's session code and its date)
    runs         one row per participant x task
    puzzles      one row per trial

Values are copied as exported; an empty cell becomes NULL. Three participants
typed a different email on each day, so they received two anonymized ids; they
were linked by hand (SAME_PERSON) and runs.participant_id holds one id per
person, while runs.participant_label keeps the id found in the raw export.
The experimenter's check of the Day-2 session (EXCLUDED) is left out.
Run from repo root:
    uv run python analysis/build_results_human.py
"""

import csv
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw" / "human"
DB = ROOT / "data" / "results_human.db"

# Day-1 id -> day-2 id of the same person (different email typed on each day).
SAME_PERSON = {"001": "002", "011": "010", "034": "030"}

# oTree participant codes that are not participants: id 007 (code nesqagkb) is the
# experimenter checking the Day-2 session before it started (one Sudoku trial
# shown, no answer submitted, no other task).
EXCLUDED = {"nesqagkb"}

SCHEMA = """
CREATE TABLE experiments (
    id INTEGER PRIMARY KEY,
    name TEXT UNIQUE NOT NULL,       -- oTree session code
    day INTEGER NOT NULL,            -- study day (1 or 2)
    created_at TEXT NOT NULL,        -- UTC, first puzzle shown in the session
    completed_at TEXT NOT NULL       -- UTC, last answer submitted in the session
);
CREATE TABLE runs (
    id INTEGER PRIMARY KEY,
    experiment_id INTEGER NOT NULL REFERENCES experiments(id),
    participant_id TEXT NOT NULL,    -- anonymized participant id, one per person
    participant_label TEXT NOT NULL, -- anonymized id as in the raw export
    participant_code TEXT NOT NULL,  -- oTree participant code (one per session)
    game TEXT NOT NULL,
    incentive INTEGER,               -- 1 = bonus per correct answer announced
    num_correct INTEGER,
    num_failed INTEGER,
    num_trials INTEGER,
    UNIQUE(experiment_id, participant_id, game)
);
CREATE TABLE puzzles (
    id INTEGER PRIMARY KEY,
    run_id INTEGER NOT NULL REFERENCES runs(id),
    iteration INTEGER,               -- trial number within the run (1-10)
    attempts INTEGER,
    text TEXT,                       -- puzzle content shown to the participant
    solution TEXT,
    response TEXT,
    is_correct INTEGER,              -- NULL if no answer was submitted
    timestamp REAL,                  -- Unix time (UTC) the puzzle was shown
    response_timestamp REAL,         -- Unix time (UTC) the answer was submitted
    response_time REAL               -- seconds from display to submission
);
"""


def _val(s, cast):
    return None if s == "" else cast(s)


def _iso(ts):
    return datetime.fromtimestamp(ts, timezone.utc).isoformat()


def read_trials():
    """All trial rows, tagged with day and game, in a deterministic order."""
    rows = []
    for path in sorted(RAW.glob("day-*/*_custom_export_*.csv")):
        day = int(path.parent.name.split("-")[1])
        game = path.name.split("_custom_export_")[0]
        with path.open(newline="", encoding="utf-8") as fh:
            for r in csv.DictReader(fh):
                if not re.fullmatch(r"\d{3}", r["participant_label"]):
                    raise ValueError(f"not an anonymized id in {path}: {r['participant_label']!r}")
                if r["participant_code"] in EXCLUDED:
                    continue
                rows.append({**r, "day": day, "game": game})
    rows.sort(
        key=lambda r: (r["day"], r["session_code"], r["participant_label"], r["game"], int(r["iteration"]))
    )
    return rows


def main():
    rows = read_trials()
    DB.unlink(missing_ok=True)
    con = sqlite3.connect(DB)
    con.executescript(SCHEMA)

    sessions = {}
    for r in rows:
        times = [float(t) for t in (r["timestamp"], r["response_timestamp"]) if t]
        s = sessions.setdefault(r["session_code"], {"day": r["day"], "times": []})
        s["times"] += times
    exp_id = {}
    for name, s in sessions.items():
        cur = con.execute(
            "INSERT INTO experiments (name, day, created_at, completed_at) VALUES (?, ?, ?, ?)",
            (name, s["day"], _iso(min(s["times"])), _iso(max(s["times"]))),
        )
        exp_id[name] = cur.lastrowid

    run_id = {}
    for r in rows:
        key = (r["session_code"], r["participant_label"], r["game"])
        if key not in run_id:
            cur = con.execute(
                "INSERT INTO runs (experiment_id, participant_id, participant_label, "
                "participant_code, game, incentive, num_correct, num_failed, num_trials) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    exp_id[r["session_code"]],
                    SAME_PERSON.get(r["participant_label"], r["participant_label"]),
                    r["participant_label"],
                    r["participant_code"],
                    r["game"],
                    _val(r["incentive"], int),
                    _val(r["num_correct"], int),
                    _val(r["num_failed"], int),
                    _val(r["num_trials"], int),
                ),
            )
            run_id[key] = cur.lastrowid
        con.execute(
            "INSERT INTO puzzles (run_id, iteration, attempts, text, solution, response, "
            "is_correct, timestamp, response_timestamp, response_time) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                run_id[key],
                _val(r["iteration"], int),
                _val(r["attempts"], int),
                _val(r["text"], str),
                _val(r["solution"], str),
                _val(r["response"], str),
                _val(r["is_correct"], int),
                _val(r["timestamp"], float),
                _val(r["response_timestamp"], float),
                _val(r["response_time"], float),
            ),
        )
    con.commit()
    con.close()
    people = {SAME_PERSON.get(r["participant_label"], r["participant_label"]) for r in rows}
    print(
        f"{DB.relative_to(ROOT)}: {len(sessions)} sessions, {len(run_id)} runs, "
        f"{len(rows)} trials, {len(people)} participants"
    )


if __name__ == "__main__":
    main()
