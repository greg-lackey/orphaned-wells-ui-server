# -*- coding: utf-8 -*-
"""
load.py  (sql_sync)

Loads transformed SQL rows into either SQLite (dev) or PostgreSQL (prod).

Tables are created automatically for SQLite using the schema JSON files.
For PostgreSQL, tables must already exist in the target database.

Note: idempotent loads require a UNIQUE constraint in the target schema
(e.g. on mongo_id for completion_reports, api_uwi for well_headers).
Without one, INSERT OR IGNORE / ON CONFLICT DO NOTHING becomes a no-op
and rerunning the loader will insert duplicate rows.  Use --truncate for
a clean reload until unique constraints are in place.

Usage:
    # SQLite
    python sql_sync/load.py --db-type sqlite \\
                             --db-path sql_sync/data/ogrre_isgs.db \\
                             --in sql_sync/data/transformed/isgs.json \\
                             --institution isgs

    # PostgreSQL
    python sql_sync/load.py --db-type postgres \\
                             --in sql_sync/data/transformed/isgs.json \\
                             --institution isgs
"""

import argparse
import json
import os
import sqlite3
from pathlib import Path

from dotenv import load_dotenv

from constants import SQLITE_TYPE_MAP

_ROOT_ENV = Path(__file__).parent.parent / ".env"
_DATA_DIR = Path(__file__).parent / "data"


# ── Schema ────────────────────────────────────────────────────────────────────

def load_schema(institution: str, db_type: str) -> dict:
    """
    Load column definitions for all tables from the schema JSON files.
    Returns {table_name: [{"column_name": ..., "data_type": ...}, ...]}
    """
    schema_dir = _DATA_DIR / f"{db_type}_schema" / institution
    if not schema_dir.exists():
        raise FileNotFoundError(f"Schema directory not found: {schema_dir}")
    schema = {}
    for path in sorted(schema_dir.glob("*.json")):
        if path.stem == "tables":
            continue
        with open(path) as f:
            schema[path.stem] = json.load(f)
    return schema


def _insertable_columns(table_schema: list) -> list:
    """Return column names suitable for INSERT, excluding the auto-generated id PK."""
    return [c["column_name"] for c in table_schema if c["column_name"] != "id"]


# ── SQLite ────────────────────────────────────────────────────────────────────

def _sqlite_type(data_type: str) -> str:
    return SQLITE_TYPE_MAP.get((data_type or "").strip().lower(), "TEXT")


def connect_sqlite(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def create_tables_sqlite(conn: sqlite3.Connection, schema: dict) -> None:
    """Create tables in SQLite from schema definitions if they don't exist."""
    for table, columns in schema.items():
        col_defs = ["id INTEGER PRIMARY KEY AUTOINCREMENT"]
        for col in columns:
            if col["column_name"] == "id":
                continue
            col_defs.append(f'"{col["column_name"]}" {_sqlite_type(col["data_type"])}')
        ddl = (
            f"CREATE TABLE IF NOT EXISTS {table} (\n  "
            + ",\n  ".join(col_defs)
            + "\n)"
        )
        conn.execute(ddl)
    conn.commit()


# ── PostgreSQL ────────────────────────────────────────────────────────────────

def connect_postgres():
    """Connect to PostgreSQL using PG_DSN from the project root .env."""
    load_dotenv(_ROOT_ENV, override=True)
    pg_dsn = os.getenv("PG_DSN")
    if not pg_dsn:
        raise ValueError("PG_DSN is not set. Add it to the project root .env.")
    try:
        import psycopg2
    except ImportError:
        raise ImportError(
            "psycopg2 is required for PostgreSQL. "
            "Install it with: pip install psycopg2-binary"
        )
    return psycopg2.connect(pg_dsn)


# ── Insert ────────────────────────────────────────────────────────────────────

def _placeholders(db_type: str, n: int) -> str:
    """Return a parameterized VALUES placeholder string for n columns."""
    marker = "?" if db_type == "sqlite" else "%s"
    return ", ".join([marker] * n)


def insert_table(conn, db_type: str, table: str, rows: list, col_names: list) -> tuple:
    """
    Insert rows into table using only the columns in col_names.
    Returns (inserted, skipped) counts.
    """
    if not rows or not col_names:
        return 0, 0

    cols_sql = ", ".join(f'"{c}"' for c in col_names)
    ph = _placeholders(db_type, len(col_names))

    if db_type == "sqlite":
        sql = f"INSERT OR IGNORE INTO {table} ({cols_sql}) VALUES ({ph})"
    else:
        sql = f"INSERT INTO {table} ({cols_sql}) VALUES ({ph}) ON CONFLICT DO NOTHING"

    values = [tuple(row.get(col) for col in col_names) for row in rows]
    cur = conn.cursor()
    cur.executemany(sql, values)

    inserted = cur.rowcount if cur.rowcount >= 0 else len(rows)
    skipped = len(rows) - inserted
    return inserted, skipped


# ── Main load function ────────────────────────────────────────────────────────

def load(transformed: dict, schema: dict, conn, db_type: str, truncate: bool = False) -> None:
    """
    Insert transformed rows into the database.

    Args:
        transformed: output of transform() — {table_name: [row_dicts]}
        schema:      output of load_schema() — {table_name: [col_defs]}
        conn:        open database connection
        db_type:     "sqlite" or "postgres"
        truncate:    if True, delete all rows in each target table before inserting
    """
    cur = conn.cursor()

    for table, rows in transformed.items():
        if table not in schema:
            print(f"  {table}: skipped (no schema found)")
            continue

        col_names = _insertable_columns(schema[table])

        # api_uwi in well_headers comes from the filename parse (_api), not the
        # field mapping — use it as a fallback when the mapping didn't supply it.
        if table == "well_headers" and "api_uwi" in col_names:
            for row in rows:
                if "api_uwi" not in row and row.get("_api"):
                    row["api_uwi"] = row["_api"]

        if truncate:
            cur.execute(f"DELETE FROM {table}")
            print(f"  {table}: truncated")

        inserted, skipped = insert_table(conn, db_type, table, rows, col_names)
        print(f"  {table}: {inserted} inserted, {skipped} skipped")

    conn.commit()


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Load transformed OGRRE records into a SQL database."
    )
    parser.add_argument(
        "--db-type", required=True, choices=["sqlite", "postgres"],
        help="Target database type.",
    )
    parser.add_argument(
        "--in", dest="input", required=True,
        help="Path to transformed JSON (output of transform.py).",
    )
    parser.add_argument(
        "--institution", required=True,
        help="Institution key (e.g. 'isgs').",
    )
    parser.add_argument(
        "--db-path",
        help="Path to the SQLite .db file (required when --db-type is sqlite).",
    )
    parser.add_argument(
        "--truncate", action="store_true",
        help="Delete all rows in each target table before inserting.",
    )
    args = parser.parse_args()

    if args.db_type == "sqlite" and not args.db_path:
        parser.error("--db-path is required when --db-type is sqlite")

    with open(args.input) as f:
        transformed = json.load(f)

    schema = load_schema(args.institution, args.db_type)

    if args.db_type == "sqlite":
        conn = connect_sqlite(args.db_path)
        create_tables_sqlite(conn, schema)
    else:
        conn = connect_postgres()

    try:
        load(transformed, schema, conn, args.db_type, truncate=args.truncate)
    finally:
        conn.close()
