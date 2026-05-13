import sys
from pathlib import Path
from unittest.mock import MagicMock
from bson import ObjectId

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "sql_sync"))
from extract import _extract_api, _filter_record_groups, _flatten_attributes, extract


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


# ── _filter_record_groups ─────────────────────────────────────────────────────

_RG_LOOKUP = {
    "aaa111": {"_id": "aaa111", "name": "Good_Group_1"},
    "bbb222": {"_id": "bbb222", "name": "Good_Group_2"},
    "ccc333": {"_id": "ccc333", "name": "rg test"},
}


def test_filter_record_groups_by_id():
    config = {"record_groups": [{"name": "Good_Group_1", "id": "aaa111"}]}
    result = _filter_record_groups(_RG_LOOKUP, config)
    assert set(result.keys()) == {"aaa111"}


def test_filter_record_groups_by_name():
    config = {"record_groups": [{"name": "Good_Group_2", "id": "nonexistent-id"}]}
    result = _filter_record_groups(_RG_LOOKUP, config)
    assert set(result.keys()) == {"bbb222"}


def test_filter_record_groups_excludes_unlisted():
    config = {"record_groups": [
        {"name": "Good_Group_1", "id": "aaa111"},
        {"name": "Good_Group_2", "id": "bbb222"},
    ]}
    result = _filter_record_groups(_RG_LOOKUP, config)
    assert "ccc333" not in result
    assert len(result) == 2


def test_filter_record_groups_empty_config_returns_all():
    assert _filter_record_groups(_RG_LOOKUP, {}) == _RG_LOOKUP
    assert _filter_record_groups(_RG_LOOKUP, {"record_groups": []}) == _RG_LOOKUP


def test_filter_record_groups_ignores_todo_placeholders():
    config = {"record_groups": [{"name": "TODO", "id": "TODO"}]}
    result = _filter_record_groups(_RG_LOOKUP, config)
    assert result == _RG_LOOKUP


def test_extract_respects_config_allowlist():
    rg_id_good = ObjectId()
    rg_id_test = ObjectId()
    proc_id = "abc123"

    records = [
        {
            "_id": ObjectId(),
            "record_group_id": str(rg_id_good),
            "filename": "51-231-23450_WellCompletion.pdf",
            "review_status": "reviewed",
            "status": "digitized",
            "dateCreated": 1700000000,
            "attributesList": [{"key": "well_name", "normalized_value": "Good Well", "value": None}],
        },
        {
            "_id": ObjectId(),
            "record_group_id": str(rg_id_test),
            "filename": "99-999-99999_WellCompletion.pdf",
            "review_status": "reviewed",
            "status": "digitized",
            "dateCreated": 1700000000,
            "attributesList": [{"key": "well_name", "normalized_value": "Test Well", "value": None}],
        },
    ]
    db = MagicMock()
    db.records.find.return_value = records
    db.record_groups.find.return_value = [
        {"_id": rg_id_good, "name": "Good_Group",  "processorId": proc_id},
        {"_id": rg_id_test, "name": "rg test",     "processorId": proc_id},
    ]
    db.processors.find.return_value = [{"processorId": proc_id, "name": "WellCompletion"}]

    config = {"record_groups": [{"name": "Good_Group", "id": str(rg_id_good)}]}
    result = extract(db, config=config)

    assert "WellCompletion" in result
    assert len(result["WellCompletion"]) == 1
    assert result["WellCompletion"][0]["well_name"] == "Good Well"
