import json
import sys
from pathlib import Path

import openpyxl
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "sql_sync" / "sql_schemas"))
from schema_excel_to_json import POSTGRES_TYPE_MAP, SQLITE_TYPE_MAP, mapping_to_json, schema_to_json


@pytest.fixture
def structure_xlsx(tmp_path):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "well_headers"
    ws.append(["ISGS Well Headers"])  # title row (skipped)
    ws.append(["Column Name", "Column description", "Data type", "Examples", "Units", "Application", "Links"])
    ws.append(["api",       "API number",   "big int", 123456789012, None,  "General", None])
    ws.append(["well_name", "Well name",    "text",    "Example Well", None, "General", None])
    ws.append(["depth",     "Total depth",  "float",   1234.5,         "ft", "General", None])
    path = tmp_path / "isgs-database-structure.xlsx"
    wb.save(str(path))
    return path


@pytest.fixture
def mapping_xlsx(tmp_path):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "ogrre_to_isgs"
    ws.append(["Google Processor", "OGRRE_Name", "ISGS Table", "ISGS Field", "Note"])
    ws.append(["WellCompletion",   "well_name",  "well_headers", "well_name", None])
    ws.append(["WellCompletion",   "api",        "well_headers", "api",       None])
    path = tmp_path / "ogrre-to-isgs-database-mapping.xlsx"
    wb.save(str(path))
    return path


def test_creates_expected_files(structure_xlsx, tmp_path):
    schema_to_json(str(structure_xlsx), institution="isgs", out_dir=str(tmp_path), type_map=POSTGRES_TYPE_MAP, db_type="postgres")
    schema_dir = tmp_path / "postgres_schema" / "isgs"
    assert (schema_dir / "well_headers.json").exists()
    assert (schema_dir / "tables.json").exists()


def test_applies_type_map(structure_xlsx, tmp_path):
    schema_to_json(str(structure_xlsx), institution="isgs", out_dir=str(tmp_path), type_map=POSTGRES_TYPE_MAP, db_type="postgres")
    data = json.loads((tmp_path / "postgres_schema" / "isgs" / "well_headers.json").read_text())
    types = {col["column_name"]: col["data_type"] for col in data}
    assert types["api"] == "bigint"
    assert types["well_name"] == "text"
    assert types["depth"] == "double precision"


def test_type_lookup_is_case_insensitive(tmp_path):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "casings"
    ws.append(["ISGS Casings"])
    ws.append(["Column Name", "Column description", "Data type", "Examples", "Units", "Application", "Links"])
    ws.append(["id",   "ID",   "Big int", 1, None, "General", None])  # capital B
    ws.append(["size", "Size", "Int",     4, None, "General", None])  # capital I
    path = tmp_path / "isgs-database-structure.xlsx"
    wb.save(str(path))

    schema_to_json(str(path), institution="isgs", out_dir=str(tmp_path), type_map=POSTGRES_TYPE_MAP, db_type="postgres")
    data = json.loads((tmp_path / "postgres_schema" / "isgs" / "casings.json").read_text())
    types = {col["column_name"]: col["data_type"] for col in data}
    assert types["id"] == "bigint"
    assert types["size"] == "integer"


def test_tables_index_lists_all_columns(structure_xlsx, tmp_path):
    schema_to_json(str(structure_xlsx), institution="isgs", out_dir=str(tmp_path), type_map=POSTGRES_TYPE_MAP, db_type="postgres")
    index = json.loads((tmp_path / "postgres_schema" / "isgs" / "tables.json").read_text())
    assert "well_headers" in index
    assert index["well_headers"] == ["api", "well_name", "depth"]


def test_mapping_to_json_creates_expected_file(mapping_xlsx, tmp_path):
    mapping_to_json(str(mapping_xlsx), institution="isgs", out_dir=str(tmp_path))
    out_file = tmp_path / "field_mapping" / "isgs" / "ogrre_to_isgs.json"
    assert out_file.exists()


def test_mapping_to_json_content(mapping_xlsx, tmp_path):
    mapping_to_json(str(mapping_xlsx), institution="isgs", out_dir=str(tmp_path))
    data = json.loads((tmp_path / "field_mapping" / "isgs" / "ogrre_to_isgs.json").read_text())
    assert len(data) == 2
    assert data[0]["OGRRE_Name"] == "well_name"
    assert data[0]["ISGS Table"] == "well_headers"
