# -*- coding: utf-8 -*-
"""
transform.py  (sql_sync)

Maps extracted OGRRE records to SQL table rows using the institution's field
mapping.  Each OGRRE record produces:
  - one row in completion_reports  (report layer — one row per OGRRE record)
  - one row per master table that has mapped fields (sidetracks, casings, etc.)
  - well_headers uses most-recent-wins: one row per unique API, taken from
    the record with the highest _date_created value

Output shape:
    {
        "completion_reports": [{...}, ...],
        "well_headers":       [{...}, ...],
        "sidetracks":         [{...}, ...],
        "casings":            [{...}, ...],
        ...
    }

Usage:
    python sql_sync/transform.py --in  sql_sync/data/extracted/isgs.json \\
                                 --institution isgs \\
                                 --out sql_sync/data/transformed/isgs.json
"""

import argparse
import json
from collections import defaultdict
from pathlib import Path

from constants import MAPPING_COLUMNS, REPORT_TABLE, WELL_TABLE

_DATA_DIR = Path(__file__).parent / "data"


# ── Helpers ───────────────────────────────────────────────────────────────────

def load_mapping(institution: str) -> list[dict]:
    expected = _DATA_DIR / "field_mapping" / institution / f"ogrre_to_{institution}.json"
    mapping_dir = _DATA_DIR / "field_mapping" / institution
    if not expected.exists():
        if not mapping_dir.exists():
            raise FileNotFoundError(
                f"Field mapping directory not found: {mapping_dir}\n"
                f"Create it and add a file named: ogrre_to_{institution}.json"
            )
        found = [f.name for f in mapping_dir.glob("*.json")]
        hint = f" Found: {found}" if found else " No .json files found in that directory."
        raise FileNotFoundError(
            f"Expected mapping file not found: {expected}\n"
            f"The file must be named 'ogrre_to_{{institution}}.json'.{hint}"
        )
    with open(expected) as f:
        return json.load(f)


def _validate_mapping_headers(mapping: list[dict]) -> None:
    """Warn if any required column headers are absent from the mapping."""
    if not mapping:
        return
    present = set(mapping[0].keys())
    missing = [col for col in MAPPING_COLUMNS.values() if col not in present]
    if missing:
        print(
            f"WARNING: field mapping is missing expected column(s): {missing}\n"
            f"  Required columns: {list(MAPPING_COLUMNS.values())}\n"
            f"  Found columns:    {sorted(present)}"
        )


def _build_lookup(mapping: list[dict]) -> dict:
    """Build {processor_name: {ogrre_name: {report_col, master_table, master_col}}}."""
    _validate_mapping_headers(mapping)
    lookup = defaultdict(dict)
    for entry in mapping:
        proc      = (entry.get(MAPPING_COLUMNS["processor"])  or "").strip()
        ogrre_name = (entry.get(MAPPING_COLUMNS["ogrre_name"]) or "").strip()
        if not proc or not ogrre_name:
            continue
        lookup[proc][ogrre_name] = {
            "report_col":   entry.get(MAPPING_COLUMNS["report_col"]),
            "master_table": entry.get(MAPPING_COLUMNS["master_table"]),
            "master_col":   entry.get(MAPPING_COLUMNS["master_col"]),
        }
    return dict(lookup)


# ── Main transform function ───────────────────────────────────────────────────

def transform(extracted: dict, mapping: list[dict]) -> dict:
    """
    Map extracted records to SQL table rows.

    Args:
        extracted: output of extract() — {processor_name: [flat_record_dicts]}
        mapping:   loaded field mapping (list of dicts from ogrre_to_*.json)

    Returns:
        dict mapping table_name -> list of row dicts
    """
    lookup = _build_lookup(mapping)

    by_table: dict[str, list] = defaultdict(list)
    # api -> (date_created, row) — for most-recent-wins on well_headers
    well_records: dict[str, tuple] = {}

    unmapped = {proc for proc in extracted if proc not in lookup}
    if unmapped:
        print(
            f"WARNING: {len(unmapped)} processor(s) in extracted data have no mapping entries "
            f"and will be skipped: {sorted(unmapped)}"
        )

    for proc_name, records in extracted.items():
        proc_map = lookup.get(proc_name, {})

        for record in records:
            api = record.get("_api")
            date_created = record.get("_date_created") or 0

            meta = {
                "_mongo_id": record["_mongo_id"],
                "_api": api,
            }
            report_row = {
                **meta,
                "_filename":      record.get("_filename"),
                "_date_created":  record.get("_date_created"),
                "_review_status": record.get("_review_status"),
            }
            master_rows: dict[str, dict] = {}

            for ogrre_name, col_info in proc_map.items():
                value = record.get(ogrre_name)

                report_col = col_info["report_col"]
                if report_col:
                    report_row[report_col] = value

                master_table = col_info["master_table"]
                master_col = col_info["master_col"]
                if master_table and master_col:
                    if master_table not in master_rows:
                        master_rows[master_table] = dict(meta)
                    master_rows[master_table][master_col] = value

            by_table[REPORT_TABLE].append(report_row)

            for table, row in master_rows.items():
                if table == WELL_TABLE:
                    existing = well_records.get(api)
                    if existing is None or date_created > existing[0]:
                        well_records[api] = (date_created, row)
                else:
                    by_table[table].append(row)

    if well_records:
        by_table[WELL_TABLE] = [row for _, row in well_records.values()]

    return dict(by_table)


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Transform extracted OGRRE records to SQL table rows."
    )
    parser.add_argument(
        "--in", dest="input", required=True,
        help="Path to extracted JSON (output of extract.py).",
    )
    parser.add_argument(
        "--institution", required=True,
        help="Institution key (e.g. 'isgs').",
    )
    parser.add_argument(
        "--out", default=None,
        help="Write transformed JSON to this file instead of stdout.",
    )
    args = parser.parse_args()

    with open(args.input) as f:
        extracted = json.load(f)

    mapping = load_mapping(args.institution)
    result = transform(extracted, mapping)

    for table, rows in sorted(result.items()):
        print(f"  {table}: {len(rows)} row(s)")

    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w") as f:
            json.dump(result, f, indent=2, default=str)
        print(f"Wrote output to {args.out}")
    else:
        print(json.dumps(result, indent=2, default=str))
