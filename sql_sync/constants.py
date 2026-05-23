# -*- coding: utf-8 -*-
"""
constants.py  (sql_sync)

Shared type maps used by both the schema converter (schema_excel_to_json.py)
and the loader (load.py).  Keys are matched case-insensitively at call sites.
"""

# ── Hardcoded table name conventions ─────────────────────────────────────────
# WELL_TABLE receives one row per unique API number (most-recent-wins),
# aggregated across all report types.  The pipeline treats this table specially.
# Report-layer table names (completion_reports, plugging_reports, etc.) are not
# hardcoded here — they are determined by the names of the mapping files.

WELL_TABLE = "well_headers"

# Tables whose primary key is a natural key supplied by the pipeline rather
# than an auto-generated SERIAL/AUTOINCREMENT integer.  The DDL generator and
# loader use this set to decide whether to emit SERIAL or use the column's own
# data type, and whether to include id in INSERT statements.
NATURAL_KEY_TABLES = {"well_headers"}

# ── Field mapping column headers ──────────────────────────────────────────────
# Required column names in each field mapping sheet.
# The mapping Excel spreadsheet must use these exact headers (case-sensitive).
# transform.py reads these keys — if they differ, fields will silently go unmapped.

MAPPING_COLUMNS = {
    "processor":    "google_processor",
    "ogrre_name":   "ogrre_field",
    "report_table": "report_table",
    "report_col":   "report_table_field",
    "master_table": "well_table",
    "master_col":   "well_table_field",
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
