# sql_schemas

Converts SQL database structure and field mapping spreadsheets into JSON files
consumed by the ETL pipeline.

Institution folders live alongside this script.  Each folder holds two
spreadsheets (not tracked in git — see below):

```
sql_sync/sql_schemas/
├── isgs/
│   ├── isgs-database-structure.xlsx
│   └── ogrre-to-isgs-database-mapping.xlsx
└── master/
    ├── master-database-structure.xlsx
    └── ogrre-to-master-database-mapping.xlsx
```

To add a new institution, create a subfolder and drop in the two spreadsheets
following the same naming convention.

## Getting the spreadsheets

`.xlsx` files are **not tracked in git** (binary, large).  Fetch them from the
shared Google Drive before running the generator:

```bash
gcloud storage cp "gs://<bucket>/isgs/isgs-database-structure.xlsx" \
    sql_sync/sql_schemas/isgs/
gcloud storage cp "gs://<bucket>/isgs/ogrre-to-isgs-database-mapping.xlsx" \
    sql_sync/sql_schemas/isgs/
```

Or download them manually from Google Drive and place them in the appropriate
institution subfolder.

## Generating JSON

Requires `pandas` and `openpyxl` — install via `pip install -r requirements-dev.txt`.

```bash
# All institutions, all db types (postgres, sqlite, raw) → sql_sync/data/
python sql_sync/sql_schemas/schema_excel_to_json.py

# One institution only
python sql_sync/sql_schemas/schema_excel_to_json.py --institution isgs

# One institution, postgres schema only
python sql_sync/sql_schemas/schema_excel_to_json.py --institution isgs --db-type postgres
```

## Output structure

```
sql_sync/data/
├── postgres_schema/
│   ├── isgs/
│   │   ├── tables.json       # master index: table -> [column_name, ...]
│   │   ├── well_headers.json
│   │   └── ...
│   └── master/
│       └── ...
├── sqlite_schema/
│   └── ...
├── raw_schema/
│   └── ...
└── field_mapping/
    ├── isgs/
    │   └── ogrre_to_isgs.json
    └── master/
        └── ogrre_to_master.json
```

Commit the regenerated JSON files — they are the source of truth used at runtime.
