"""
Configuration for the pg_sync ETL pipeline.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env", override=False)


# ---------------------------------------------------------------------------
# MongoDB
# ---------------------------------------------------------------------------
MONGO_URI: str = os.environ["DB_CONNECTION"]
MONGO_DB_NAME: str = os.environ.get("MONGO_DB_NAME", "ogrre")

# ---------------------------------------------------------------------------
# PostgreSQL  (connection string or individual parts)
# Use PG_DSN if set, otherwise assemble from parts.
# ---------------------------------------------------------------------------
_pg_dsn = os.environ.get("PG_DSN")
if not _pg_dsn:
    _pg_dsn = (
        f"host={os.environ['PG_HOST']} "
        f"port={os.environ.get('PG_PORT', '5432')} "
        f"dbname={os.environ['PG_DBNAME']} "
        f"user={os.environ['PG_USER']} "
        f"password={os.environ['PG_PASSWORD']}"
    )
PG_DSN: str = _pg_dsn

# ---------------------------------------------------------------------------
# Runtime
# ---------------------------------------------------------------------------
COLLABORATOR: str = os.environ.get("COLLABORATOR", "isgs")

SCHEMA_DIR: Path = Path(__file__).parent / "schema"
MAPPING_DIR: Path = Path(__file__).parent / "field_mappings"

# Processors that feed each unified form-type table.
# Keys match the form_type argument used by run_sync.py.
PROCESSOR_FORM_MAP: dict[str, list[str]] = {
    "completion_reports": [
        "IL_Ver_A_WellCompletion",
        "IL_Ver_B_Well_Completion",
        "IL_WellCompletion_F",
        "IL_WellCompletion_G",
    ],
    "plugging_reports": [
        "IL_Ver_A_PluggingReport",
        "IL_Ver_B_PluggingReport",
        "IL_Ver_C_PluggingReport",
    ],
    "inspector_casing_cement_reports": [
        "IL_InspectorCasingCement_B",
    ],
    "drilling_reports": [
        "Illinois_Well_Drilling",
    ],
}
