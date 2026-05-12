import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "sql_sync"))
from transform import _build_lookup, transform


MAPPING = [
    {
        "Google Processor": "ProcA",
        "OGRRE_Name": "Well_Name",
        "Completion Report Table Field": "well_name",
        "Master Table": "well_headers",
        "Master Field": "name",
    },
    {
        "Google Processor": "ProcA",
        "OGRRE_Name": "Spud_Date",
        "Completion Report Table Field": "spud_date",
        "Master Table": "well_headers",
        "Master Field": "spud_date",
    },
    {
        "Google Processor": "ProcA",
        "OGRRE_Name": "Comp_Date",
        "Completion Report Table Field": "comp_date",
        "Master Table": "sidetracks",
        "Master Field": "comp_date",
    },
    {
        "Google Processor": "ProcB",
        "OGRRE_Name": "Completion_Date",
        "Completion Report Table Field": "comp_date",
        "Master Table": "sidetracks",
        "Master Field": "comp_date",
    },
]


def _record(proc, api, mongo_id="abc", date_created=1000, **fields):
    return {
        "_mongo_id": mongo_id,
        "_api": api,
        "_filename": f"{api}.pdf",
        "_date_created": date_created,
        "_review_status": "reviewed",
        "_processor_name": proc,
        **fields,
    }


# ── _build_lookup ─────────────────────────────────────────────────────────────

def test_build_lookup_indexes_by_processor_and_ogrre_name():
    lookup = _build_lookup(MAPPING)
    assert "ProcA" in lookup
    assert "Well_Name" in lookup["ProcA"]
    assert lookup["ProcA"]["Well_Name"]["report_col"] == "well_name"
    assert lookup["ProcA"]["Well_Name"]["master_table"] == "well_headers"
    assert lookup["ProcA"]["Well_Name"]["master_col"] == "name"


def test_build_lookup_skips_entries_missing_processor_or_ogrre_name():
    bad = [
        {"Google Processor": "", "OGRRE_Name": "X", "Completion Report Table Field": "x"},
        {"Google Processor": "P", "OGRRE_Name": "", "Completion Report Table Field": "x"},
        {"Google Processor": None, "OGRRE_Name": "X"},
    ]
    lookup = _build_lookup(bad)
    assert lookup == {}


# ── transform ─────────────────────────────────────────────────────────────────

def test_transform_produces_completion_reports_row():
    extracted = {
        "ProcA": [_record("ProcA", "1234567890", Well_Name="Test Well")]
    }
    result = transform(extracted, MAPPING)
    assert len(result["completion_reports"]) == 1
    assert result["completion_reports"][0]["well_name"] == "Test Well"


def test_transform_maps_master_table_fields():
    extracted = {
        "ProcA": [_record("ProcA", "1234567890", Comp_Date="2023-01-01")]
    }
    result = transform(extracted, MAPPING)
    assert "sidetracks" in result
    assert result["sidetracks"][0]["comp_date"] == "2023-01-01"


def test_transform_well_headers_most_recent_wins():
    extracted = {
        "ProcA": [
            _record("ProcA", "1234567890", mongo_id="old", date_created=1000, Well_Name="Old Name"),
            _record("ProcA", "1234567890", mongo_id="new", date_created=2000, Well_Name="New Name"),
        ]
    }
    result = transform(extracted, MAPPING)
    well_rows = result["well_headers"]
    assert len(well_rows) == 1
    assert well_rows[0]["name"] == "New Name"


def test_transform_well_headers_one_row_per_api():
    extracted = {
        "ProcA": [
            _record("ProcA", "1111111111", Well_Name="Well A"),
            _record("ProcA", "2222222222", Well_Name="Well B"),
        ]
    }
    result = transform(extracted, MAPPING)
    assert len(result["well_headers"]) == 2


def test_transform_includes_meta_fields_in_completion_reports():
    extracted = {
        "ProcA": [_record("ProcA", "1234567890", mongo_id="m1")]
    }
    result = transform(extracted, MAPPING)
    row = result["completion_reports"][0]
    assert row["_mongo_id"] == "m1"
    assert row["_api"] == "1234567890"
    assert row["_review_status"] == "reviewed"


def test_transform_unknown_processor_produces_meta_only_report_row():
    extracted = {
        "UnknownProc": [_record("UnknownProc", "9999999999", Well_Name="X")]
    }
    result = transform(extracted, MAPPING)
    assert len(result["completion_reports"]) == 1
    assert "well_name" not in result["completion_reports"][0]


def test_transform_different_processors_same_report_column():
    extracted = {
        "ProcA": [_record("ProcA", "1111111111", Comp_Date="2023-01-01")],
        "ProcB": [_record("ProcB", "2222222222", Completion_Date="2024-06-15")],
    }
    result = transform(extracted, MAPPING)
    comp_dates = {r["_api"]: r.get("comp_date") for r in result["completion_reports"]}
    assert comp_dates["1111111111"] == "2023-01-01"
    assert comp_dates["2222222222"] == "2024-06-15"


def test_transform_empty_extracted_returns_empty():
    assert transform({}, MAPPING) == {}
