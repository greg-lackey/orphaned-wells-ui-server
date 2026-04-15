"""
pg_sync — OGRRE → PostgreSQL ETL pipeline.

Package structure:
  config.py           Environment-based configuration
  field_mappings/     YAML mapping files (OGRRE field → PG column, per institution/form)
  schema/             Hand-authored DDL (.sql files, one per institution/form)
  tools/              Utility scripts (import from xlsx, validate mappings)
  mongo_reader.py     Queries MongoDB for reviewed/verified records
  transformer.py      Pivots attributesList → flat row dict + child row dicts
  pg_writer.py        Upserts rows into PostgreSQL
  sync.py             Orchestrator
  run_sync.py         CLI entry point (called by cron)
"""
