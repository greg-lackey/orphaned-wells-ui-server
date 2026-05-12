# -*- coding: utf-8 -*-
"""
run.py  (sql_sync)

Runs the full ETL pipeline in one command:
    Step 1 — extract:   MongoDB → dict
    Step 2 — transform: dict    → table rows (using institution field mapping)
    Step 3 — load:      rows    → SQLite or PostgreSQL

Intermediate JSON files are kept in memory by default.  Pass
--save-intermediates to write them to sql_sync/data/extracted/ and
sql_sync/data/transformed/ for inspection or incremental reruns.

Usage:
    # SQLite (dev) — DB name defaults to institution key
    python sql_sync/run.py --institution isgs \\
                            --db-type sqlite \\
                            --db-path sql_sync/data/ogrre_isgs.db

    # Override DB name when it differs from the institution key
    python sql_sync/run.py --institution isgs --db-name isgs_production \\
                            --db-type postgres

    # Save intermediate files for inspection
    python sql_sync/run.py --institution isgs --db-type sqlite \\
                            --db-path sql_sync/data/ogrre_isgs.db \\
                            --save-intermediates

    # Full reload (clear tables before inserting)
    python sql_sync/run.py --institution isgs --db-type sqlite \\
                            --db-path sql_sync/data/ogrre_isgs.db \\
                            --truncate
"""

import argparse
import json
from pathlib import Path

from extract import connect, extract
from transform import load_mapping, transform
from load import connect_postgres, connect_sqlite, create_tables_sqlite, load, load_schema

_DATA_DIR = Path(__file__).parent / "data"


def run_pipeline(
    extracted: dict,
    institution: str,
    db_type: str,
    db_path: str = None,
    truncate: bool = False,
) -> dict:
    """
    Run transform → load on already-extracted data.

    Separated from run() so it can be called in tests without a live MongoDB.
    """
    print(f"\n--- Step 2: Transform ({institution}) ---")
    mapping = load_mapping(institution)
    transformed = transform(extracted, mapping)
    for table, rows in sorted(transformed.items()):
        print(f"  {table}: {len(rows)} row(s)")

    print(f"\n--- Step 3: Load ({db_type}) ---")
    schema = load_schema(institution, db_type)

    if db_type == "sqlite":
        conn = connect_sqlite(db_path)
        create_tables_sqlite(conn, schema)
    else:
        conn = connect_postgres()

    try:
        load(transformed, schema, conn, db_type, truncate=truncate)
    finally:
        conn.close()

    return transformed


def run(
    institution: str,
    db_type: str,
    db_path: str = None,
    truncate: bool = False,
    save_intermediates: bool = False,
    db_name: str = None,
) -> None:
    """Run the full extract → transform → load pipeline."""
    print("--- Step 1: Extract ---")
    db = connect(db_name=db_name or institution)
    extracted = extract(db)

    if not extracted:
        print("No records extracted — pipeline complete.")
        return

    if save_intermediates:
        out = _DATA_DIR / "extracted" / f"{institution}.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        with open(out, "w") as f:
            json.dump(extracted, f, indent=2, default=str)
        print(f"  Saved extracted data to {out}")

    transformed = run_pipeline(extracted, institution, db_type, db_path, truncate)

    if save_intermediates:
        out = _DATA_DIR / "transformed" / f"{institution}.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        with open(out, "w") as f:
            json.dump(transformed, f, indent=2, default=str)
        print(f"  Saved transformed data to {out}")

    print("\nPipeline complete.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Run the full OGRRE ETL pipeline (extract → transform → load)."
    )
    parser.add_argument(
        "--institution", required=True,
        help="Institution key (e.g. 'isgs'). Selects field mapping and schema.",
    )
    parser.add_argument(
        "--db-name", default=None,
        help=(
            "MongoDB database name. Defaults to the --institution value. "
            "Use this when the database name differs from the institution key."
        ),
    )
    parser.add_argument(
        "--db-type", required=True, choices=["sqlite", "postgres"],
        help="Target database type.",
    )
    parser.add_argument(
        "--db-path",
        help="Path to the SQLite .db file (required when --db-type is sqlite).",
    )
    parser.add_argument(
        "--truncate", action="store_true",
        help="Delete all rows in each target table before inserting.",
    )
    parser.add_argument(
        "--save-intermediates", action="store_true",
        help="Write extracted and transformed JSON to sql_sync/data/ for inspection.",
    )
    args = parser.parse_args()

    if args.db_type == "sqlite" and not args.db_path:
        parser.error("--db-path is required when --db-type is sqlite")

    run(
        institution=args.institution,
        db_type=args.db_type,
        db_path=args.db_path,
        truncate=args.truncate,
        save_intermediates=args.save_intermediates,
        db_name=args.db_name,
    )
