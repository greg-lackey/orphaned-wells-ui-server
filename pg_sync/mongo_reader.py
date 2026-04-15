"""
mongo_reader.py — Queries MongoDB for reviewed/verified records
that have been updated since the last successful sync.
"""
import logging
from datetime import datetime
from typing import Generator, Optional

from bson import ObjectId
from pymongo import MongoClient
from pymongo.database import Database

log = logging.getLogger(__name__)


def get_mongo_db(mongo_uri: str, db_name: str) -> Database:
    client = MongoClient(mongo_uri, serverSelectionTimeoutMS=10_000)
    return client[db_name]


def get_processor_name(db: Database, record_group_id: str) -> Optional[str]:
    """
    Look up the processor name for a given record_group_id.
    Returns the human-readable processor name (e.g. 'IL_Ver_A_WellCompletion').
    """
    try:
        rg = db.record_groups.find_one({"_id": ObjectId(record_group_id)})
        if not rg:
            return None
        processor_id = rg.get("processorId")
        if not processor_id:
            return None
        proc = db.processors.find_one({"processorId": processor_id})
        if proc:
            return proc.get("name")
        # Fallback: check if processorId matches a name field directly
        proc = db.processors.find_one({"name": processor_id})
        if proc:
            return proc.get("name")
        return None
    except Exception as exc:
        log.warning("Could not resolve processor for record_group %s: %s", record_group_id, exc)
        return None


def iter_reviewed_records(
    db: Database,
    processor_names: list[str],
    since_timestamp: Optional[float] = None,
    batch_size: int = 500,
) -> Generator[tuple[dict, str], None, None]:
    """
    Yields (mongo_doc, processor_name) tuples for all reviewed/verified records
    whose processor matches one of the given names and whose lastUpdated timestamp
    is greater than since_timestamp (if provided).

    The generator resolves the processor name per record once via its record_group.
    """
    query: dict = {
        "review_status": {"$in": ["reviewed", "verified"]},
        "status": "digitized",
    }
    if since_timestamp:
        query["lastUpdated"] = {"$gt": since_timestamp}

    # Build a lookup of record_group_id → processor_name for efficiency
    rg_proc_cache: dict[str, Optional[str]] = {}

    cursor = db.records.find(query, batch_size=batch_size)
    for doc in cursor:
        doc["_id"] = str(doc["_id"])
        rg_id = doc.get("record_group_id", "")

        if rg_id not in rg_proc_cache:
            rg_proc_cache[rg_id] = get_processor_name(db, rg_id)

        proc_name = rg_proc_cache[rg_id]
        if proc_name not in processor_names:
            continue  # not a processor we handle for this form type

        yield doc, proc_name
    
    log.info("Finished iterating records. Resolved %d unique record groups.", len(rg_proc_cache))
