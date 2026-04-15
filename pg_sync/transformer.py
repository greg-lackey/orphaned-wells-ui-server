"""
transformer.py — Pivots an OGRRE attributesList into a flat PostgreSQL row dict
plus child-table row lists, using the YAML field mapping configuration.

Key behaviours:
  - Scalar fields: first-occurrence-wins (the mapping targets a single pg column)
  - Child (Table-type) fields: subattributes → list of child row dicts
  - Interval fields: "NNNN-MMMM" strings are parsed into _from and _to float columns
  - sidetrack_id: derived from api_number by appending '00'
"""
import logging
import re
from typing import Any, Optional

log = logging.getLogger(__name__)

# Regex to parse interval strings like "4000-5000", "4,000 - 5,000 ft"
_INTERVAL_RE = re.compile(
    r"(?P<from>[\d,]+(?:\.\d+)?)\s*[-–to]+\s*(?P<to>[\d,]+(?:\.\d+)?)"
)


def _parse_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    cleaned = re.sub(r"[^\d.\-]", "", str(value))
    try:
        return float(cleaned)
    except ValueError:
        return None


def _parse_interval(raw: Any) -> tuple[Optional[float], Optional[float]]:
    """
    Attempts to split a string like '4000-5000' into (4000.0, 5000.0).
    Returns (None, None) on failure.
    """
    if raw is None:
        return None, None
    m = _INTERVAL_RE.search(str(raw))
    if not m:
        return None, None
    try:
        from_val = float(m.group("from").replace(",", ""))
        to_val   = float(m.group("to").replace(",", ""))
        return from_val, to_val
    except ValueError:
        return None, None


def _derive_sidetrack_id(api_number: Optional[str]) -> Optional[int]:
    """
    Illinois uses 10-digit API numbers. Append '00' for the sidetrack suffix
    to form the 12-digit sidetrack_id.
    """
    if not api_number:
        return None
    digits = re.sub(r"\D", "", api_number)  # strip dashes, spaces
    if len(digits) == 10:
        digits = digits + "00"
    elif len(digits) == 12:
        pass
    else:
        log.debug("Unexpected API number length (%d digits): %s", len(digits), api_number)
        return None
    try:
        return int(digits)
    except ValueError:
        return None


def transform_record(
    mongo_doc: dict,
    processor_name: str,
    mapping: dict,
) -> tuple[dict, dict[str, list[dict]]]:
    """
    Transforms a single MongoDB record document into a PostgreSQL row dict
    and a dict of child-table rows.

    Args:
        mongo_doc:      Raw MongoDB document (with _id already stringified)
        processor_name: e.g. 'IL_Ver_A_WellCompletion'
        mapping:        Parsed YAML mapping dict (from load_mapping())

    Returns:
        (row, child_rows)
        row:        dict suitable for INSERT into isgs.completion_reports
        child_rows: {child_table_name: [row_dict, ...]}
    """
    proc_mapping    = mapping.get("processors", {}).get(processor_name, {})
    scalar_fields   = proc_mapping.get("scalar_fields", {})
    child_fields    = proc_mapping.get("child_fields", {})    # parent → {sub → pg_col}
    child_tables    = mapping.get("child_tables", {})         # parent → child_table_name
    interval_fields = mapping.get("interval_fields", {})      # compound_key → {from_col, to_col, raw_col}

    api_number = mongo_doc.get("api_number")
    row: dict[str, Any] = {
        "report_name":      mongo_doc.get("name"),
        "api_number":       api_number,
        "sidetrack_id":     _derive_sidetrack_id(api_number),
        "source_processor": processor_name,
    }
    child_rows: dict[str, list[dict]] = {}

    for attr in mongo_doc.get("attributesList", []):
        key:   str       = attr.get("key", "")
        value: Any       = attr.get("value")   # already cleaned by ogrre_data_cleaning
        subattributes    = attr.get("subattributes") or []

        # ------------------------------------------------------------------
        # Child (Table-type) attribute
        # ------------------------------------------------------------------
        if key in child_tables:
            child_table = child_tables[key]
            sub_col_map = child_fields.get(key, {})  # sub_field → pg_col

            if subattributes:
                # Multiple subattributes encode rows in a table
                # Each top-level 'attr' is one occurrence (row); subattributes are its columns
                occ_idx = len(child_rows.get(child_table, []))
                sub_row: dict[str, Any] = {"occurrence_idx": occ_idx}

                for sub in subattributes:
                    sub_key = sub.get("key", "")
                    sub_val = sub.get("value")
                    pg_col  = sub_col_map.get(sub_key)
                    if pg_col:
                        sub_row[pg_col] = sub_val

                    # Handle interval parsing on subattributes
                    compound = f"{key}::{sub_key}"
                    if compound in interval_fields:
                        spec = interval_fields[compound]
                        from_val, to_val = _parse_interval(sub_val)
                        if spec.get("raw_col"):
                            sub_row[spec["raw_col"]] = str(sub_val) if sub_val else None
                        if spec.get("from_col"):
                            sub_row[spec["from_col"]] = from_val
                        if spec.get("to_col"):
                            sub_row[spec["to_col"]] = to_val

                child_rows.setdefault(child_table, []).append(sub_row)
            continue

        # ------------------------------------------------------------------
        # Interval field that stays in the parent row (not a child table)
        # ------------------------------------------------------------------
        if key in interval_fields:
            spec = interval_fields[key]
            raw_col  = spec.get("raw_col")
            from_col = spec.get("from_col")
            to_col   = spec.get("to_col")
            if raw_col and raw_col not in row:
                row[raw_col] = str(value) if value is not None else None
            if from_col or to_col:
                from_val, to_val = _parse_interval(value)
                if from_col and from_col not in row:
                    row[from_col] = from_val
                if to_col and to_col not in row:
                    row[to_col] = to_val
            continue

        # ------------------------------------------------------------------
        # Plain scalar field
        # ------------------------------------------------------------------
        pg_col = scalar_fields.get(key)
        if pg_col and pg_col not in row:  # first-occurrence-wins
            row[pg_col] = value

    return row, child_rows
