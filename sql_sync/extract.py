# -*- coding: utf-8 -*-
"""
extract.py  (sql_sync)

Queries validated records from MongoDB and returns them grouped by processor
name.  Each record's attributesList is flattened to a plain dict, and the
API number is parsed from the filename and stored without dashes.

Output shape:
    {
        "WellCompletion": [
            {
                "_mongo_id": "...",
                "_api": "5123123450",
                "_filename": "51-231-23450_WellCompletion.pdf",
                "_date_created": 1234567890,
                "_review_status": "reviewed",
                "_processor_name": "WellCompletion",
                "well_name": "Example Well",
                ...
            },
            ...
        ],
        "PlugAndAbandonment": [...],
    }

Usage:
    python sql_sync/extract.py --db-name isgs --out sql_sync/data/extracted/isgs.json
    python sql_sync/extract.py --db-name isgs --dry-run
    python sql_sync/extract.py --dry-run          # falls back to DB_NAME in .env
"""

import argparse
import json
import os
import re
import urllib.parse
from collections import defaultdict
from pathlib import Path

import certifi
from bson import ObjectId
from dotenv import load_dotenv
from pymongo import MongoClient
from pymongo.server_api import ServerApi

# ── Constants ─────────────────────────────────────────────────────────────────

_ROOT_ENV   = Path(__file__).parent.parent / ".env"
_CONFIG_DIR = Path(__file__).parent / "config"

# Matches XX-XXX-XXXXX or XXXXXXXXXX (10-digit US API number)
_API_RE = re.compile(r"(\d{2})-?(\d{3})-?(\d{5})")

VALIDATED_QUERY = {
    "review_status": {"$in": ["reviewed", "verified"]},
    "status": {"$in": ["digitized", "reprocessed"]},
}


# ── Connection ────────────────────────────────────────────────────────────────

def connect(db_name: str):
    """Connect to MongoDB using credentials from the project root .env.

    Args:
        db_name: MongoDB database name (required). Pass --db-name on the CLI,
                 or use run.py which defaults this to the --institution value.
    """
    if not db_name:
        raise ValueError(
            "db_name is required. Pass --db-name when running extract.py, "
            "or use run.py which defaults it to the --institution value."
        )
    load_dotenv(_ROOT_ENV, override=True)

    db_connection = os.getenv("DB_CONNECTION")
    db_username   = os.getenv("DB_USERNAME")
    db_password   = os.getenv("DB_PASSWORD")

    if not db_connection:
        raise ValueError(
            "DB_CONNECTION is not set. Add it to the project root .env."
        )

    app_name = os.getenv("MONGO_APP_NAME", "OGRRE")

    if db_connection.startswith("mongodb://") or db_connection.startswith("mongodb+srv://"):
        uri = db_connection
        client = MongoClient(uri, server_api=ServerApi("1"))
    else:
        username = urllib.parse.quote_plus(db_username)
        password = urllib.parse.quote_plus(db_password)
        cluster  = urllib.parse.quote_plus(db_connection)
        uri = f"mongodb+srv://{username}:{password}@{cluster}.mongodb.net/?appName={app_name}"
        client = MongoClient(uri, server_api=ServerApi("1"), tlsCAFile=certifi.where())

    try:
        client.admin.command("ping")
        print("Successfully connected to MongoDB!")
    except Exception as e:
        print(f"Unable to connect to MongoDB: {e}")
        raise

    return client[db_name]


# ── Helpers ───────────────────────────────────────────────────────────────────

def _extract_api(filename: str) -> str | None:
    """Parse API number from filename and return it without dashes."""
    match = _API_RE.search(filename or "")
    if match:
        return match.group(1) + match.group(2) + match.group(3)
    return None


def _flatten_attributes(attributes_list: list) -> dict:
    """Convert [{key, normalized_value, value, ...}, ...] to {key: best_value}.

    normalized_value holds the human-reviewed answer; value holds the raw AI
    extraction. Prefer normalized_value, fall back to value when not yet reviewed.
    """
    result = {}
    for attr in attributes_list:
        if "key" not in attr:
            continue
        val = attr.get("normalized_value")
        if val is None:
            val = attr.get("value")
        result[attr["key"]] = val
    return result


def _build_processor_lookup(db, processor_ids: set) -> dict:
    """Return {processorId: processor_name} for the given processor IDs."""
    if not processor_ids:
        return {}
    docs = db.processors.find({"processorId": {"$in": list(processor_ids)}})
    return {
        p["processorId"]: p.get("name", p["processorId"])
        for p in docs
    }


def _build_record_group_lookup(db, rg_ids: set) -> dict:
    """Return {rg_id_str: record_group_doc} for the given record group ID strings."""
    if not rg_ids:
        return {}
    object_ids = []
    for rg_id in rg_ids:
        try:
            object_ids.append(ObjectId(rg_id))
        except Exception:
            pass
    docs = db.record_groups.find({"_id": {"$in": object_ids}})
    return {str(rg["_id"]): rg for rg in docs}


# ── Config ───────────────────────────────────────────────────────────────────

def load_config(institution: str) -> dict:
    """
    Load the institution config from sql_sync/config/{institution}.json.

    Returns an empty dict if no config file exists for the institution.
    """
    path = _CONFIG_DIR / f"{institution}.json"
    if not path.exists():
        return {}
    with open(path) as f:
        return json.load(f)


def _filter_record_groups(rg_lookup: dict, config: dict) -> dict:
    """
    Filter rg_lookup to only record groups listed in config["record_groups"].

    A record group is included if its ObjectId string matches any entry's "id"
    OR its name matches any entry's "name".  Returns the full rg_lookup
    unchanged when config has no record_groups list.
    """
    entries = config.get("record_groups", [])
    if not entries:
        return rg_lookup

    allowed_ids   = {e["id"]   for e in entries if e.get("id")   and e["id"]   != "TODO"}
    allowed_names = {e["name"] for e in entries if e.get("name") and e["name"] != "TODO"}

    if not allowed_ids and not allowed_names:
        return rg_lookup

    filtered = {
        rg_id: rg for rg_id, rg in rg_lookup.items()
        if rg_id in allowed_ids or rg.get("name") in allowed_names
    }
    excluded = len(rg_lookup) - len(filtered)
    if excluded:
        print(f"extract: excluded {excluded} record group(s) not in config allowlist")
    return filtered


# ── Main extract function ─────────────────────────────────────────────────────

def extract(db, dry_run: bool = False, config: dict = None) -> dict:
    """
    Query validated records from MongoDB and return them grouped by processor name.

    Args:
        db:       pymongo database object (from connect())
        dry_run:  if True, print counts by processor and return {} without
                  extracting field values
        config:   optional institution config dict (from load_config()).
                  When provided, only records belonging to record groups listed
                  in config["record_groups"] are included.

    Returns:
        dict mapping processor_name -> list of flat record dicts
    """
    records = list(db.records.find(VALIDATED_QUERY))
    print(f"extract: found {len(records)} validated record(s)")

    if not records:
        return {}

    # Batch-resolve record groups and processors to avoid per-record queries
    rg_ids = {str(r["record_group_id"]) for r in records if r.get("record_group_id")}
    rg_lookup = _build_record_group_lookup(db, rg_ids)

    # Apply record group allowlist from config if present
    if config:
        rg_lookup = _filter_record_groups(rg_lookup, config)
        records = [r for r in records
                   if str(r.get("record_group_id", "")) in rg_lookup]
        print(f"extract: {len(records)} record(s) in allowed record groups")

    processor_ids = {rg.get("processorId") for rg in rg_lookup.values() if rg.get("processorId")}
    proc_lookup = _build_processor_lookup(db, processor_ids)

    if dry_run:
        # Count records by processor without flattening attributes
        counts = defaultdict(int)
        for record in records:
            rg = rg_lookup.get(str(record.get("record_group_id", "")), {})
            proc_id = rg.get("processorId", "unknown")
            proc_name = proc_lookup.get(proc_id, proc_id)
            counts[proc_name] += 1
        print("Record counts by processor:")
        for name, count in sorted(counts.items()):
            print(f"  {name}: {count}")
        return {}

    by_processor = defaultdict(list)

    for record in records:
        rg_id = str(record.get("record_group_id", ""))
        rg = rg_lookup.get(rg_id, {})
        proc_id = rg.get("processorId", "unknown")
        proc_name = proc_lookup.get(proc_id, proc_id)

        filename = record.get("filename", "")
        flat = _flatten_attributes(record.get("attributesList", []))

        flat["_mongo_id"] = str(record["_id"])
        flat["_api"] = _extract_api(filename)
        flat["_filename"] = filename
        flat["_date_created"] = record.get("dateCreated")
        flat["_review_status"] = record.get("review_status")
        flat["_processor_name"] = proc_name

        by_processor[proc_name].append(flat)

    return dict(by_processor)


def _print_diagnostics(db, config: dict = None) -> None:
    """Print database/collection layout and status value counts to diagnose zero results."""
    client = db.client
    print(f"\nConnected database: {db.name}")
    print(f"Available databases: {client.list_database_names()}")
    print(f"Collections in '{db.name}': {db.list_collection_names()}")

    total = db.records.count_documents({})
    matched = db.records.count_documents(VALIDATED_QUERY)
    print(f"\nrecords collection — total: {total}, matching query: {matched}")

    if total == 0:
        return

    for field in ("review_status", "status"):
        pipeline = [{"$group": {"_id": f"${field}", "count": {"$sum": 1}}}, {"$sort": {"count": -1}}]
        buckets = list(db.records.aggregate(pipeline))
        print(f"\n{field} value counts:")
        for b in buckets:
            print(f"  {b['_id']!r}: {b['count']}")

    pipeline = [
        {"$match": VALIDATED_QUERY},
        {"$group": {"_id": "$record_group_id", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
    ]
    rg_buckets = list(db.records.aggregate(pipeline))
    if rg_buckets:
        rg_ids = {str(b["_id"]) for b in rg_buckets}
        rg_lookup = _build_record_group_lookup(db, rg_ids)
        if config:
            rg_lookup = _filter_record_groups(rg_lookup, config)
            rg_buckets = [b for b in rg_buckets if str(b["_id"]) in rg_lookup]

        print("\nValidated record counts by record group:")
        for b in rg_buckets:
            rg_id = str(b["_id"])
            name = rg_lookup.get(rg_id, {}).get("name", rg_id)
            print(f"  {name}: {b['count']}")

        processor_ids = {rg.get("processorId") for rg in rg_lookup.values() if rg.get("processorId")}
        proc_lookup = _build_processor_lookup(db, processor_ids)
        proc_counts: dict[str, int] = defaultdict(int)
        for b in rg_buckets:
            rg = rg_lookup.get(str(b["_id"]), {})
            proc_name = proc_lookup.get(rg.get("processorId"), rg.get("processorId", "unknown"))
            proc_counts[proc_name] += b["count"]

        print("\nValidated record counts by processor:")
        for name, count in sorted(proc_counts.items(), key=lambda x: -x[1]):
            print(f"  {name}: {count}")


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Extract validated OGRRE records from MongoDB."
    )
    parser.add_argument(
        "--db-name",
        required=True,
        help="MongoDB database name (e.g. 'isgs').",
    )
    parser.add_argument(
        "--out",
        default=None,
        help="Write JSON output to this file instead of stdout.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print record counts by processor without extracting field values.",
    )
    args = parser.parse_args()

    db = connect(db_name=args.db_name)
    config = load_config(args.db_name)
    result = extract(db, dry_run=args.dry_run, config=config)

    if args.dry_run:
        _print_diagnostics(db, config=config)
    elif args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, default=str)
        print(f"Wrote output to {args.out}")
    else:
        print(json.dumps(result, indent=2, default=str))
