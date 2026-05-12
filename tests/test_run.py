import sqlite3
import sys
from pathlib import Path
from bson import ObjectId

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "sql_sync"))
from run import run_pipeline

SCHEMA = {
    "well_headers": [
        {"column_name": "id",      "data_type": "INTEGER"},
        {"column_name": "api_uwi", "data_type": "string"},
        {"column_name": "name",    "data_type": "string"},
    ],
    "completion_reports": [
        {"column_name": "id",        "data_type": "INTEGER"},
        {"column_name": "well_name", "data_type": "string"},
        {"column_name": "comp_date", "data_type": "date"},
    ],
}

MAPPING = {
    "completion_reports": [
        {
            "Google Processor": "WellCompletion",
            "OGRRE Field": "Well_Name",
            "Report Table Field": "well_name",
            "Well Table": "well_headers",
            "Well Field": "name",
        },
        {
            "Google Processor": "WellCompletion",
            "OGRRE Field": "Comp_Date",
            "Report Table Field": "comp_date",
            "Well Table": None,
            "Well Field": None,
        },
    ]
}

EXTRACTED = {
    "WellCompletion": [
        {
            "_mongo_id": str(ObjectId()),
            "_api": "1234567890",
            "_filename": "1234567890_WellCompletion.pdf",
            "_date_created": 1700000000,
            "_review_status": "reviewed",
            "_processor_name": "WellCompletion",
            "Well_Name": "Test Well",
            "Comp_Date": "2023-01-01",
        }
    ]
}


@pytest.fixture
def mem_db(tmp_path):
    db_path = str(tmp_path / "test.db")
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    for table, cols in SCHEMA.items():
        col_defs = ["id INTEGER PRIMARY KEY AUTOINCREMENT"]
        for col in cols:
            if col["column_name"] == "id":
                continue
            col_defs.append(f'"{col["column_name"]}" TEXT')
        conn.execute(f"CREATE TABLE {table} ({', '.join(col_defs)})")
    conn.commit()
    return conn, db_path


def test_run_pipeline_inserts_completion_report(mem_db, monkeypatch):
    conn, db_path = mem_db

    monkeypatch.setattr("run.load_mapping", lambda institution: MAPPING)
    monkeypatch.setattr("run.load_schema", lambda institution, db_type: SCHEMA)
    monkeypatch.setattr("run.connect_sqlite", lambda path: conn)
    monkeypatch.setattr("run.create_tables_sqlite", lambda conn, schema: None)

    run_pipeline(EXTRACTED, "isgs", "sqlite", db_path)

    verify = sqlite3.connect(db_path)
    rows = verify.execute("SELECT well_name FROM completion_reports").fetchall()
    verify.close()
    assert len(rows) == 1
    assert rows[0][0] == "Test Well"


def test_run_pipeline_inserts_well_header(mem_db, monkeypatch):
    conn, db_path = mem_db

    monkeypatch.setattr("run.load_mapping", lambda institution: MAPPING)
    monkeypatch.setattr("run.load_schema", lambda institution, db_type: SCHEMA)
    monkeypatch.setattr("run.connect_sqlite", lambda path: conn)
    monkeypatch.setattr("run.create_tables_sqlite", lambda conn, schema: None)

    run_pipeline(EXTRACTED, "isgs", "sqlite", db_path)

    verify = sqlite3.connect(db_path)
    rows = verify.execute("SELECT api_uwi, name FROM well_headers").fetchall()
    verify.close()
    assert len(rows) == 1
    assert rows[0][0] == "1234567890"
    assert rows[0][1] == "Test Well"


def test_run_pipeline_truncate_clears_existing(mem_db, monkeypatch):
    conn, db_path = mem_db
    conn.execute("INSERT INTO completion_reports (well_name) VALUES ('Old Well')")
    conn.commit()
    conn.close()

    new_conn = sqlite3.connect(db_path)
    monkeypatch.setattr("run.load_mapping", lambda institution: MAPPING)
    monkeypatch.setattr("run.load_schema", lambda institution, db_type: SCHEMA)
    monkeypatch.setattr("run.connect_sqlite", lambda path: new_conn)
    monkeypatch.setattr("run.create_tables_sqlite", lambda conn, schema: None)

    run_pipeline(EXTRACTED, "isgs", "sqlite", db_path, truncate=True)

    verify = sqlite3.connect(db_path)
    rows = verify.execute("SELECT well_name FROM completion_reports").fetchall()
    verify.close()
    assert len(rows) == 1
    assert rows[0][0] == "Test Well"
