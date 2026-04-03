"""
ia-templatizer.py

-------------------------------------------------------------------------------
DESCRIPTION
-------------------------------------------------------------------------------
Main CLI application for applying a metadata template (JSON) to a CSV file for Internet Archive workflows.

This script loads a template and an input CSV, fills missing fields, generates identifiers, expands repeatable fields, validates metadata, and writes a new output CSV suitable for Internet Archive CLI tools and Python library.

-------------------------------------------------------------------------------
USAGE
-------------------------------------------------------------------------------
    python ia-templatizer.py [flags] <template_path> <csv_path> <output_path>

Example:
    python ia-templatizer.py --expand-directories template.json input.csv output.csv

    # MODS compound-object source with column remapping:
    python ia-templatizer.py --flatten --mapping mapping.csv template.json mods.csv output.csv

    # Combined template (mapping + options embedded in the JSON):
    python ia-templatizer.py template.json mods.csv output.csv

    # Combined template with a CLI override:
    python ia-templatizer.py --flatten template.json mods.csv output.csv

-------------------------------------------------------------------------------
DETAILS
-------------------------------------------------------------------------------
- The template JSON may contain control fields and repeatable fields (lists).
- Identifiers are generated using template rules and file names if missing.
- Repeatable fields (lists) are expanded into indexed columns (e.g., subject[0], subject[1]).
- Output CSV columns are ordered for Internet Archive workflows.
- Control fields are not included in the output unless explicitly specified.
- --mapping FILE: remap source columns to IA field names using a mapping CSV
  (columns: SOURCE_COL, IA_FIELD[0], optional IA_FIELD[1]).
- --delimiter STR: multi-value delimiter used in source cells (default "|@|").
- --flatten: flatten compound objects before processing (requires --type-col / --page-type).
- --type-col COL: column identifying row type for flattening (default "type").
- --page-type VAL: type value for child page rows (default "GraphicalPage").
- --images-col COL: column with image file path (default "images").
- --sequence-col COL: column with page sequence number (default "sequence_id").
-------------------------------------------------------------------------------
"""

import sys
import os
import re
import warnings

# Import modules from codebase directory
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "codebase"))
from template import load_template
from csvutils import load_csv, write_output_csv, dedupe_preserve_order
from identifier import generate_identifier
from fields import get_repeatable_fields, detect_mediatype, normalize_rights_statement_field, is_valid_rights_statement, is_valid_licenseurl
from expand_directories import write_expanded_csv
from flatten import flatten_compound_objects
from mapping import load_column_mapping, apply_mapping, buckets_to_flat_row

def is_valid_url(url):
    url_pattern = r'^https?://[^\s]+$'
    return bool(re.match(url_pattern, url))

def validate_metadata_fields(metadata, context="row"):
    rs_val = metadata.get('rights-statement', metadata.get('rightsstatement', ''))
    if rs_val and not is_valid_rights_statement(rs_val):
        warnings.warn(f"Warning: Invalid rights-statement URL '{rs_val}' in {context}")

    lic_val = metadata.get('licenseurl', '')
    if lic_val and not is_valid_licenseurl(lic_val):
        warnings.warn(f"Warning: Invalid licenseurl '{lic_val}' in {context}")

    incl_val = metadata.get('inclusive-language-statement', '')
    if incl_val and not is_valid_url(incl_val):
        warnings.warn(f"Warning: Invalid inclusive-language-statement URL '{incl_val}' in {context}")

def main():
    if len(sys.argv) < 4:
        print("Usage: python ia-templatizer.py [flags] <template_path> <csv_path> <output_path>")
        sys.exit(1)

    template_path = sys.argv[-3]
    csv_path = sys.argv[-2]
    output_path = sys.argv[-1]
    raw_args = sys.argv[1:-3]

    # ── parse named options ──────────────────────────────────────────────────
    mapping_path   = None
    delimiter      = "|@|"
    do_flatten     = False
    type_col       = "type"
    page_type      = "GraphicalPage"
    images_col     = "images"
    file_columns   = None
    sequence_col   = "sequence_id"
    # Default behaviour: when template does not specify an explicit value,
    # preserve parent item rows and drop child page rows (Archipelago-style).
    drop_child_pages = True

    flags = []
    i = 0
    while i < len(raw_args):
        arg = raw_args[i]
        if arg in ('--mapping',):
            i += 1
            if i >= len(raw_args):
                print(f"Error: '{arg}' requires a value.")
                sys.exit(1)
            mapping_path = raw_args[i]
        elif arg in ('--delimiter',):
            i += 1
            if i >= len(raw_args):
                print(f"Error: '{arg}' requires a value.")
                sys.exit(1)
            delimiter = raw_args[i]
        elif arg in ('--type-col',):
            i += 1
            if i >= len(raw_args):
                print(f"Error: '{arg}' requires a value.")
                sys.exit(1)
            type_col = raw_args[i]
        elif arg in ('--page-type',):
            i += 1
            if i >= len(raw_args):
                print(f"Error: '{arg}' requires a value.")
                sys.exit(1)
            page_type = raw_args[i]
        elif arg in ('--images-col',):
            i += 1
            if i >= len(raw_args):
                print(f"Error: '{arg}' requires a value.")
                sys.exit(1)
            images_col = raw_args[i]
        elif arg in ('--file-columns',):
            i += 1
            if i >= len(raw_args):
                print(f"Error: '{arg}' requires a value.")
                sys.exit(1)
            file_columns = [s.strip() for s in raw_args[i].split(',') if s.strip()]
        elif arg in ('--sequence-col',):
            i += 1
            if i >= len(raw_args):
                print(f"Error: '{arg}' requires a value.")
                sys.exit(1)
            sequence_col = raw_args[i]
        elif arg in ('--flatten', '--expand-directories', '-E'):
            if arg == '--flatten':
                do_flatten = True
        elif arg in ('--drop-child-pages',):
            drop_child_pages = True
            flags.append(arg)
        elif arg in ('--keep-child-pages',):
            # CLI flag to explicitly keep/emit child page continuation rows
            # (legacy behaviour). This sets `drop_child_pages` to False.
            drop_child_pages = False
            flags.append(arg)
        else:
            flags.append(arg)
        i += 1

    allowed_flags = {'--expand-directories', '-E', '--flatten', '--drop-child-pages', '--keep-child-pages'}
    for flag in flags:
        if flag not in allowed_flags:
            print(f"Error: Unknown flag '{flag}'")
            print(f"Allowed flags/options: {', '.join(allowed_flags)}, --mapping FILE, "
                  f"--delimiter STR, --type-col COL, --page-type VAL, "
                  f"--images-col COL, --sequence-col COL")
            sys.exit(1)
    expand_dirs = '--expand-directories' in flags or '-E' in flags

    template, embedded_mapping, embedded_options = load_template(template_path)
    validate_metadata_fields(template, context="template")

    # ── related URL derivation config (from template defaults) ───────────────
    related_url_base = template.get('related-url-base', '').strip()
    related_url_col  = (template.get('related-url-col', '') or '').strip() or 'node_uuid'

    # ── apply embedded options as defaults (CLI flags take precedence) ───────
    # Only set from embedded_options when the value hasn't been explicitly
    # supplied on the command line (i.e. it still holds its hard-coded default).
    _cli_set = set()  # track which options were set via CLI
    # (We re-parse raw_args minimally just to know what was explicit)
    _i = 0
    while _i < len(raw_args):
        _a = raw_args[_i]
        if _a in ('--mapping', '--delimiter', '--type-col', '--page-type',
                  '--images-col', '--sequence-col', '--file-columns'):
            _cli_set.add(_a)
            _i += 2
        elif _a in ('--flatten', '--expand-directories', '-E', '--drop-child-pages', '--keep-child-pages'):
            # Flags without a following value
            _cli_set.add(_a)
            _i += 1
        else:
            _i += 1

    if embedded_options:
        if 'delimiter'    not in _cli_set and 'delimiter'    in embedded_options:
            delimiter    = embedded_options['delimiter']
        if 'type_col'     not in _cli_set and 'type_col'     in embedded_options:
            type_col     = embedded_options['type_col']
        if 'page_type'    not in _cli_set and 'page_type'    in embedded_options:
            page_type    = embedded_options['page_type']
        if 'images_col'   not in _cli_set and 'images_col'   in embedded_options:
            images_col   = embedded_options['images_col']
        if 'file_columns' not in _cli_set and 'file_columns' in embedded_options:
            file_columns = embedded_options['file_columns']
        if 'sequence_col' not in _cli_set and 'sequence_col' in embedded_options:
            sequence_col = embedded_options['sequence_col']
        # Respect an explicit drop_child_pages value in the template. CLI
        # flags take precedence; if the user passed either --drop-child-pages
        # or --keep-child-pages it is already recorded in `_cli_set` and we
        # should not override it here.
        if 'drop_child_pages' in embedded_options and ('--drop-child-pages' not in _cli_set and '--keep-child-pages' not in _cli_set):
            drop_child_pages = bool(embedded_options['drop_child_pages'])
        if '--flatten'    not in _cli_set and embedded_options.get('flatten'):
            do_flatten   = True

    # ── resolve mapping: CLI --mapping overrides embedded mapping ────────────
    if mapping_path:
        column_mapping = load_column_mapping(mapping_path)
        _mapping_source = f"'{mapping_path}'"
    elif embedded_mapping is not None:
        column_mapping = embedded_mapping
        _mapping_source = "embedded in template"
    else:
        column_mapping = None
        _mapping_source = None

    # ── load CSV ─────────────────────────────────────────────────────────────
    import csv as _csv
    with open(csv_path, newline="", encoding="utf-8") as fh:
        reader = _csv.DictReader(fh)
        raw_fieldnames = list(reader.fieldnames or [])
        raw_rows = list(reader)
    print(f"Input rows : {len(raw_rows)}")

    # ── step 0a: flatten compound objects (optional) ──────────────────────────
    if do_flatten:
        # Determine final candidate file columns: CLI --file-columns takes
        # precedence, then embedded template 'file_columns', then legacy
        # --images-col / embedded 'images_col'. Normalise to a list which is
        # accepted by flatten and apply_mapping.
        if file_columns:
            final_file_columns = file_columns
        elif isinstance(images_col, list):
            final_file_columns = images_col
        else:
            final_file_columns = [images_col]

        raw_rows = flatten_compound_objects(
            raw_rows, raw_fieldnames,
            type_col=type_col,
            page_type=page_type,
            images_col=final_file_columns,
            sequence_col=sequence_col,
            drop_child_pages=drop_child_pages,
        )
        n_item  = sum(1 for r in raw_rows if r.get(type_col, "").strip())
        n_image = len(raw_rows) - n_item
        print(f"Flattened  : {len(raw_rows)} rows  "
              f"({n_item} item rows + {n_image} image-only rows)")

    # ── step 0b: remap columns (optional) ────────────────────────────────────
    if column_mapping is not None:
        mapped_src_cols = {src for src, _ in column_mapping}
        for src_col in mapped_src_cols:
            if src_col not in raw_fieldnames:
                print(f"  WARNING: mapping references '{src_col}' "
                      f"which is not in the input CSV")
        # Ensure the same final file-columns list is passed to mapping so
        # implicit file mapping and continuation-row detection behave the
        # same way as the flatten step.
        if file_columns:
            final_file_columns = file_columns
        elif isinstance(images_col, list):
            final_file_columns = images_col
        else:
            final_file_columns = [images_col]

        bucket_rows = apply_mapping(
            raw_rows, column_mapping,
            images_col=final_file_columns,
            delimiter=delimiter,
            source_fieldnames=raw_fieldnames,
        )
        # Determine which IA fields are non-repeatable for flat conversion
        _non_rep_for_mapping = {
            "identifier", "file", "mediatype", "color", "date", "licenseurl",
            "rights", "rights-statement", "publisher", "summary",
            "ai-note", "ai-summary", "title", "creator", "volume", "year", "issue"
        }
        csv_data = [
            buckets_to_flat_row(b, _non_rep_for_mapping)
            for b in bucket_rows
        ]
        print(f"Mapped cols: remapped {len(raw_rows)} rows via {_mapping_source}")
    else:
        csv_data = [{
            k: v.strip() if isinstance(v, str) else v
            for k, v in row.items()
        } for row in raw_rows]

    # ── inject UUID-derived related URL at position 0 of each item row ───────
    if related_url_base:
        for data_row, raw_row in zip(csv_data, raw_rows):
            if data_row.get('_inherited_identifier') == '1':
                continue  # skip continuation rows
            uuid_val = (
                data_row.get(related_url_col, '').strip()
                or raw_row.get(related_url_col, '').strip()
            )
            if uuid_val:
                derived_url = related_url_base.rstrip('/') + '/' + uuid_val
                # Shift any existing related[n] up by one slot to insert at [0]
                existing = sorted(
                    [k for k in data_row if re.match(r'^related\[\d+\]$', k)],
                    key=lambda k: int(k.split('[')[1].rstrip(']')),
                    reverse=True,
                )
                for k in existing:
                    n = int(k.split('[')[1].rstrip(']'))
                    data_row[f'related[{n + 1}]'] = data_row.pop(k)
                data_row['related[0]'] = derived_url

    # Control fields used for logic, not output (support both hyphen and underscore)
    control_fields = {
        "identifier-date", "identifier_prefix", "identifier-prefix", "identifier_basename",
        "related-url-base", "related-url-col"
    }

    # Non-repeatable fields (for repeatable field detection)
    non_repeatable_fields = {
        "identifier", "file", "mediatype", "color", "date", "licenseurl", "rights",
        "rights-statement", "publisher", "summary", "ai-note", "ai-summary",
        "title", "volume", "year", "issue"
    }.union(control_fields)

    repeatable_fields = get_repeatable_fields(template, non_repeatable_fields)
    repeatable_field_values = {field: template[field] for field in repeatable_fields}

    # Ensure 'related' is treated as a repeatable field whenever a URL base is
    # configured, even if the template has no static 'related' list.
    if related_url_base and 'related' not in repeatable_fields:
        repeatable_fields.append('related')
        repeatable_field_values['related'] = template.get('related', [])

    output_data = []
    existing_identifiers = set()

    # We'll collect subject[n] and collection[n] columns for final ordering
    def get_repeatable_input(row, field):
        # If subject[n] columns exist, use those values
        n_keys = sorted([k for k in row.keys() if k.startswith(f"{field}[")], key=lambda x: int(x.split("[")[1].split("]")[0]))
        vals = []
        if n_keys:
            for k in n_keys:
                val = row[k]
                if val:
                    vals.append(val.strip() if isinstance(val, str) else val)
            # Remove subject[n] columns from row
            for k in n_keys:
                del row[k]
        else:
            # Otherwise, look for subject/subjects/keywords and split on semicolons
            keys = [k for k in row.keys() if k.lower() == field or k.lower() == field + "s" or (field == "subject" and k.lower() == "keywords")]
            for k in keys:
                val = row[k]
                if val:
                    if isinstance(val, list):
                        vals.extend([v.strip() for v in val if isinstance(v, str) and v.strip()])
                    elif isinstance(val, str):
                        vals.extend([v.strip() for v in val.split(";") if v.strip()])
            # Remove original fields from row
            for k in keys:
                if k in row:
                    del row[k]
        return vals

    for row in csv_data:
        # Normalize field names; strip internal mapping markers
        normalized_row = {}
        inherited_id = False
        for k, v in row.items():
            if k == "_inherited_identifier":
                inherited_id = bool(v)
                continue
            norm_k = normalize_rights_statement_field(k)
            normalized_row[norm_k] = v.strip() if isinstance(v, str) else v
        row = normalized_row

        # Expand all repeatable fields: template values first, then input values, deduped
        for field in repeatable_fields:
            template_vals = repeatable_field_values.get(field, [])
            input_vals = get_repeatable_input(row, field)
            all_vals = dedupe_preserve_order(list(template_vals) + input_vals)
            for i, val in enumerate(all_vals):
                row[f"{field}[{i}]"] = val

        validate_metadata_fields(row, context="row")

        file_val = row.get('file', '')
        # We'll build fieldnames after collecting all output_data

        # Directory expansion logic
        if expand_dirs and file_val and os.path.isdir(file_val):
            try:
                os.listdir(file_val)
                expanded = write_expanded_csv(output_path, file_val, template, row)
                if expanded:
                    continue
            except Exception:
                pass

            # Treat as normal "data" item if expansion failed or directory not listable
            new_row = row.copy()
            new_row['mediatype'] = 'data'
            for field, value in template.items():
                if field == "identifier":
                    continue
                if field in control_fields:
                    continue
                if field not in new_row or not new_row[field]:
                    new_row[field] = value
            # Expand repeatable fields for directory row
            for field in repeatable_fields:
                template_vals = repeatable_field_values.get(field, [])
                input_vals = get_repeatable_input(new_row, field)
                all_vals = dedupe_preserve_order(list(template_vals) + input_vals)
                for i, val in enumerate(all_vals):
                    new_row[f"{field}[{i}]"] = val
            for field in repeatable_fields:
                if field in new_row and isinstance(new_row[field], list):
                    del new_row[field]
            for field in control_fields:
                if field in new_row:
                    del new_row[field]
            identifier_date = template.get('identifier-date', '')
            new_row['identifier'] = generate_identifier(new_row, template, identifier_date, existing_identifiers)
            output_data.append(new_row)
            continue

        # Fill in missing fields from the template
        new_row = row.copy()
        for field, value in template.items():
            if field == "identifier":
                continue
            if field in control_fields:
                continue
            if field not in new_row or not new_row[field]:
                new_row[field] = value

        # Special mediatype detection
        if template.get('mediatype', '').upper() == 'DETECT':
            file_val = new_row.get('file', '')
            detected_type = detect_mediatype(file_val)
            # If file is a directory or unknown type, set mediatype to "data"
            if not detected_type or (file_val and os.path.isdir(file_val)):
                new_row['mediatype'] = 'data'
            else:
                new_row['mediatype'] = detected_type

        # Expand repeatable fields for main output row
        for field in repeatable_fields:
            template_vals = repeatable_field_values.get(field, [])
            input_vals = get_repeatable_input(new_row, field)
            all_vals = dedupe_preserve_order(list(template_vals) + input_vals)
            for i, val in enumerate(all_vals):
                new_row[f"{field}[{i}]"] = val

        # Remove original repeatable fields from output
        for field in repeatable_fields:
            if field in new_row and isinstance(new_row[field], list):
                del new_row[field]

        # Remove control fields from output
        for field in control_fields:
            if field in new_row:
                del new_row[field]

        identifier_date = template.get('identifier-date', '')
        if inherited_id and new_row.get('identifier'):
            # Continuation row: keep the inherited parent identifier as-is
            existing_identifiers.add(new_row['identifier'])
        else:
            new_row['identifier'] = generate_identifier(new_row, template, identifier_date, existing_identifiers)

        output_data.append(new_row)

    # Build fieldnames for output: identifier, file, mediatype, collection[n], title, date, creator, description, subject[n], extras
    all_cols = set().union(*(row.keys() for row in output_data))
    all_cols.discard("_inherited_identifier")
    exclude_subject_keys = {"subject", "subjects", "keywords"}
    exclude_collection_keys = {"collection", "collections"}

    collection_n_cols = sorted(
        [col for col in all_cols if col.startswith("collection[")],
        key=lambda x: int(x.split("[")[1].split("]")[0])
    )
    subject_n_cols = sorted(
        [col for col in all_cols if col.startswith("subject[")],
        key=lambda x: int(x.split("[")[1].split("]")[0])
    )
    # Preferred ordering for non-subject, non-collection extra columns
    EXTRA_FIELD_ORDER = [
        "rights-statement", "rights", "licenseurl",
        "alternative_title", "subtitle",
        "genre", "contributor", "language", "extent",
        "abstract", "notes", "source", "location",
        "publisher", "summary", "color",
        "related",
        "ai-note", "ai-summary",
        "inclusive-description-statement",
    ]
    _extra_anchor = {f: i for i, f in enumerate(EXTRA_FIELD_ORDER)}

    extra_cols_set = {
        col for col in all_cols
        if col not in {
            "identifier", "file", "mediatype", "title", "date", "creator", "description"
        }
        and col not in control_fields
        and col.lower() not in exclude_subject_keys
        and col.lower() not in exclude_collection_keys
        and not col.startswith("subject[")
        and not col.startswith("collection[")
    }
    # Sort: known fields first (by preferred order), then indexed variants of
    # those fields, then remaining fields alphabetically.
    def _extra_sort_key(col):
        base = col.split("[")[0]
        idx  = int(col.split("[")[1].split("]")[0]) if "[" in col else -1
        return (_extra_anchor.get(base, len(EXTRA_FIELD_ORDER)), base, idx)

    extra_cols = sorted(extra_cols_set, key=_extra_sort_key)

    # Insert collection[n] after mediatype, subject[n] after description
    fieldnames = [
        "identifier", "file", "mediatype"
    ] + collection_n_cols + [
        "title", "date", "creator", "description"
    ] + subject_n_cols + extra_cols

    write_output_csv(output_path, output_data, fieldnames)
    print(f"Output written to '{output_path}'")

if __name__ == "__main__":
    main()

# End of ia-templatizer.py