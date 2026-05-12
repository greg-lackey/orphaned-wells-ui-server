import sqlite3
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "sql_sync"))
from load import (
    _insertable_columns,
    _placeholders,
    _postgres_type,
    _sqlite_type,
    create_tables_postgres,
    create_tables_sqlite,
    insert_table,
    load,
)

# ── Fixtures ──────────────────────────────────────────────────────────────────

SCHEMA = {
    "well_headers": [
        {"column_name": "id",      "data_type": "INTEGER"},
        {"column_name": "api_uwi", "data_type": "string"},
        {"column_name": "name",    "data_type": "string"},
        {"column_name": "county",  "data_type": "string"},
    ],
    "completion_reports": [
        {"column_name": "id",          "data_type": "INTEGER"},
        {"column_name": "well_name",   "data_type": "string"},
        {"column_name": "comp_date",   "data_type": "date"},
        {"column_name": "spud_date",   "data_type": "date"},
    ],
}


@pytest.fixture
def mem_db():
    """In-memory SQLite connection with tables created from SCHEMA."""
    conn = sqlite3.connect(":memory:")
    conn.execute("PRAGMA foreign_keys = ON")
    create_tables_sqlite(conn, SCHEMA)
    return conn


# ── _sqlite_type / _postgres_type ────────────────────────────────────────────

@pytest.mark.parametrize("data_type,expected", [
    ("bigint",    "INTEGER"),
    ("integer",   "INTEGER"),
    ("numeric",   "NUMERIC"),
    ("string",    "TEXT"),
    ("text",      "TEXT"),
    ("date",      "TEXT"),
    ("boolean",   "INTEGER"),
    ("BIGINT",    "INTEGER"),   # case-insensitive
    ("unknown",   "TEXT"),      # falls back to TEXT
])
def test_sqlite_type(data_type, expected):
    assert _sqlite_type(data_type) == expected


@pytest.mark.parametrize("data_type,expected", [
    ("bigint",           "bigint"),
    ("big int",          "bigint"),
    ("integer",          "integer"),
    ("text",             "text"),
    ("double precision", "double precision"),
    ("float",            "double precision"),
    ("boolean",          "boolean"),
    ("date",             "date"),
    ("BIGINT",           "bigint"),    # case-insensitive
    ("unknown",          "text"),      # fallback
])
def test_postgres_type(data_type, expected):
    assert _postgres_type(data_type) == expected


# ── _insertable_columns ───────────────────────────────────────────────────────

def test_insertable_columns_excludes_id():
    cols = _insertable_columns(SCHEMA["well_headers"])
    assert "id" not in cols
    assert "api_uwi" in cols


def test_insertable_columns_order_preserved():
    cols = _insertable_columns(SCHEMA["completion_reports"])
    assert cols == ["well_name", "comp_date", "spud_date"]


# ── _placeholders ─────────────────────────────────────────────────────────────

def test_placeholders_sqlite():
    assert _placeholders("sqlite", 3) == "?, ?, ?"


def test_placeholders_postgres():
    assert _placeholders("postgres", 3) == "%s, %s, %s"


# ── create_tables_sqlite ──────────────────────────────────────────────────────

def test_create_tables_creates_all_tables(mem_db):
    tables = {r[0] for r in mem_db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert "well_headers" in tables
    assert "completion_reports" in tables


def test_create_tables_id_is_primary_key(mem_db):
    info = mem_db.execute("PRAGMA table_info(well_headers)").fetchall()
    id_col = next(c for c in info if c[1] == "id")
    assert id_col[5] == 1  # pk flag


def test_create_tables_is_idempotent(mem_db):
    create_tables_sqlite(mem_db, SCHEMA)  # second call must not raise


def test_create_tables_sqlite_unique_constraint():
    schema = {
        "well_headers": [
            {"column_name": "id",      "data_type": "INTEGER"},
            {"column_name": "api_uwi", "data_type": "string", "unique": True},
            {"column_name": "name",    "data_type": "string"},
        ]
    }
    conn = sqlite3.connect(":memory:")
    create_tables_sqlite(conn, schema)
    conn.execute('INSERT INTO well_headers ("api_uwi") VALUES ("12345")')
    conn.commit()
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute('INSERT INTO well_headers ("api_uwi") VALUES ("12345")')
        conn.commit()


def test_create_tables_postgres_ddl():
    """create_tables_postgres generates correct DDL with SERIAL PK and UNIQUE."""
    schema = {
        "well_headers": [
            {"column_name": "id",      "data_type": "integer"},
            {"column_name": "api_uwi", "data_type": "text", "unique": True},
            {"column_name": "name",    "data_type": "text"},
        ]
    }
    conn = MagicMock()
    cur = conn.cursor.return_value
    create_tables_postgres(conn, schema)
    assert cur.execute.called
    ddl = cur.execute.call_args[0][0]
    assert "CREATE TABLE IF NOT EXISTS well_headers" in ddl
    assert "id SERIAL PRIMARY KEY" in ddl
    assert '"api_uwi" text UNIQUE' in ddl
    assert '"name" text' in ddl
    conn.commit.assert_called_once()


# ── insert_table ──────────────────────────────────────────────────────────────

def test_insert_table_inserts_rows(mem_db):
    rows = [{"api_uwi": "1234567890", "name": "Test Well", "county": "Cook"}]
    col_names = _insertable_columns(SCHEMA["well_headers"])
    inserted, skipped = insert_table(mem_db, "sqlite", "well_headers", rows, col_names)
    assert inserted == 1
    assert skipped == 0
    result = mem_db.execute("SELECT api_uwi, name FROM well_headers").fetchone()
    assert result == ("1234567890", "Test Well")


def test_insert_table_filters_to_col_names(mem_db):
    rows = [{"api_uwi": "9999999999", "name": "Well", "_mongo_id": "abc", "_extra": "ignored"}]
    col_names = _insertable_columns(SCHEMA["well_headers"])
    insert_table(mem_db, "sqlite", "well_headers", rows, col_names)
    cols = [desc[0] for desc in mem_db.execute("SELECT * FROM well_headers").description]
    assert "_mongo_id" not in cols
    assert "_extra" not in cols


def test_insert_table_missing_field_inserts_null(mem_db):
    rows = [{"api_uwi": "1111111111"}]  # name and county missing
    col_names = _insertable_columns(SCHEMA["well_headers"])
    insert_table(mem_db, "sqlite", "well_headers", rows, col_names)
    result = mem_db.execute("SELECT name FROM well_headers").fetchone()
    assert result[0] is None


def test_insert_table_empty_rows_returns_zero(mem_db):
    col_names = _insertable_columns(SCHEMA["well_headers"])
    inserted, skipped = insert_table(mem_db, "sqlite", "well_headers", [], col_names)
    assert inserted == 0
    assert skipped == 0


# ── load ──────────────────────────────────────────────────────────────────────

def test_load_inserts_into_multiple_tables(mem_db):
    transformed = {
        "well_headers": [{"_api": "1234567890", "name": "Well A"}],
        "completion_reports": [{"well_name": "Well A", "comp_date": "2023-01-01"}],
    }
    load(transformed, SCHEMA, mem_db, "sqlite")
    assert mem_db.execute("SELECT COUNT(*) FROM well_headers").fetchone()[0] == 1
    assert mem_db.execute("SELECT COUNT(*) FROM completion_reports").fetchone()[0] == 1


def test_load_api_fallback_populates_api_uwi(mem_db):
    transformed = {
        "well_headers": [{"_api": "5551234567", "name": "Fallback Well"}],
    }
    load(transformed, SCHEMA, mem_db, "sqlite")
    result = mem_db.execute("SELECT api_uwi FROM well_headers").fetchone()
    assert result[0] == "5551234567"


def test_load_skips_table_not_in_schema(mem_db, capsys):
    transformed = {"unknown_table": [{"col": "val"}]}
    load(transformed, SCHEMA, mem_db, "sqlite")
    assert "skipped" in capsys.readouterr().out


def test_load_truncate_clears_existing_rows(mem_db):
    transformed = {"well_headers": [{"api_uwi": "1111111111", "name": "First"}]}
    load(transformed, SCHEMA, mem_db, "sqlite")
    assert mem_db.execute("SELECT COUNT(*) FROM well_headers").fetchone()[0] == 1

    transformed2 = {"well_headers": [{"api_uwi": "2222222222", "name": "Second"}]}
    load(transformed2, SCHEMA, mem_db, "sqlite", truncate=True)
    count = mem_db.execute("SELECT COUNT(*) FROM well_headers").fetchone()[0]
    assert count == 1
    name = mem_db.execute("SELECT name FROM well_headers").fetchone()[0]
    assert name == "Second"
