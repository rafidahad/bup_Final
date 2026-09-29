"""Decision audit history (PS §9, §20) in SQLite. Stdlib only."""
import json
import os
import pathlib
import sqlite3
import threading
import time

DB_PATH = pathlib.Path(os.environ.get("FUELOPS_DB", pathlib.Path(__file__).resolve().parent.parent / "data" / "fuelops.db"))

_lock = threading.Lock()
_conn = None


def conn():
    global _conn
    if _conn is None:
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        _conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        _conn.execute("""CREATE TABLE IF NOT EXISTS decisions (
            id INTEGER PRIMARY KEY AUTOINCREMENT, wall REAL, run_id TEXT, tick INTEGER,
            station_id TEXT, fuel TEXT, status TEXT, decided_by TEXT, source TEXT,
            confidence REAL, risk_before REAL, risk_after REAL, liters REAL, card TEXT, outcome TEXT)""")
        _conn.execute("CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT)")
        _conn.execute("""CREATE TABLE IF NOT EXISTS incident_summaries (
            case_id TEXT, version INTEGER, evidence_hash TEXT, source TEXT, body TEXT, model TEXT,
            prompt_version TEXT, generated_at REAL, PRIMARY KEY (case_id, version, evidence_hash))""")
        _conn.execute("""CREATE TABLE IF NOT EXISTS incidents (
            id INTEGER PRIMARY KEY AUTOINCREMENT, wall REAL, run_id TEXT, tick INTEGER, kind TEXT, detail TEXT)""")
        _conn.commit()
    return _conn


def record_decision(run_id, tick, card, status, decided_by, outcome=None):
    with _lock:
        c = conn()
        cur = c.execute(
            "INSERT INTO decisions (wall, run_id, tick, station_id, fuel, status, decided_by, source, confidence,"
            " risk_before, risk_after, liters, card, outcome) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (time.time(), run_id, tick, card["station_id"], card["fuel"], status, decided_by, card["source"],
             card["confidence"], card["before"]["risk"], card["after"]["risk"] if card["after"] else None,
             sum(a["liters"] for a in card["allocations"]), json.dumps(card), json.dumps(outcome)))
        c.commit()
        return cur.lastrowid


def record_incident(run_id, tick, kind, detail):
    with _lock:
        c = conn()
        c.execute("INSERT INTO incidents (wall, run_id, tick, kind, detail) VALUES (?,?,?,?,?)",
                  (time.time(), run_id, tick, kind, detail))
        c.commit()


def decisions(limit=200):
    with _lock:
        rows = conn().execute("SELECT id, wall, run_id, tick, station_id, fuel, status, decided_by, source, confidence,"
                              " risk_before, risk_after, liters, card, outcome FROM decisions ORDER BY id DESC LIMIT ?",
                              (limit,)).fetchall()
    keys = ("id", "wall", "run_id", "tick", "station_id", "fuel", "status", "decided_by", "source", "confidence",
            "risk_before", "risk_after", "liters", "card", "outcome")
    out = []
    for r in rows:
        d = dict(zip(keys, r))
        d["card"], d["outcome"] = json.loads(d["card"]), json.loads(d["outcome"]) if d["outcome"] else None
        out.append(d)
    return out


def healthy():
    try:
        with _lock:
            conn().execute("SELECT 1").fetchone()
        return True
    except sqlite3.Error:
        return False


def get_meta(key):
    with _lock:
        row = conn().execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
    return json.loads(row[0]) if row else None


def set_meta(key, value):
    with _lock:
        c = conn()
        c.execute("INSERT INTO meta (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                  (key, json.dumps(value)))
        c.commit()


def get_summary(case_id, version, evidence_hash):
    with _lock:
        row = conn().execute("SELECT body FROM incident_summaries WHERE case_id=? AND version=? AND evidence_hash=?",
                             (case_id, version, evidence_hash)).fetchone()
    return json.loads(row[0]) if row else None


def save_summary(case_id, version, evidence_hash, body, model, prompt_version):
    with _lock:
        c = conn()
        c.execute("INSERT OR REPLACE INTO incident_summaries VALUES (?,?,?,?,?,?,?,?)",
                  (case_id, version, evidence_hash, body.get("source"), json.dumps(body), model, prompt_version, time.time()))
        c.commit()


def latest_summaries(limit=30):
    """Newest version of each case, newest first."""
    with _lock:
        rows = conn().execute(
            "SELECT case_id, version, source, body, model, generated_at FROM incident_summaries s1 WHERE version = "
            "(SELECT MAX(version) FROM incident_summaries s2 WHERE s2.case_id = s1.case_id) "
            "ORDER BY generated_at DESC LIMIT ?", (limit,)).fetchall()
    return [{"case_id": r[0], "version": r[1], "source": r[2], **json.loads(r[3]), "model": r[4], "generated_at": r[5]}
            for r in rows]
