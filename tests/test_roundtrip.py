# -*- coding: utf-8 -*-
"""
test_roundtrip.py

Verifies that every field value noted in the institution's field mapping
reaches the SQLite database without data loss or type corruption.

Strategy: re-run transform in memory on the saved extracted JSON, then
compare sorted value lists per column between the transformed data and
the live DB.  Sorted comparison catches:
  - dropped rows    (list lengths differ)
  - NULL inflation  (a value that became None due to a type mismatch)
  - value corruption (a value that changed during storage/retrieval)

Because there is no shared join key between the extracted data and the DB
rows, comparisons are set-level rather than row-level.

Prerequisites (both must exist before running):
  sql_sync/data/extracted/{institution}.json   — saved via --save-intermediates
  sql_sync/data/ogrre_{institution}.db         — populated by run.py
"""

import json
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "sql_sync"))

from load import load_schema
from transform import load_mapping, transform

_DATA_DIR = Path(__file__).parent.parent / "sql_sync" / "data"


# ── Helpers ───────────────────────────────────────────────────────────────────

def _normalize(val, col_type: str = None):
    """Normalize a value so equivalent representations compare equal.

    Handles:
      bool  → int         (SQLite stores True/False as 1/0)
      float → int         (9210.0 → 9210 for whole numbers, avoiding
                           spurious float-vs-INTEGER mismatches)
      numeric → str       (for TEXT columns: int/float inserted by the
                           pipeline are stored and returned as strings,
                           e.g. 1785 → '1785')
    """
    if val is None:
        return None
    is_text = col_type and col_type.upper() in ("TEXT", "VARCHAR", "CHAR")
    if isinstance(val, bool):
        int_val = int(val)
        return str(int_val) if is_text else int_val
    if is_text:
        if isinstance(val, (int, float)):
            return str(val)
        return val
    # Non-TEXT: coerce numeric strings to numbers (mirrors SQLite's type affinity)
    if isinstance(val, str):
        try:
            f = float(val)
            return int(f) if f == int(f) else f
        except (ValueError, OverflowError):
            pass
    if isinstance(val, float) and val == int(val):
        return int(val)
    return val


def _sorted_vals(rows: list[dict], col: str, col_type: str = None) -> list:
    """Return a sorted list of normalized values for col across all rows."""
    return sorted(
        (_normalize(r.get(col), col_type) for r in rows),
        key=lambda x: (x is None, str(x)),
    )


def _load_extracted(institution: str) -> dict:
    path = _DATA_DIR / "extracted" / f"{institution}.json"
    if not path.exists():
        pytest.skip(
            f"No extracted data at {path}. "
            f"Run: python sql_sync/run.py --institution {institution} "
            f"--db-type sqlite --db-path ... --save-intermediates"
        )
    with open(path) as f:
        return json.load(f)


def _fetch_table(conn: sqlite3.Connection, table: str) -> list[dict]:
    conn.row_factory = sqlite3.Row
    rows = conn.execute(f"SELECT * FROM {table}").fetchall()
    return [dict(r) for r in rows]


def _check_roundtrip(institution: str, conn: sqlite3.Connection, db_type: str) -> None:
    """Core comparison: transformed data vs live DB."""
    extracted = _load_extracted(institution)
    mapping = load_mapping(institution)
    transformed = transform(extracted, mapping)
    schema = load_schema(institution, db_type)

    failures = []

    for table in sorted(transformed):
        if table not in schema:
            continue

        expected_rows = transformed[table]

        try:
            db_rows = _fetch_table(conn, table)
        except Exception as exc:
            failures.append(f"{table}: query failed — {exc}")
            continue

        if len(db_rows) != len(expected_rows):
            failures.append(
                f"{table}: row count — expected {len(expected_rows)}, got {len(db_rows)}"
            )
            continue  # column diffs are misleading when row counts differ

        col_type_map = {c["column_name"]: c["data_type"] for c in schema[table]}
        schema_cols = [c["column_name"] for c in schema[table] if c["column_name"] != "id"]
        for col in schema_cols:
            col_type = col_type_map.get(col)
            expected_vals = _sorted_vals(expected_rows, col, col_type)
            actual_vals = _sorted_vals(db_rows, col, col_type)
            if expected_vals != actual_vals:
                # Use repr() so type differences surface: repr(605) != repr('605')
                exp_set = set(map(repr, expected_vals))
                act_set = set(map(repr, actual_vals))
                only_expected = exp_set - act_set
                only_actual = act_set - exp_set
                detail = []
                if only_expected:
                    detail.append(f"missing from DB: {sorted(only_expected)[:5]}")
                if only_actual:
                    detail.append(f"extra in DB: {sorted(only_actual)[:5]}")
                failures.append(f"{table}.{col}: {'; '.join(detail)}")

    assert not failures, (
        f"{len(failures)} field(s) did not round-trip cleanly:\n"
        + "\n".join(f"  {f}" for f in failures)
    )


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def isgs_sqlite_conn():
    path = _DATA_DIR / "ogrre_isgs.db"
    if not path.exists():
        pytest.skip(f"SQLite DB not found at {path}")
    conn = sqlite3.connect(str(path))
    yield conn
    conn.close()


# ── Tests ─────────────────────────────────────────────────────────────────────

def test_isgs_roundtrip_sqlite(isgs_sqlite_conn):
    """Every mapped field in the isgs extracted JSON reaches the SQLite DB."""
    _check_roundtrip("isgs", isgs_sqlite_conn, "sqlite")
