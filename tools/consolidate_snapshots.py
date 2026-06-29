#!/usr/bin/env python3
"""
BataviaHeat R290 Snapshot Consolidator

The HACS integration's register offload writes one small ``snap_<ts>.json``
file per poll cycle. This script bulk-loads those JSON snapshots into a single
SQLite database and (by default) deletes the files it has successfully ingested.

Schema:
  snapshots(id, ts, host, slave_id)            -- one row per snapshot file
  readings(snapshot_id, reg_type, address, value)
                                               -- long format, one row per register
  Indexes on readings(address) and snapshots(ts) for fast querying.

Each JSON file looks like:
  {
    "ts": "2026-06-29T12:34:56.789012+00:00",
    "host": "192.168.1.91",
    "slave_id": 1,
    "holding": {"768": 4, "772": 280, ...},
    "input":   {"22": 156, "23": 142, ...}
  }

Usage:
    # One-shot consolidation (delete files after merge):
    python consolidate_snapshots.py --dir /media/Modbus --db /media/Modbus/snapshots.db

    # Keep the JSON files (don't delete):
    python consolidate_snapshots.py --dir /media/Modbus --db /media/Modbus/snapshots.db --keep

    # Run continuously, consolidating every 5 minutes:
    python consolidate_snapshots.py --dir /media/Modbus --db /media/Modbus/snapshots.db --interval 300

Only the standard library is required.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import time
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS snapshots (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    ts        TEXT NOT NULL,
    host      TEXT,
    slave_id  INTEGER
);
CREATE TABLE IF NOT EXISTS readings (
    snapshot_id INTEGER NOT NULL,
    reg_type    TEXT NOT NULL,
    address     INTEGER NOT NULL,
    value       INTEGER,
    FOREIGN KEY (snapshot_id) REFERENCES snapshots(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_snapshots_ts ON snapshots(ts);
CREATE INDEX IF NOT EXISTS idx_readings_addr ON readings(reg_type, address);
"""


def _open_db(db_path: Path) -> sqlite3.Connection:
    """Open the SQLite database, applying the schema and durability pragmas."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    conn.executescript(SCHEMA)
    return conn


def _ingest_file(conn: sqlite3.Connection, path: Path) -> int:
    """Ingest a single snapshot JSON file. Returns the number of readings stored."""
    with open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)

    cur = conn.execute(
        "INSERT INTO snapshots (ts, host, slave_id) VALUES (?, ?, ?)",
        (data.get("ts"), data.get("host"), data.get("slave_id")),
    )
    snapshot_id = cur.lastrowid

    rows: list[tuple[int, str, int, int | None]] = []
    for reg_type in ("holding", "input"):
        for addr, value in (data.get(reg_type) or {}).items():
            try:
                rows.append((snapshot_id, reg_type, int(addr), value))
            except (ValueError, TypeError):
                continue
    if rows:
        conn.executemany(
            "INSERT INTO readings (snapshot_id, reg_type, address, value) "
            "VALUES (?, ?, ?, ?)",
            rows,
        )
    return len(rows)


def consolidate(directory: Path, db_path: Path, keep: bool) -> tuple[int, int]:
    """Consolidate all snap_*.json files in *directory* into *db_path*.

    Returns (files_processed, readings_stored). Each file is committed
    individually, then deleted (unless *keep*), so an interruption never loses
    data and never re-ingests the same file.
    """
    files = sorted(directory.glob("snap_*.json"))
    if not files:
        return (0, 0)

    conn = _open_db(db_path)
    processed = 0
    readings = 0
    try:
        for path in files:
            try:
                n = _ingest_file(conn, path)
                conn.commit()
            except (json.JSONDecodeError, OSError) as err:
                conn.rollback()
                print(f"  ! skipped {path.name}: {err}", file=sys.stderr)
                continue
            readings += n
            processed += 1
            if not keep:
                try:
                    path.unlink()
                except OSError as err:
                    print(f"  ! could not delete {path.name}: {err}", file=sys.stderr)
    finally:
        conn.close()
    return (processed, readings)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dir", required=True, type=Path,
                        help="Directory containing snap_*.json files (e.g. /media/Modbus)")
    parser.add_argument("--db", required=True, type=Path,
                        help="SQLite database file to create/append (e.g. /media/Modbus/snapshots.db)")
    parser.add_argument("--keep", action="store_true",
                        help="Keep JSON files after ingesting (default: delete)")
    parser.add_argument("--interval", type=int, default=0,
                        help="Run continuously, consolidating every N seconds (0 = run once)")
    args = parser.parse_args()

    if not args.dir.is_dir():
        print(f"Directory not found: {args.dir}", file=sys.stderr)
        return 1

    def _run_once() -> None:
        files, readings = consolidate(args.dir, args.db, args.keep)
        stamp = time.strftime("%Y-%m-%d %H:%M:%S")
        if files:
            print(f"[{stamp}] merged {files} file(s), {readings} reading(s) -> {args.db}")
        else:
            print(f"[{stamp}] no new snapshots")

    if args.interval <= 0:
        _run_once()
        return 0

    print(f"Consolidating every {args.interval}s. Press Ctrl+C to stop.")
    try:
        while True:
            _run_once()
            time.sleep(args.interval)
    except KeyboardInterrupt:
        print("\nStopped.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
