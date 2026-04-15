"""
pg_writer.py — Upserts completion report rows into PostgreSQL.

Design decisions:
  - Uses ON CONFLICT (report_name) DO UPDATE to make syncs idempotent.
  - Child table rows are always DELETE + INSERT (simpler than row-level diffing).
  - All operations for a single record are wrapped in a transaction.
  - Columns in the row dict that don't exist in the table are silently dropped
    (allows schema.sql to lag behind new fields being added to the mapping).
"""
import logging
from typing import Any

import psycopg2
import psycopg2.extras

log = logging.getLogger(__name__)

# Maps each child table name to the column that references completion_reports.id
CHILD_FK_COLUMN = "completion_report_id"

# Child tables that belong to isgs.completion_reports
CHILD_TABLES: list[str] = [
    "completion_report_logs",
    "completion_report_completion_intervals",
    "completion_report_gun_perforating_windows",
    "completion_report_acid_records",
    "completion_report_casing_records",
    "completion_report_packers",
]


def get_table_columns(cur, schema: str, table: str) -> set[str]:
    """Return the set of column names that exist in a given table."""
    cur.execute(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = %s AND table_name = %s
        """,
        (schema, table),
    )
    return {row[0] for row in cur.fetchall()}


def _filter_row(row: dict, allowed_columns: set[str]) -> dict:
    """Drop keys from row that are not present in the table schema."""
    return {k: v for k, v in row.items() if k in allowed_columns}


def upsert_metadata(cur, metadata_row: dict, schema: str = "isgs") -> None:
    """
    Insert or update a row in ogrre_record_metadata.
    """
    allowed = get_table_columns(cur, schema, "ogrre_record_metadata")
    row = _filter_row(metadata_row, allowed)
    if not row:
        return

    cols   = list(row.keys())
    values = [row[c] for c in cols]
    placeholders = ", ".join(["%s"] * len(cols))
    col_names    = ", ".join(cols)
    updates      = ", ".join(f"{c} = EXCLUDED.{c}" for c in cols if c != "report_name")

    sql = f"""
        INSERT INTO {schema}.ogrre_record_metadata ({col_names})
        VALUES ({placeholders})
        ON CONFLICT (report_name) DO UPDATE SET {updates}
    """
    cur.execute(sql, values)


def upsert_completion_report(
    cur,
    row: dict,
    schema: str = "isgs",
) -> int:
    """
    Upsert a row into isgs.completion_reports.
    Returns the id of the upserted row.
    """
    allowed = get_table_columns(cur, schema, "completion_reports")
    row = _filter_row(row, allowed)

    # Ensure report_name is present (conflict target)
    if "report_name" not in row:
        raise ValueError("row is missing required field 'report_name'")

    cols         = list(row.keys())
    values       = [row[c] for c in cols]
    placeholders = ", ".join(["%s"] * len(cols))
    col_names    = ", ".join(cols)
    updates      = ", ".join(
        f"{c} = EXCLUDED.{c}"
        for c in cols
        if c not in ("id", "report_name")
    )

    sql = f"""
        INSERT INTO {schema}.completion_reports ({col_names})
        VALUES ({placeholders})
        ON CONFLICT (report_name) DO UPDATE SET {updates}
        RETURNING id
    """
    cur.execute(sql, values)
    return cur.fetchone()[0]


def replace_child_rows(
    cur,
    completion_report_id: int,
    child_table: str,
    child_rows: list[dict],
    schema: str = "isgs",
) -> None:
    """
    Delete all existing child rows for this completion_report_id,
    then insert the new ones.
    """
    full_table = f"{schema}.{child_table}"

    cur.execute(
        f"DELETE FROM {full_table} WHERE {CHILD_FK_COLUMN} = %s",
        (completion_report_id,),
    )

    if not child_rows:
        return

    allowed = get_table_columns(cur, schema, child_table)

    for idx, child_row in enumerate(child_rows):
        child_row[CHILD_FK_COLUMN] = completion_report_id
        child_row.setdefault("occurrence_idx", idx)
        row = _filter_row(child_row, allowed)

        cols         = list(row.keys())
        values       = [row[c] for c in cols]
        placeholders = ", ".join(["%s"] * len(cols))
        col_names    = ", ".join(cols)

        cur.execute(
            f"INSERT INTO {full_table} ({col_names}) VALUES ({placeholders})",
            values,
        )


def write_record(
    conn,
    metadata_row: dict,
    main_row: dict,
    child_rows: dict[str, list[dict]],
    schema: str = "isgs",
) -> bool:
    """
    Write a single record to PostgreSQL inside a transaction.
    Returns True on success, False on error.
    """
    report_name = main_row.get("report_name", "<unknown>")
    try:
        with conn:  # transaction
            with conn.cursor() as cur:
                upsert_metadata(cur, metadata_row, schema)
                cr_id = upsert_completion_report(cur, main_row, schema)
                for child_table, rows in child_rows.items():
                    replace_child_rows(cur, cr_id, child_table, rows, schema)
        return True
    except Exception as exc:
        log.error("Failed to write record '%s': %s", report_name, exc)
        conn.rollback()
        return False


def apply_schema(conn, sql_path: str) -> None:
    """Execute a SQL schema file against the database."""
    with open(sql_path) as f:
        sql = f.read()
    with conn:
        with conn.cursor() as cur:
            cur.execute(sql)
    log.info("Applied schema: %s", sql_path)


def log_sync_start(conn, collaborator: str, form_type: str, schema: str = "isgs") -> int:
    """Insert a sync_log row with status='running', return its id."""
    with conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                INSERT INTO {schema}.sync_log
                    (started_at, collaborator, form_type, status)
                VALUES (now(), %s, %s, 'running')
                RETURNING id
                """,
                (collaborator, form_type),
            )
            return cur.fetchone()[0]


def log_sync_end(
    conn,
    log_id: int,
    synced: int,
    failed: int,
    error_message: str | None = None,
    schema: str = "isgs",
) -> None:
    """Update the sync_log row with final counts and status."""
    status = "success" if failed == 0 else "failed"
    with conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                UPDATE {schema}.sync_log
                SET finished_at    = now(),
                    records_synced = %s,
                    records_failed = %s,
                    error_message  = %s,
                    status         = %s
                WHERE id = %s
                """,
                (synced, failed, error_message, status, log_id),
            )


def get_last_sync_timestamp(
    conn, collaborator: str, form_type: str, schema: str = "isgs"
) -> float | None:
    """Return the finished_at timestamp of the last successful sync, or None."""
    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT EXTRACT(EPOCH FROM finished_at)
            FROM {schema}.sync_log
            WHERE collaborator = %s
              AND form_type = %s
              AND status = 'success'
            ORDER BY finished_at DESC
            LIMIT 1
            """,
            (collaborator, form_type),
        )
        row = cur.fetchone()
        return float(row[0]) if row else None
