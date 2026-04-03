"""
mapping.py — Remap source CSV columns to IA field names via a mapping CSV.

The mapping CSV has columns: SOURCE_COL, IA_FIELD[0], [IA_FIELD[1]]
(same format as the mapping CSV used by mods_to_ia.py).

Multiple source columns may map to the same IA field; their values are merged
and deduplicated (order preserved).  Cell values containing a multi-value
delimiter (default "|@|") are split into separate values.

apply_mapping() returns a list of dicts where every key is an IA field name
and every value is a list of strings — one entry per unique value -- suitable
for the ia-templatizer repeatable-field logic.
"""

import csv
from collections import defaultdict


def load_column_mapping(source) -> list:
    """
    Return a canonical ``[(source_col, [ia_field, ...])]`` mapping list.

    ``source`` may be:
    - A **file path** (str) to a CSV with columns SOURCE_COL, IA_FIELD[0], [IA_FIELD[1]].
    - A **list** already in canonical form (passed through unchanged).
    - A **dict** from a JSON ``mapping`` section (delegated to
      ``_parse_mapping_dict`` in template.py — but callers can also pass the raw
      dict here and it will be normalised the same way).

    A ``!`` prefix on an IA field name marks it as an **override** target: if
    the source column has a value, it *replaces* anything already collected for
    that field rather than appending.

    CSV parsing uses QUOTE_NONE so malformed/unclosed quotes don't break the
    parser; stray quote characters and trailing commas are stripped.
    """
    if isinstance(source, list):
        return source

    if isinstance(source, dict):
        return _mapping_from_dict(source)

    # File path → parse CSV
    mapping = []
    with open(source, newline="", encoding="utf-8") as fh:
        reader = csv.reader(fh, quoting=csv.QUOTE_NONE, escapechar="\\")
        next(reader)  # skip header
        for row in reader:
            if not row:
                continue
            cleaned = [
                cell.strip().strip('"').strip().rstrip(",").strip()
                for cell in row
            ]
            source_col = cleaned[0]
            if not source_col:
                continue
            ia_fields = [f for f in cleaned[1:] if f]
            if ia_fields:
                mapping.append((source_col, ia_fields))
    return mapping


def _mapping_from_dict(mapping_raw: dict) -> list:
    """Normalise a JSON mapping dict to the canonical list-of-tuples form."""
    result = []
    for source_col, targets in mapping_raw.items():
        if isinstance(targets, str):
            targets = [targets]
        elif not isinstance(targets, list):
            targets = [str(targets)]
        targets = [t.strip() for t in targets if t and t.strip()]
        if targets:
            result.append((source_col, targets))
    return result


def _is_image_only(row: dict, images_col) -> bool:
    """True when every field is blank except (possibly) the images column(s).

    ``images_col`` may be a single column name (str) or an iterable of
    candidate file-column names (list/tuple). A row is considered an
    "image-only"/continuation row when all non-file columns are empty.
    """
    if isinstance(images_col, str):
        file_cols = {images_col}
    else:
        try:
            file_cols = set(images_col)
        except Exception:
            file_cols = {images_col}
    return not any(v.strip() for k, v in row.items() if k not in file_cols)


def apply_mapping(
    rows: list,
    column_mapping: list,
    images_col = "images",
    delimiter: str = "|@|",
    source_fieldnames: list = None,
) -> list:
    """
    Translate source column names to IA field-name buckets and split multi-values.
    Returns a list of dicts: {ia_field_name: [value, value, …]}.

    Rules:
    - A source column may map to 1 or 2 IA fields (both receive all its values).
    - Cell values containing ``delimiter`` are split; each part is a separate value.
    - Values are deduplicated within each IA field bucket (order preserved).
    - Image-only rows (all fields empty except ``images_col``) inherit the
      identifier of the most recently seen item row.
    - The images column is always mapped to "file" regardless of the mapping CSV
      (unless the mapping CSV already maps it explicitly).
    """
    # Build a quick lookup: does the mapping CSV already handle any of the
    # candidate file columns → file? ``images_col`` may be a single name or
    # a list; normalise to a list and check whether at least one candidate is
    # not covered by the mapping CSV. If so, we'll implicitly carry those
    # values into the "file" bucket.
    mapped_cols = {src for src, _ in column_mapping}
    if isinstance(images_col, str):
        images_cols = [images_col]
    else:
        try:
            images_cols = list(images_col)
        except Exception:
            images_cols = [images_col]
    implicit_file_map = any(col not in mapped_cols for col in images_cols)

    remapped = []
    last_identifier = ""

    for row in rows:
        buckets: dict = defaultdict(list)

        for source_col, ia_fields in column_mapping:
            val = row.get(source_col, "").strip()
            if not val:
                continue
            parts = [p.strip() for p in val.split(delimiter) if p.strip()]
            for ia_field in ia_fields:
                override = ia_field.startswith("!")
                field_key = ia_field.lstrip("!") if override else ia_field
                if override:
                    # Replace whatever was collected for this field so far
                    buckets[field_key] = []
                for part in parts:
                    if part not in buckets[field_key]:
                        buckets[field_key].append(part)

        # Always carry any candidate file columns over as "file" if not
        # covered by the mapping CSV. Check each candidate in order and
        # append non-empty values into the buckets['file'] list.
        if implicit_file_map:
            for col in images_cols:
                img_val = row.get(col, "").strip()
                if img_val and img_val not in buckets["file"]:
                    buckets["file"].append(img_val)

        is_continuation = _is_image_only(row, images_cols)
        if is_continuation:
            # Propagate the parent item's identifier to this continuation row.
            if last_identifier and not buckets.get("identifier"):
                buckets["identifier"].append(last_identifier)
            buckets["_inherited_identifier"] = ["1"]
        else:
            if buckets.get("identifier"):
                last_identifier = buckets["identifier"][0]

        remapped.append(dict(buckets))

    return remapped


def buckets_to_flat_row(buckets: dict, non_repeatable_fields: set) -> dict:
    """
    Convert a bucket dict (field → [values]) to a flat string dict suitable
    for ia-templatizer's normal row processing.

    - Fields in ``non_repeatable_fields`` keep only their first value (string).
    - Other (repeatable) fields are joined into a semicolon-separated string
      so that ia-templatizer's existing semicolon splitter picks them up,
      OR are emitted as ``field[0]``, ``field[1]`` … columns directly.

    We choose the indexed-column approach here so the values flow through
    ``get_repeatable_input`` intact (already expanded before template merge).
    """
    flat = {}
    for field, vals in buckets.items():
        if not vals:
            continue
        # Internal control marker — pass through as-is
        if field.startswith("_"):
            flat[field] = vals[0]
            continue
        if field in non_repeatable_fields:
            flat[field] = vals[0]
        else:
            for i, v in enumerate(vals):
                flat[f"{field}[{i}]"] = v
    return flat
