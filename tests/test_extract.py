import sys
from pathlib import Path
from unittest.mock import MagicMock
from bson import ObjectId

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "sql_sync"))
from extract import _extract_api, _flatten_attributes, extract


# ── _extract_api ──────────────────────────────────────────────────────────────

@pytest.mark.parametrize("filename,expected", [
    ("51-231-23450_WellCompletion.pdf", "5123123450"),
    ("5123123450_WellCompletion.pdf",   "5123123450"),
    ("API51-231-23450_report.pdf",      "5123123450"),
    ("no_api_here.pdf",                 None),
    ("",                                None),
])
def test_extract_api(filename, expected):
    assert _extract_api(filename) == expected


# ── _flatten_attributes ───────────────────────────────────────────────────────

def test_flatten_attributes_prefers_normalized_value():
    attrs = [
        {"key": "well_name", "normalized_value": "Reviewed Name", "value": "AI Name"},
        {"key": "depth",     "normalized_value": 1234.5,           "value": None},
    ]
    result = _flatten_attributes(attrs)
    assert result["well_name"] == "Reviewed Name"
    assert result["depth"] == 1234.5


def test_flatten_attributes_falls_back_to_value():
    attrs = [
        {"key": "well_name", "normalized_value": None, "value": "AI Name"},
        {"key": "county",    "value": "Cook"},           # no normalized_value key at all
    ]
    result = _flatten_attributes(attrs)
    assert result["well_name"] == "AI Name"
    assert result["county"] == "Cook"


def test_flatten_attributes_returns_null_when_both_absent():
    attrs = [{"key": "depth", "normalized_value": None, "value": None}]
    assert _flatten_attributes(attrs) == {"depth": None}


def test_flatten_attributes_skips_entries_without_key():
    attrs = [{"value": "orphaned"}, {"key": "api_uwi", "normalized_value": "123"}]
    assert _flatten_attributes(attrs) == {"api_uwi": "123"}


# ── extract() ────────────────────────────────────────────────────────────────

def _make_db(records, record_groups, processors):
    """Build a minimal mock pymongo database."""
    rg_id = ObjectId()

    db = MagicMock()
    db.records.find.return_value = records
    db.record_groups.find.return_value = record_groups
    db.processors.find.return_value = processors
    return db, rg_id


def test_extract_groups_by_processor():
    rg_id = ObjectId()
    proc_id = "abc123"

    records = [
        {
            "_id": ObjectId(),
            "record_group_id": str(rg_id),
            "filename": "51-231-23450_WellCompletion.pdf",
            "review_status": "reviewed",
            "status": "digitized",
            "dateCreated": 1700000000,
            "attributesList": [{"key": "well_name", "value": "Test Well"}],
        }
    ]
    record_groups = [{"_id": rg_id, "processorId": proc_id}]
    processors = [{"processorId": proc_id, "name": "WellCompletion"}]

    db = MagicMock()
    db.records.find.return_value = records
    db.record_groups.find.return_value = record_groups
    db.processors.find.return_value = processors

    result = extract(db)

    assert "WellCompletion" in result
    assert len(result["WellCompletion"]) == 1


def test_extract_parses_api_from_filename():
    rg_id = ObjectId()
    proc_id = "abc123"

    records = [
        {
            "_id": ObjectId(),
            "record_group_id": str(rg_id),
            "filename": "51-231-23450_WellCompletion.pdf",
            "review_status": "verified",
            "status": "reprocessed",
            "dateCreated": 1700000000,
            "attributesList": [],
        }
    ]
    db = MagicMock()
    db.records.find.return_value = records
    db.record_groups.find.return_value = [{"_id": rg_id, "processorId": proc_id}]
    db.processors.find.return_value = [{"processorId": proc_id, "name": "WellCompletion"}]

    result = extract(db)
    record = result["WellCompletion"][0]

    assert record["_api"] == "5123123450"
    assert record["_review_status"] == "verified"


def test_extract_dry_run_returns_empty(capsys):
    rg_id = ObjectId()
    proc_id = "abc123"

    records = [
        {
            "_id": ObjectId(),
            "record_group_id": str(rg_id),
            "filename": "51-231-23450_WellCompletion.pdf",
            "review_status": "reviewed",
            "status": "digitized",
            "dateCreated": 1700000000,
            "attributesList": [{"key": "well_name", "value": "Test Well"}],
        }
    ]
    db = MagicMock()
    db.records.find.return_value = records
    db.record_groups.find.return_value = [{"_id": rg_id, "processorId": proc_id}]
    db.processors.find.return_value = [{"processorId": proc_id, "name": "WellCompletion"}]

    result = extract(db, dry_run=True)

    assert result == {}
    captured = capsys.readouterr()
    assert "WellCompletion: 1" in captured.out


def test_extract_empty_returns_empty():
    db = MagicMock()
    db.records.find.return_value = []
    assert extract(db) == {}
