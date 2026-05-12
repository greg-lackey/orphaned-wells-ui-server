# sql_sync

ETL pipeline that syncs OGRRE records from MongoDB into a relational database (SQLite or PostgreSQL).

## Pipeline stages

```
MongoDB  →  extract.py  →  transform.py  →  load.py
               ↓                ↓               ↓
          extracted JSON   transformed JSON   SQLite / PostgreSQL
```

1. **extract** — queries MongoDB for reviewed/verified records and flattens them by processor name
2. **transform** — maps OGRRE field names to SQL column names using the institution field mapping
3. **load** — creates tables (SQLite) and bulk-inserts rows

All three stages can be run individually via their CLIs, or together via `run.py`.

## Quick start

```bash
# Full pipeline (SQLite) — MongoDB DB name defaults to institution key
python sql_sync/run.py --institution isgs --db-type sqlite --db-path sql_sync/data/ogrre_isgs.db

# Override DB name when it differs from the institution key
python sql_sync/run.py --institution isgs --db-name isgs_production --db-type postgres

# Full pipeline (PostgreSQL — reads PG_DSN from .env)
python sql_sync/run.py --institution isgs --db-type postgres

# Save intermediate JSON files for inspection
python sql_sync/run.py --institution isgs --db-type sqlite \
                        --db-path sql_sync/data/ogrre_isgs.db \
                        --save-intermediates

# Full reload (truncate tables before inserting)
python sql_sync/run.py --institution isgs --db-type sqlite \
                        --db-path sql_sync/data/ogrre_isgs.db \
                        --truncate
```

## Adding a new institution

Follow these conventions and the pipeline will work without code changes.

### 1. Field mapping

Create `sql_sync/data/field_mapping/<institution>/ogrre_to_<institution>.json`.

The easiest way to produce this file is to export the institution's mapping spreadsheet and run
`schema_excel_to_json.py` (see `sql_sync/sql_schemas/README.md` for details).

The JSON must be a list of objects with these keys (defined in `constants.MAPPING_COLUMNS`):

| Key | Required | Description |
|-----|----------|-------------|
| `Google Processor` | yes | Processor name as it appears in the OGRRE `processor_name` field |
| `OGRRE_Name` | yes | OGRRE extracted field name |
| `Completion Report Table Field` | no | Column in `completion_reports` to populate |
| `Master Table` | no | Master table name (e.g. `well_headers`, `sidetracks`) |
| `Master Field` | no | Column in the master table to populate |

### 2. Schema

Create `sql_sync/data/schemas/<institution>/` and add one JSON schema file per database type:

- `sqlite/<institution>_schema.json` — used for SQLite
- `postgres/<institution>_schema.json` — used for PostgreSQL

Each schema file is a dict mapping table name → list of column descriptors:

```json
{
  "well_headers": [
    {"column_name": "id",      "data_type": "INTEGER"},
    {"column_name": "api_uwi", "data_type": "text"},
    {"column_name": "name",    "data_type": "text"}
  ],
  "completion_reports": [
    {"column_name": "id",        "data_type": "INTEGER"},
    {"column_name": "well_name", "data_type": "text"}
  ]
}
```

### 3. Reserved table names

Two table names are hardcoded as pipeline conventions (see `constants.py`):

| Constant | Table name | Semantics |
|----------|------------|-----------|
| `REPORT_TABLE` | `completion_reports` | One row per OGRRE record |
| `WELL_TABLE` | `well_headers` | One row per unique API number (most-recent-wins) |

Every institution's schema must include these tables.

## Environment variables

Copy `.env.example` to `.env` and fill in:

| Variable | Required | Description |
|----------|----------|-------------|
| `MONGO_USER` | yes | MongoDB Atlas username |
| `MONGO_PASSWORD` | yes | MongoDB Atlas password |
| `MONGO_CLUSTER` | yes | Atlas cluster hostname (e.g. `cluster0.abc123.mongodb.net`) |
| `DB_NAME` | yes | MongoDB database name for this institution |
| `PG_DSN` | postgres only | PostgreSQL connection string (`postgresql://user:pass@host/db`) |

## Running the tests

```bash
pytest tests/
```
