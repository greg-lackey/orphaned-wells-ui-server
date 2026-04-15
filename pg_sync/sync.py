"""
sync.py — Orchestrates the MongoDB → PostgreSQL ETL for a single form type.
"""
import logging
from pathlib import Path
from typing import Optional

import psycopg2
import yaml

from . import config
from .mongo_reader import get_mongo_db, iter_reviewed_records
from .pg_writer import (
    apply_schema,
    get_last_sync_timestamp,
    log_sync_end,
    log_sync_start,
    write_record,
)
from .transformer import transform_record

log = logging.getLogger(__name__)


def load_mapping(collaborator: str, form_type: str) -> dict:
    """Load and parse the YAML field-mapping file for a given collaborator / form type."""
    mapping_path = config.MAPPING_DIR / collaborator / f"{form_type}.yaml"
    if not mapping_path.exists():
        raise FileNotFoundError(f"No field mapping file found at {mapping_path}")
    with open(mapping_path) as f:
        return yaml.safe_load(f)


def run_sync(
    form_type: str,
    collaborator: Optional[str] = None,
    full_sync: bool = False,
) -> tuple[int, int]:
    """
    Run the ETL pipeline for the given form_type.

    Args:
        form_type:    e.g. 'completion_reports'
        collaborator: e.g. 'isgs' (defaults to config.COLLABORATOR)
        full_sync:    If True, ignore the last sync timestamp and sync all records.

    Returns:
        (records_synced, records_failed)
    """
    collaborator = collaborator or config.COLLABORATOR
    processor_names: list[str] = config.PROCESSOR_FORM_MAP.get(form_type, [])

    if not processor_names:
        raise ValueError(
            f"No processors configured for form_type='{form_type}'. "
            f"Check PROCESSOR_FORM_MAP in config.py."
        )

    log.info(
        "Starting sync: collaborator=%s form_type=%s processors=%s",
        collaborator, form_type, processor_names,
    )

    # ------------------------------------------------------------------
    # Connect to PostgreSQL
    # ------------------------------------------------------------------
    pg_conn = psycopg2.connect(config.PG_DSN)
    pg_conn.autocommit = False

    # ------------------------------------------------------------------
    # Apply schema (idempotent CREATE TABLE IF NOT EXISTS)
    # ------------------------------------------------------------------
    schema_path = config.SCHEMA_DIR / collaborator / f"{form_type}.sql"
    if schema_path.exists():
        apply_schema(pg_conn, str(schema_path))
    else:
        log.warning("No schema file found at %s — skipping DDL apply.", schema_path)

    # ------------------------------------------------------------------
    # Load field mapping
    # ------------------------------------------------------------------
    mapping = load_mapping(collaborator, form_type)
    pg_schema = mapping.get("target_schema", collaborator)

    # ------------------------------------------------------------------
    # Determine sync window
    # ------------------------------------------------------------------
    since: Optional[float] = None
    if not full_sync:
        since = get_last_sync_timestamp(pg_conn, collaborator, form_type, pg_schema)
        if since:
            log.info("Incremental sync: only records updated after UNIX timestamp %.0f", since)
        else:
            log.info("No previous successful sync found — performing full sync.")

    # ------------------------------------------------------------------
    # Connect to MongoDB
    # ------------------------------------------------------------------
    mongo_db = get_mongo_db(config.MONGO_URI, config.MONGO_DB_NAME)

    # ------------------------------------------------------------------
    # Sync loop
    # ------------------------------------------------------------------
    sync_log_id = log_sync_start(pg_conn, collaborator, form_type, pg_schema)
    synced = 0
    failed = 0

    try:
        for mongo_doc, processor_name in iter_reviewed_records(
            mongo_db, processor_names, since_timestamp=since
        ):
            report_name = mongo_doc.get("name", mongo_doc.get("_id"))

            try:
                main_row, child_rows = transform_record(mongo_doc, processor_name, mapping)
            except Exception as exc:
                log.error("Transform error for record '%s': %s", report_name, exc)
                failed += 1
                continue

            # Build metadata row (audit trail, not well data)
            metadata_row = {
                "report_name":      mongo_doc.get("name"),
                "mongo_id":         mongo_doc.get("_id"),
                "source_processor": processor_name,
                "review_status":    mongo_doc.get("review_status"),
                "reviewer":         mongo_doc.get("last_updated_by"),
                "reviewed_at":      (
                    _unix_to_pg_ts(mongo_doc.get("lastUpdated"))
                    if mongo_doc.get("lastUpdated") else None
                ),
            }

            success = write_record(pg_conn, metadata_row, main_row, child_rows, pg_schema)
            if success:
                synced += 1
                if synced % 100 == 0:
                    log.info("Progress: %d synced, %d failed", synced, failed)
            else:
                failed += 1

    except Exception as exc:
        log.exception("Fatal error during sync: %s", exc)
        log_sync_end(pg_conn, sync_log_id, synced, failed, str(exc), pg_schema)
        pg_conn.close()
        raise

    log_sync_end(pg_conn, sync_log_id, synced, failed, schema=pg_schema)
    pg_conn.close()

    log.info(
        "Sync complete: collaborator=%s form_type=%s synced=%d failed=%d",
        collaborator, form_type, synced, failed,
    )
    return synced, failed


def _unix_to_pg_ts(ts: Optional[float]) -> Optional[str]:
    """Convert a UNIX float timestamp to an ISO-8601 string PostgreSQL can parse."""
    if ts is None:
        return None
    from datetime import datetime, timezone
    return datetime.fromtimestamp(float(ts), tz=timezone.utc).isoformat()
