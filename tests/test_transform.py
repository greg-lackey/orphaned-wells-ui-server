import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "sql_sync"))
from transform import _build_lookup, _validate_mapping_headers, transform


# ── Fixtures ──────────────────────────────────────────────────────────────────

# Single-report-type mapping (completion_reports only)
MAPPING = {
    "completion_reports": [
        {
            "google_processor": "ProcA",
            "ogrre_field": "Well_Name",
            "report_table": "completion_reports",
            "report_table_field": "well_name",
            "well_table": "well_headers",
            "well_table_field": "name",
        },
        {
            "google_processor": "ProcA",
            "ogrre_field": "Spud_Date",
            "report_table": "completion_reports",
            "report_table_field": "spud_date",
            "well_table": "well_headers",
            "well_table_field": "spud_date",
        },
        {
            "google_processor": "ProcA",
            "ogrre_field": "Comp_Date",
            "report_table": "completion_reports",
            "report_table_field": "comp_date",
            "well_table": "sidetracks",
            "well_table_field": "comp_date",
        },
        {
            "google_processor": "ProcB",
            "ogrre_field": "Completion_Date",
            "report_table": "completion_reports",
            "report_table_field": "comp_date",
            "well_table": "sidetracks",
            "well_table_field": "comp_date",
        },
    ]
}

# Multi-report-type mapping: completion_reports + plugging_reports
MULTI_MAPPING = {
    "completion_reports": [
        {
            "google_processor": "ProcA",
            "ogrre_field": "Well_Name",
            "report_table": "completion_reports",
            "report_table_field": "well_name",
            "well_table": "well_headers",
            "well_table_field": "name",
        },
    ],
    "plugging_reports": [
        {
            "google_processor": "ProcPlug",
            "ogrre_field": "Well_Name",
            "report_table": "plugging_reports",
            "report_table_field": "well_name",
            "well_table": "well_headers",
            "well_table_field": "name",
        },
        {
            "google_processor": "ProcPlug",
            "ogrre_field": "Plug_Date",
            "report_table": "plugging_reports",
            "report_table_field": "plug_date",
            "well_table": None,
            "well_table_field": None,
        },
    ],
}


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

def test_build_lookup_indexes_by_report_table_and_processor():
    lookup = _build_lookup(MAPPING)
    assert "completion_reports" in lookup
    assert "ProcA" in lookup["completion_reports"]
    entry = lookup["completion_reports"]["ProcA"]["Well_Name"]
    assert entry["report_col"] == "well_name"
    assert entry["master_table"] == "well_headers"
    assert entry["master_col"] == "name"


def test_build_lookup_skips_entries_missing_processor_or_ogrre_name():
    bad = {
        "completion_reports": [
            {"google_processor": "",  "ogrre_field": "X", "report_table_field": "x"},
            {"google_processor": "P", "ogrre_field": "",  "report_table_field": "x"},
            {"google_processor": None, "ogrre_field": "X"},
        ]
    }
    lookup = _build_lookup(bad)
    assert lookup == {"completion_reports": {}}


# ── transform — single report type ───────────────────────────────────────────

def test_transform_produces_completion_reports_row():
    extracted = {"ProcA": [_record("ProcA", "1234567890", Well_Name="Test Well")]}
    result = transform(extracted, MAPPING)
    assert len(result["completion_reports"]) == 1
    assert result["completion_reports"][0]["well_name"] == "Test Well"


def test_transform_maps_well_layer_fields():
    extracted = {"ProcA": [_record("ProcA", "1234567890", Comp_Date="2023-01-01")]}
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
    assert len(result["well_headers"]) == 1
    assert result["well_headers"][0]["name"] == "New Name"


def test_transform_well_headers_one_row_per_api():
    extracted = {
        "ProcA": [
            _record("ProcA", "1111111111", Well_Name="Well A"),
            _record("ProcA", "2222222222", Well_Name="Well B"),
        ]
    }
    result = transform(extracted, MAPPING)
    assert len(result["well_headers"]) == 2


def test_transform_includes_meta_fields_in_report_row():
    extracted = {"ProcA": [_record("ProcA", "1234567890", mongo_id="m1")]}
    result = transform(extracted, MAPPING)
    row = result["completion_reports"][0]
    assert row["mongo_id"] == "m1"
    assert row["well_id"] == 1234567890
    assert row["review_status"] == "reviewed"
    assert row["filename"] == "1234567890.pdf"
    assert row["processor_name"] == "ProcA"


def test_transform_skips_unmapped_processor():
    """Processors not found in any mapping file are skipped entirely."""
    extracted = {"UnknownProc": [_record("UnknownProc", "9999999999", Well_Name="X")]}
    result = transform(extracted, MAPPING)
    assert result.get("completion_reports", []) == []


def test_transform_different_processors_same_report_column():
    extracted = {
        "ProcA": [_record("ProcA", "1111111111", Comp_Date="2023-01-01")],
        "ProcB": [_record("ProcB", "2222222222", Completion_Date="2024-06-15")],
    }
    result = transform(extracted, MAPPING)
    comp_dates = {r["well_id"]: r.get("comp_date") for r in result["completion_reports"]}
    assert comp_dates[1111111111] == "2023-01-01"
    assert comp_dates[2222222222] == "2024-06-15"


def test_transform_empty_extracted_returns_empty():
    assert transform({}, MAPPING) == {}


# ── transform — multiple report types ────────────────────────────────────────

def test_transform_routes_processors_to_correct_report_table():
    extracted = {
        "ProcA":    [_record("ProcA",    "1111111111", Well_Name="Comp Well")],
        "ProcPlug": [_record("ProcPlug", "2222222222", Well_Name="Plug Well", Plug_Date="2024-01-01")],
    }
    result = transform(extracted, MULTI_MAPPING)
    assert len(result.get("completion_reports", [])) == 1
    assert len(result.get("plugging_reports", [])) == 1
    assert result["completion_reports"][0]["well_name"] == "Comp Well"
    assert result["plugging_reports"][0]["plug_date"] == "2024-01-01"


def test_transform_well_headers_shared_across_report_types():
    """most-recent-wins on well_headers spans all report types."""
    extracted = {
        "ProcA":    [_record("ProcA",    "1111111111", date_created=1000, Well_Name="Old Name")],
        "ProcPlug": [_record("ProcPlug", "1111111111", date_created=2000, Well_Name="New Name")],
    }
    result = transform(extracted, MULTI_MAPPING)
    assert len(result["well_headers"]) == 1
    assert result["well_headers"][0]["name"] == "New Name"


def test_transform_unmapped_processor_does_not_affect_other_tables():
    """An unmapped processor is skipped; mapped processors still produce rows."""
    extracted = {
        "ProcA":    [_record("ProcA",    "1111111111", Well_Name="Good Well")],
        "BadProc":  [_record("BadProc",  "2222222222", Well_Name="Ignored")],
    }
    result = transform(extracted, MAPPING)
    assert len(result["completion_reports"]) == 1
    assert result["completion_reports"][0]["well_name"] == "Good Well"


# ── warnings ─────────────────────────────────────────────────────────────────

def test_transform_warns_on_unmapped_processor(capsys):
    extracted = {
        "UnknownProc": [_record("UnknownProc", "9999999999")],
        "ProcA":       [_record("ProcA",       "1111111111")],
    }
    transform(extracted, MAPPING)
    out = capsys.readouterr().out
    assert "WARNING" in out
    assert "UnknownProc" in out
    assert "ProcA" not in out


def test_validate_mapping_headers_warns_on_missing_column(capsys):
    bad_mapping = [{"google_processor": "P", "ogrre_field": "X"}]  # missing required cols
    _validate_mapping_headers(bad_mapping)
    out = capsys.readouterr().out
    assert "WARNING" in out
    assert "report_table_field" in out


def test_validate_mapping_headers_includes_table_name_in_warning(capsys):
    bad_mapping = [{"google_processor": "P", "ogrre_field": "X"}]
    _validate_mapping_headers(bad_mapping, table_name="plugging_reports")
    out = capsys.readouterr().out
    assert "plugging_reports" in out


# ── non-None overwrites ───────────────────────────────────────────────────────

_ALIAS_MAPPING = {
    "completion_reports": [
        # Two field names alias to the same column (single vs numbered casing)
        {
            "google_processor": "ProcG",
            "ogrre_field": "Casing_Record_Depth",
            "report_table": "completion_reports",
            "report_table_field": "casing_1_depth",
            "well_table": None,
            "well_table_field": None,
        },
        {
            "google_processor": "ProcG",
            "ogrre_field": "Casing_Record_1_Depth",
            "report_table": "completion_reports",
            "report_table_field": "casing_1_depth",
            "well_table": None,
            "well_table_field": None,
        },
    ]
}


def test_non_none_overwrites_single_casing_record():
    """Single-casing doc: un-numbered key has value, numbered key is absent."""
    extracted = {
        "ProcG": [_record("ProcG", "1234567890", Casing_Record_Depth=1234)]
    }
    result = transform(extracted, _ALIAS_MAPPING)
    assert result["completion_reports"][0]["casing_1_depth"] == 1234


def test_non_none_overwrites_multi_casing_record():
    """Multi-casing doc: numbered key has value, un-numbered key is absent."""
    extracted = {
        "ProcG": [_record("ProcG", "1234567890", Casing_Record_1_Depth=5678)]
    }
    result = transform(extracted, _ALIAS_MAPPING)
    assert result["completion_reports"][0]["casing_1_depth"] == 5678


def test_non_none_does_not_overwrite_with_none():
    """A None value must not overwrite a previously set non-None value."""
    # Both present but only Casing_Record_Depth has a value
    extracted = {
        "ProcG": [_record("ProcG", "1234567890",
                           Casing_Record_Depth=999,
                           Casing_Record_1_Depth=None)]
    }
    result = transform(extracted, _ALIAS_MAPPING)
    assert result["completion_reports"][0]["casing_1_depth"] == 999
