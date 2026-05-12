# -*- coding: utf-8 -*-
"""
schema_excel_to_json.py  (sql_sync/sql_schemas)

Converts SQL database structure and field mapping spreadsheets into JSON files
consumed by the ETL pipeline.

Institution folders live alongside this script (e.g. isgs/, master/).  Each
folder contains two spreadsheets:
    {institution}-database-structure.xlsx  — table/column definitions
    ogrre-to-{institution}-database-mapping.xlsx — MongoDB → SQL field mapping

Usage (standalone):
    # process all institution folders, all db types
    python schema_excel_to_json.py

    # one institution only
    python schema_excel_to_json.py --institution isgs

    # one institution, postgres schema only
    python schema_excel_to_json.py --institution isgs --db-type postgres

Usage (as a library):
    from sql_sync.sql_schemas.schema_excel_to_json import (
        schema_to_json, mapping_to_json, SQLITE_TYPE_MAP, POSTGRES_TYPE_MAP
    )
    schema_to_json("isgs/isgs-database-structure.xlsx",
                   institution="isgs", type_map=POSTGRES_TYPE_MAP)
    mapping_to_json("isgs/ogrre-to-isgs-database-mapping.xlsx",
                    institution="isgs")
"""

import json
import math
import datetime
import os
import re
import sys
import argparse
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))
from constants import SQLITE_TYPE_MAP, POSTGRES_TYPE_MAP  # noqa: E402


# SQL reserved words that are plausible column names — warn if any appear in a sheet.
# Quoting handles them at load time, but renaming in the spreadsheet is cleaner.
_SQL_RESERVED = {
    "primary", "index", "order", "select", "where", "group", "table", "column",
    "check", "default", "key", "value", "values", "type", "status", "date",
    "name", "level", "end", "range", "match", "left", "right", "full",
}

# ── Column header mapping ─────────────────────────────────────────────────────
# Maps the spreadsheet column header names to the snake_case keys used in
# the output JSON.  Extend this if the spreadsheet gains new columns.

COLUMN_HEADERS = {
    "Column Name":        "column_name",
    "Column description": "description",
    "Data type":          "data_type",
    "Examples":           "examples",
    "Units":              "units",
    "Application":        "application",
    "Links":              "links",
}

# ── Built-in type maps ────────────────────────────────────────────────────────
# Imported from sql_sync/constants.py — edit there to keep load.py in sync.
# Pass one of these as `type_map` to remap spreadsheet type strings to your
# target database's type system.  If type_map=None, raw strings are kept.
# Keys are matched case-insensitively (.strip().lower()) at call sites.


# ── Helpers ───────────────────────────────────────────────────────────────────

def _normalize_column_name(name: str) -> str:
    """Convert a spreadsheet column name to a valid snake_case SQL identifier."""
    name = str(name).strip().lower()
    name = re.sub(r"[\s\-]+", "_", name)       # spaces/hyphens → underscores
    name = re.sub(r"[^a-z0-9_]", "", name)     # drop everything else
    name = re.sub(r"_+", "_", name).strip("_") # collapse duplicate underscores
    return name


def _clean_value(v):
    """Convert NaN -> None and non-serialisable types for clean JSON output."""
    if isinstance(v, float) and math.isnan(v):
        return None
    if isinstance(v, (datetime.datetime, datetime.date)):
        return v.isoformat()
    # pandas returns numpy scalar types; .item() converts them to Python natives
    if hasattr(v, "item"):
        v = v.item()
        if isinstance(v, float) and math.isnan(v):
            return None
    return v


def _default_out_dir():
    """sql_sync/data/ — sibling of this script's sql_schemas/ directory."""
    return os.path.normpath(
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data")
    )


def _find_xlsx(institution_dir, pattern):
    """Return the path of the first .xlsx file in institution_dir whose name contains pattern."""
    for fname in os.listdir(institution_dir):
        if fname.endswith(".xlsx") and pattern in fname:
            return os.path.join(institution_dir, fname)
    return None


def _institution_dirs(schemas_dir):
    """Yield (institution_name, dir_path) for each institution subfolder of schemas_dir."""
    for name in sorted(os.listdir(schemas_dir)):
        path = os.path.join(schemas_dir, name)
        if os.path.isdir(path) and not name.startswith((".", "__")):
            yield name, path


# ── schema_to_json ────────────────────────────────────────────────────────────

def schema_to_json(excel_file_path, institution, out_dir=None, type_map=None,
                   db_type=None):
    """
    Convert a database structure spreadsheet to JSON schema files.

    Each table sheet becomes its own JSON file in:
        {out_dir}/{db_type}_schema/{institution}/{table_name}.json

    A master index listing all tables and their column names is written to:
        {out_dir}/{db_type}_schema/{institution}/tables.json

    Args:
        excel_file_path (str): Path to the *-database-structure.xlsx file.
        institution (str):     Institution key (e.g. "isgs", "master") — used
                               as the output subdirectory name.
        out_dir (str):         Directory to write output into.
                               Defaults to sql_sync/data/.
        type_map (dict):       Optional mapping of spreadsheet type strings to
                               target-DB type strings.  Built-in options:
                                   SQLITE_TYPE_MAP   — for SQLite prototyping
                                   POSTGRES_TYPE_MAP — for PostgreSQL
                               Keys are matched case-insensitively.
                               If None, raw spreadsheet type strings are kept.
        db_type (str):         Label used in the output directory name
                               (e.g. "postgres" -> postgres_schema/isgs/).
                               If None, the directory is simply {institution}/.
    """

    if out_dir is None:
        out_dir = _default_out_dir()

    if db_type:
        schema_dir = os.path.join(out_dir, f"{db_type}_schema", institution)
    else:
        schema_dir = os.path.join(out_dir, institution)
    os.makedirs(schema_dir, exist_ok=True)

    excel_file = pd.ExcelFile(excel_file_path)
    table_sheets = excel_file.sheet_names
    print(f"schema_to_json [{institution}]: found {len(table_sheets)} table sheets: {table_sheets}")

    tables_index = {}

    for sheet in table_sheets:
        # Row 0 is a title row; row 1 is the column header row
        df = pd.read_excel(excel_file_path, sheet_name=sheet, header=1)

        col_lower = {c.lower(): c for c in df.columns}
        rename = {
            col_lower[k.lower()]: v
            for k, v in COLUMN_HEADERS.items()
            if k.lower() in col_lower
        }
        df = df.rename(columns=rename)

        if "column_name" in df.columns:
            df = df[df["column_name"].notna()]
            df["column_name"] = df["column_name"].apply(_normalize_column_name)

            seen, dupes = set(), set()
            for name in df["column_name"]:
                if name in seen:
                    dupes.add(name)
                seen.add(name)
            if dupes:
                print(f"  WARNING: duplicate column name(s) in sheet '{sheet}': {sorted(dupes)}")

            reserved = {n for n in seen if n in _SQL_RESERVED}
            if reserved:
                print(f"  WARNING: reserved SQL keyword(s) used as column name(s) in sheet '{sheet}': {sorted(reserved)} — consider renaming")

        if df.empty:
            print(f"  Skipping {sheet} (empty after filtering)")
            continue

        columns = []
        for row in df.to_dict(orient="records"):
            record = {k: _clean_value(v) for k, v in row.items()}
            if type_map and record.get("data_type") is not None:
                normalised = str(record["data_type"]).strip().lower()
                if normalised in type_map:
                    record["data_type"] = type_map[normalised]
            columns.append(record)

        out_path = os.path.join(schema_dir, f"{sheet}.json")
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(columns, f, indent=4)
        print(f"  Wrote {out_path}")

        tables_index[sheet] = [c.get("column_name") for c in columns]

    index_path = os.path.join(schema_dir, "tables.json")
    with open(index_path, "w", encoding="utf-8") as f:
        json.dump(tables_index, f, indent=4)
    print(f"  Wrote {index_path}")


# ── mapping_to_json ───────────────────────────────────────────────────────────

def mapping_to_json(excel_file_path, institution, out_dir=None):
    """
    Convert a field mapping spreadsheet to JSON.

    Each sheet becomes its own JSON file in:
        {out_dir}/field_mapping/{institution}/{sheet_name}.json

    Args:
        excel_file_path (str): Path to the ogrre-to-*-database-mapping.xlsx file.
        institution (str):     Institution key (e.g. "isgs", "master").
        out_dir (str):         Directory to write output into.
                               Defaults to sql_sync/data/.
    """
    if out_dir is None:
        out_dir = _default_out_dir()

    mapping_dir = os.path.join(out_dir, "field_mapping", institution)
    os.makedirs(mapping_dir, exist_ok=True)

    xl = pd.ExcelFile(excel_file_path)
    print(f"mapping_to_json [{institution}]: found {len(xl.sheet_names)} sheet(s): {xl.sheet_names}")

    for sheet in xl.sheet_names:
        df = pd.read_excel(excel_file_path, sheet_name=sheet, header=0)
        records = [{k: _clean_value(v) for k, v in row.items()}
                   for row in df.to_dict(orient="records")]
        out_path = os.path.join(mapping_dir, f"{sheet}.json")
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(records, f, indent=4)
        print(f"  Wrote {out_path}")


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    _DB_TYPES = {
        "postgres": POSTGRES_TYPE_MAP,
        "sqlite":   SQLITE_TYPE_MAP,
        "raw":      None,
    }

    _SCHEMAS_DIR = os.path.dirname(os.path.abspath(__file__))

    parser = argparse.ArgumentParser(
        description="Convert institution spreadsheets to JSON schema and mapping files."
    )
    parser.add_argument(
        "--institution",
        default=None,
        help="Institution to process (e.g. 'isgs'). Defaults to all institution folders.",
    )
    parser.add_argument(
        "--db-type",
        choices=list(_DB_TYPES.keys()) + ["all"],
        default="all",
        help="Target database type for schema generation (default: all).",
    )
    parser.add_argument(
        "--out-dir",
        default=None,
        help="Output directory (default: sql_sync/data/).",
    )
    args = parser.parse_args()

    if args.institution:
        institutions = [(args.institution, os.path.join(_SCHEMAS_DIR, args.institution))]
    else:
        institutions = list(_institution_dirs(_SCHEMAS_DIR))

    db_targets = _DB_TYPES.items() if args.db_type == "all" else [(args.db_type, _DB_TYPES[args.db_type])]

    for institution, inst_dir in institutions:
        print(f"\n{'='*50}")
        print(f"Processing institution: {institution}")
        print(f"{'='*50}")

        structure_xlsx = _find_xlsx(inst_dir, "database-structure")
        mapping_xlsx = _find_xlsx(inst_dir, "database-mapping")

        if structure_xlsx:
            for db_type, type_map in db_targets:
                print(f"\n--- Schema: {db_type} ---")
                schema_to_json(
                    excel_file_path=structure_xlsx,
                    institution=institution,
                    out_dir=args.out_dir,
                    type_map=type_map,
                    db_type=db_type,
                )
        else:
            print(f"  No *-database-structure.xlsx found in {inst_dir}, skipping schema.")

        if mapping_xlsx:
            print(f"\n--- Field mapping ---")
            mapping_to_json(
                excel_file_path=mapping_xlsx,
                institution=institution,
                out_dir=args.out_dir,
            )
        else:
            print(f"  No *-database-mapping.xlsx found in {inst_dir}, skipping mapping.")

    print(f"\nDone. Output written to: {args.out_dir or _default_out_dir()}")
