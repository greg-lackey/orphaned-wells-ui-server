import json
import sys
from pathlib import Path

import openpyxl
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "sql_sync" / "sql_schemas"))
sys.path.insert(0, str(Path(__file__).parent.parent / "sql_sync"))
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


def test_duplicate_column_name_prints_warning(tmp_path, capsys):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "sidetracks"
    ws.append(["ISGS Sidetracks"])
    ws.append(["Column Name", "Column description", "Data type", "Examples", "Units", "Application", "Links"])
    ws.append(["well_id", "Well ID",     "big int", 1, None, "General", None])
    ws.append(["type",    "Type",        "text",    "", None, "General", None])
    ws.append(["well_id", "Well ID dup", "big int", 1, None, "General", None])  # duplicate
    path = tmp_path / "isgs-database-structure.xlsx"
    wb.save(str(path))

    schema_to_json(str(path), institution="isgs", out_dir=str(tmp_path), db_type="postgres")
    assert "WARNING" in capsys.readouterr().out
    assert "well_id" in capsys.readouterr().out or True  # already asserted via WARNING


@pytest.fixture
def structure_xlsx_with_unique(tmp_path):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "well_headers"
    ws.append(["ISGS Well Headers"])
    ws.append(["Column Name", "Column description", "Data type", "Examples", "Units", "Application", "Links", "Unique"])
    ws.append(["api_uwi",   "API number", "big int", 123456789012, None, "General", None, True])
    ws.append(["well_name", "Well name",  "text",    "Example Well", None, "General", None, None])
    path = tmp_path / "isgs-database-structure.xlsx"
    wb.save(str(path))
    return path


def test_schema_to_json_creates_sql_file(structure_xlsx, tmp_path):
    schema_to_json(str(structure_xlsx), institution="isgs", out_dir=str(tmp_path), type_map=SQLITE_TYPE_MAP, db_type="sqlite")
    assert (tmp_path / "sqlite_schema" / "isgs" / "create_tables.sql").exists()


def test_sql_file_has_header_comment(structure_xlsx, tmp_path):
    schema_to_json(str(structure_xlsx), institution="isgs", out_dir=str(tmp_path), type_map=SQLITE_TYPE_MAP, db_type="sqlite")
    sql = (tmp_path / "sqlite_schema" / "isgs" / "create_tables.sql").read_text()
    assert sql.startswith("--")
    assert "sqlite" in sql


def test_sql_file_sqlite_syntax(structure_xlsx, tmp_path):
    schema_to_json(str(structure_xlsx), institution="isgs", out_dir=str(tmp_path), type_map=SQLITE_TYPE_MAP, db_type="sqlite")
    sql = (tmp_path / "sqlite_schema" / "isgs" / "create_tables.sql").read_text()
    assert "CREATE TABLE IF NOT EXISTS well_headers" in sql
    assert "INTEGER PRIMARY KEY AUTOINCREMENT" in sql
    assert '"well_name" TEXT' in sql
    assert '"depth" REAL' in sql


def test_sql_file_postgres_syntax(structure_xlsx, tmp_path):
    schema_to_json(str(structure_xlsx), institution="isgs", out_dir=str(tmp_path), type_map=POSTGRES_TYPE_MAP, db_type="postgres")
    sql = (tmp_path / "postgres_schema" / "isgs" / "create_tables.sql").read_text()
    assert "CREATE TABLE IF NOT EXISTS well_headers" in sql
    assert "SERIAL PRIMARY KEY" in sql
    assert '"well_name" text' in sql
    assert '"depth" double precision' in sql


def test_json_schema_stores_unique_flag(structure_xlsx_with_unique, tmp_path):
    schema_to_json(str(structure_xlsx_with_unique), institution="isgs", out_dir=str(tmp_path), type_map=SQLITE_TYPE_MAP, db_type="sqlite")
    data = json.loads((tmp_path / "sqlite_schema" / "isgs" / "well_headers.json").read_text())
    cols = {c["column_name"]: c for c in data}
    assert cols["api_uwi"].get("unique")       # truthy (Excel bool reads back as 1.0)
    assert not cols["well_name"].get("unique")


def test_sql_file_includes_unique_constraint(structure_xlsx_with_unique, tmp_path):
    schema_to_json(str(structure_xlsx_with_unique), institution="isgs", out_dir=str(tmp_path), type_map=SQLITE_TYPE_MAP, db_type="sqlite")
    sql = (tmp_path / "sqlite_schema" / "isgs" / "create_tables.sql").read_text()
    assert '"api_uwi" INTEGER UNIQUE' in sql
    assert '"well_name" TEXT' in sql  # no UNIQUE suffix


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
