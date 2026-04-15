"""
tools/validate_mappings.py — Pre-flight check for YAML field mapping files.

Verifies that every PostgreSQL column referenced in a YAML mapping actually
exists in the corresponding schema.sql DDL. Intended to run in CI before
any sync to catch typos before they silently drop data.

Usage:
    python pg_sync/tools/validate_mappings.py --collaborator isgs --form completion_reports
    python pg_sync/tools/validate_mappings.py  # validates all known mappings
"""
import argparse
import re
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    print("ERROR: Install pyyaml: pip install pyyaml")
    sys.exit(1)

REPO_ROOT = Path(__file__).parent.parent.parent
MAPPING_DIR = Path(__file__).parent.parent / "field_mappings"
SCHEMA_DIR  = Path(__file__).parent.parent / "schema"


def extract_columns_from_sql(sql_path: Path) -> dict[str, set[str]]:
    """
    Parse a schema .sql file and return {table_name: {column_names}}.
    Uses a simple regex — good enough for our hand-authored DDL.
    """
    text = sql_path.read_text()
    tables: dict[str, set[str]] = {}

    # Match CREATE TABLE [IF NOT EXISTS] schema.tablename ( ... )
    table_re = re.compile(
        r"CREATE TABLE(?:\s+IF NOT EXISTS)?\s+"
        r"(?:\w+\.)?(\w+)\s*\(([^;]+?)\)\s*;",
        re.IGNORECASE | re.DOTALL,
    )
    col_re = re.compile(r"^\s{4}(\w+)\s+", re.MULTILINE)

    for m in table_re.finditer(text):
        table_name  = m.group(1).lower()
        table_body  = m.group(2)
        col_names   = {c.lower() for c in col_re.findall(table_body)
                       if c.upper() not in ("PRIMARY", "CONSTRAINT", "FOREIGN", "UNIQUE", "CHECK")}
        tables[table_name] = col_names

    return tables


def validate_mapping(
    collaborator: str,
    form_type: str,
    verbose: bool = False,
) -> list[str]:
    """
    Validate one mapping file against its schema.sql.
    Returns a list of error strings (empty = all good).
    """
    mapping_path = MAPPING_DIR / collaborator / f"{form_type}.yaml"
    schema_path  = SCHEMA_DIR  / collaborator / f"{form_type}.sql"

    errors: list[str] = []

    if not mapping_path.exists():
        return [f"Mapping file not found: {mapping_path}"]
    if not schema_path.exists():
        return [f"Schema file not found: {schema_path}"]

    with open(mapping_path) as f:
        mapping = yaml.safe_load(f)

    schema_tables = extract_columns_from_sql(schema_path)
    target_table  = mapping.get("target_table", form_type).lower()
    target_cols   = schema_tables.get(target_table, set())
    child_table_map = mapping.get("child_tables", {})

    if not target_cols:
        errors.append(f"Table '{target_table}' not found in {schema_path.name}")

    for proc_name, proc_data in mapping.get("processors", {}).items():
        # Validate scalar fields
        for ogrre_field, pg_col in proc_data.get("scalar_fields", {}).items():
            if pg_col and pg_col.lower() not in target_cols:
                errors.append(
                    f"[{proc_name}] scalar '{ogrre_field}' → '{pg_col}' "
                    f"not found in {target_table}"
                )

        # Validate child table subfields
        for parent_field, subfields in proc_data.get("child_fields", {}).items():
            child_table = child_table_map.get(parent_field, "").lower()
            child_cols  = schema_tables.get(child_table, set())
            if not child_cols and child_table:
                errors.append(
                    f"[{proc_name}] child table '{child_table}' "
                    f"not found in {schema_path.name}"
                )
            for sub_field, pg_col in subfields.items():
                if pg_col and pg_col.lower() not in child_cols:
                    errors.append(
                        f"[{proc_name}] child '{parent_field}::{sub_field}' → "
                        f"'{child_table}.{pg_col}' not in schema"
                    )

    # Validate interval fields
    for compound_key, spec in mapping.get("interval_fields", {}).items():
        for col_key in ("from_col", "to_col", "raw_col"):
            pg_col = spec.get(col_key)
            if pg_col and pg_col.lower() not in target_cols:
                # Could be in a child table — check
                found_in_child = any(
                    pg_col.lower() in cols
                    for tbl, cols in schema_tables.items()
                    if tbl != target_table
                )
                if not found_in_child:
                    errors.append(
                        f"interval_field '{compound_key}'.{col_key}='{pg_col}' "
                        f"not found in schema"
                    )

    if verbose and not errors:
        print(f"  ✓ {collaborator}/{form_type} — all columns valid")

    return errors


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate YAML field mappings against schema.")
    parser.add_argument("--collaborator", default=None)
    parser.add_argument("--form",         default=None)
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    # Discover all mapping files if not specified
    pairs: list[tuple[str, str]] = []
    if args.collaborator and args.form:
        pairs = [(args.collaborator, args.form)]
    else:
        for collab_dir in MAPPING_DIR.iterdir():
            if not collab_dir.is_dir():
                continue
            for yaml_file in collab_dir.glob("*.yaml"):
                pairs.append((collab_dir.name, yaml_file.stem))

    if not pairs:
        print("No mapping files found.")
        sys.exit(0)

    all_errors: list[str] = []
    for collaborator, form_type in sorted(pairs):
        errs = validate_mapping(collaborator, form_type, verbose=args.verbose)
        for e in errs:
            print(f"ERROR [{collaborator}/{form_type}]: {e}")
        all_errors.extend(errs)

    if all_errors:
        print(f"\n{len(all_errors)} validation error(s) found.")
        sys.exit(1)
    else:
        print(f"All {len(pairs)} mapping file(s) valid.")
