# -*- coding: utf-8 -*-
"""
constants.py  (sql_sync)

Shared type maps used by both the schema converter (schema_excel_to_json.py)
and the loader (load.py).  Keys are matched case-insensitively at call sites.
"""

# ── Hardcoded table name conventions ─────────────────────────────────────────
# Every institution's schema must use these table names for the pipeline to
# work correctly.  REPORT_TABLE receives one row per OGRRE record.
# WELL_TABLE receives one row per unique API number (most-recent-wins).

REPORT_TABLE = "completion_reports"
WELL_TABLE   = "well_headers"

# ── Field mapping column headers ──────────────────────────────────────────────
# Required column names in the ogrre_to_{institution}.json field mapping file.
# The mapping Excel spreadsheet must use these exact headers (case-sensitive).
# transform.py reads these keys — if they differ, fields will silently go unmapped.

MAPPING_COLUMNS = {
    "processor":    "Google Processor",
    "ogrre_name":   "OGRRE_Name",
    "report_col":   "Completion Report Table Field",
    "master_table": "Master Table",
    "master_col":   "Master Field",
}

# ── Type maps ─────────────────────────────────────────────────────────────────
# Maps spreadsheet/schema type strings to SQLite affinity types.
# Covers both raw Excel strings (e.g. "big int") and already-converted
# schema JSON values (e.g. "INTEGER") so the same map works at every stage.
SQLITE_TYPE_MAP = {
    "big int":          "INTEGER",
    "bigint":           "INTEGER",
    "int":              "INTEGER",
    "integer":          "INTEGER",
    "smallint":         "INTEGER",
    "bool":             "INTEGER",
    "boolean":          "INTEGER",
    "text":             "TEXT",
    "string":           "TEXT",
    "varchar":          "TEXT",
    "char":             "TEXT",
    "float":            "REAL",
    "real":             "REAL",
    "double":           "REAL",
    "double precision": "REAL",
    "numeric":          "NUMERIC",
    "decimal":          "NUMERIC",
    "date":             "TEXT",
    "timestamp":        "TEXT",
    "timestamptz":      "TEXT",
    "json":             "TEXT",
    "jsonb":            "TEXT",
}

# Maps spreadsheet/schema type strings to PostgreSQL type names.
POSTGRES_TYPE_MAP = {
    "big int":          "bigint",
    "bigint":           "bigint",
    "int":              "integer",
    "integer":          "integer",
    "smallint":         "smallint",
    "bool":             "boolean",
    "boolean":          "boolean",
    "text":             "text",
    "string":           "text",
    "varchar":          "text",
    "char":             "text",
    "float":            "double precision",
    "real":             "double precision",
    "double":           "double precision",
    "double precision": "double precision",
    "numeric":          "numeric",
    "decimal":          "numeric",
    "date":             "date",
    "timestamp":        "timestamp",
    "timestamptz":      "timestamptz",
    "json":             "jsonb",
    "jsonb":            "jsonb",
}
