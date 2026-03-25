# IA Templatizer 3.1 — Student Programmer Reference

This document covers every function and module in the IA Templatizer codebase. It is intended for student programmers who are maintaining, extending, or debugging the tool. Each entry describes what a function does, what it takes in, what it returns, and how it connects to the rest of the application.

For usage instructions and template format documentation, see the User & Developer Manual.

---

## Quick Module Map

| Module | Role |
|---|---|
| `ia-templatizer.py` | CLI entry point; orchestrates the full pipeline |
| `codebase/template.py` | Load and validate template JSON |
| `codebase/csvutils.py` | Load/write CSV; whitespace normalization; deduplication |
| `codebase/identifier.py` | Generate unique, sanitized IA identifiers |
| `codebase/fields.py` | Repeatable-field detection, mediatype detection, validation helpers |
| `codebase/flatten.py` | Flatten compound objects from MODS-derived CSVs |
| `codebase/mapping.py` | Remap source columns to IA field names; split multi-value cells |
| `codebase/expand_directories.py` | Expand directory paths into per-file output sheets |

---

## `ia-templatizer.py`

This is the main script. It parses CLI arguments, loads the template and input CSV, runs the optional MODS pipeline steps (flatten → remap), runs the main processing loop, and writes the output CSV.

---

### `is_valid_url(url)`

**Description:** Checks whether a string is a well-formed HTTP or HTTPS URL.

**Used in:** `validate_metadata_fields()`

**Inputs:**
- `url` (str) — The string to test.

**Outputs:** `bool` — `True` if the string matches `^https?://[^\s]+$`.

**Why this matters:** URL fields like `inclusive-description-statement` must be real URLs, not plain text. This function uses a regular expression to enforce that. Regular expressions are a powerful tool for format validation — the same pattern can be adapted for email addresses, DOIs, or any other structured string.

---

### `validate_metadata_fields(metadata, context="row")`

**Description:** Issues warnings for any metadata field that contains an invalid URL or value. Does not raise exceptions; uses `warnings.warn()` so that row processing continues.

**Used in:** `main()` — called once on the template defaults, then once per output row.

**Inputs:**
- `metadata` (dict) — A metadata row or the template defaults dict.
- `context` (str) — A label used in warning messages (e.g., `"template"` or `"row"`).

**Outputs:** `None`. Warnings are printed to stderr.

**Fields checked:** `rights-statement` (or `rightsstatement`), `licenseurl`, `inclusive-language-statement`.

**Why this matters:** Centralising validation in one function keeps the main loop clean. By issuing warnings rather than errors, the script can continue processing remaining rows even if one row has a bad value — useful when working with large batches where one bad entry shouldn't block everything.

---

### `main()`

**Description:** Full CLI entry point and pipeline orchestrator.

**How it works (in order):**

1. Parse `sys.argv` to extract `<template_path>`, `<csv_path>`, `<output_path>`, and any option flags/values.
2. Validate all flags; exit with a helpful error message for unrecognised ones.
3. Call `load_template()` → unpack into `(template, embedded_mapping, embedded_options)`.
4. Read `related-url-base` and `related-url-col` from the template defaults (control fields, never in output).
5. Apply `embedded_options` as defaults for any option not explicitly set via CLI.
6. Resolve `column_mapping` (CLI `--mapping` > embedded mapping > `None`).
7. Load the input CSV.
8. If `do_flatten=True`: call `flatten_compound_objects()`.
9. If `column_mapping is not None`: call `apply_mapping()`, then `buckets_to_flat_row()` for each row.
10. **UUID-to-URL injection:** if `related_url_base` is set, iterate over every non-continuation row. Look up the UUID in `related_url_col` (trying the remapped row first, then the raw row). Construct `related_url_base.rstrip('/') + '/' + uuid`. Shift any existing `related[n]` columns up by one index and place the derived URL at `related[0]`. Ensure `related` is listed in `repeatable_fields` so subsequent template-merge logic handles it correctly.
11. Main loop over rows:
   - Strip the internal `_inherited_identifier` marker; set `inherited_id` flag.
   - Expand repeatable fields (template values first, then input values, deduplicated).
   - Fill missing fields from template defaults.
   - Detect mediatype if template uses `"DETECT"`.
   - Remove control fields from the row.
   - For normal rows: call `generate_identifier()`. For continuation rows (`inherited_id=True`): keep the inherited identifier as-is.
12. Determine output column order (see User & Developer Manual).
13. Write output CSV.

**Key variables:**
- `do_flatten` (bool) — whether compound-object flattening is active.
- `column_mapping` (list or None) — the canonical `[(source_col, [ia_fields])]` mapping list.
- `control_fields` (set) — field names that affect behaviour but must never appear in output. Includes `identifier-date`, `identifier-prefix`, `identifier-basename`, `related-url-base`, and `related-url-col`.
- `non_repeatable_fields` (set) — fields that always hold a single value.
- `repeatable_fields` (list) — fields that expand into `field[0]`, `field[1]`, … columns. `related` is added automatically when `related-url-base` is set.
- `related_url_base` (str) — the URL prefix read from `template["related-url-base"]`; empty string when not set.
- `related_url_col` (str) — the source column name for UUIDs; defaults to `"node_uuid"`.
- `EXTRA_FIELD_ORDER` (list) — preferred ordering for "extra" output columns after `subject[n]`.

---

## `codebase/template.py`

---

### `load_template(template_path)`

**Description:** Loads a JSON template file and returns its contents as a 3-tuple.

**Used in:** `main()`

**Inputs:**
- `template_path` (str) — Absolute or relative path to a `.json` file.

**Outputs:** `(template_dict, column_mapping, options_dict)`
- `template_dict` (dict) — Flat metadata defaults (always a plain dict, never nested).
- `column_mapping` (list or None) — Canonical `[(source_col, [ia_fields])]` list, or `None` if no mapping is present.
- `options_dict` (dict) — Runtime option overrides (`flatten`, `images_col`, `delimiter`, etc.), or `{}`.

**Behaviour:**
- Detects combined format via `_is_combined_format()`.
- Flat-format templates: `column_mapping=None`, `options={}`.
- Combined-format templates: parses `"defaults"`, `"mapping"`, and `"options"` sections.
- Always calls `validate_template()` on the defaults dict.

**Raises:** `FileNotFoundError` if the file does not exist.

**Why this matters:** This function is the gateway to the template system. It returns a 3-tuple so that a single combined JSON file can carry all the information previously split across two files (template JSON + mapping CSV). Code that was written for an older version expecting a plain `dict` must be updated to unpack the tuple.

---

### `_is_combined_format(raw)`

**Description:** Returns `True` if the parsed JSON dict uses the combined format (i.e., has a `"defaults"` or `"mapping"` key).

**Inputs:** `raw` (dict) — The fully parsed JSON object.

**Outputs:** `bool`

**Why this matters:** Allows the tool to accept both old flat templates and new combined templates without requiring users to specify which format they're using.

---

### `_parse_mapping_dict(mapping_raw)`

**Description:** Converts a JSON `"mapping"` object to the canonical list-of-tuples form used by `apply_mapping()`.

**Inputs:** `mapping_raw` (dict) — The raw `"mapping"` section from the combined template.

**Outputs:** `list` of `(source_col, [ia_field, ...])` tuples.

**Rules:**
- String values are wrapped in a list.
- List values are used as-is.
- Leading/trailing whitespace is stripped from all field names.

---

### `validate_template(template)`

**Description:** Warns on invalid values in the template defaults. Does not raise exceptions.

**Inputs:** `template` (dict) — The flat defaults dict.

**Checks performed:**
- `"subject"` key must be present and must be a list.
- `"mediatype"` must be one of `movies`, `audio`, `texts`, `software`, `image`, `data`, `DETECT`.
- `"rights-statement"` must be a valid `rightsstatements.org/vocab/` URL.
- `"inclusive-description-statement"` must be a valid HTTP(S) URL.
- `"date"` must match the `YYYY`, `YYYY-MM`, or `YYYY-MM-DD` pattern (with `x` for uncertain digits).
- `"licenseurl"` must be a valid `creativecommons.org` URL.
- `"identifier-date"` must be a valid date string or the string `"TRUE"`.
- `"related-url-base"` must be a valid HTTP(S) URL.
- `"related"` must be a list if present.

---

## `codebase/csvutils.py`

---

### `load_csv(csv_path)`

**Description:** Loads a CSV file into a list of dicts (one dict per row, keys from the header row).

**Inputs:** `csv_path` (str) — Path to the input CSV.

**Outputs:** `list[dict]`

**Why this matters:** Python's `csv.DictReader` is the standard way to read CSV data into dicts. This wrapper keeps the CSV-loading logic in one place so it can be changed (e.g., to add encoding options or BOM handling) without touching the main script.

---

### `write_output_csv(output_path, output_data, fieldnames)`

**Description:** Writes a list of row dicts to a CSV file in the specified column order.

**Inputs:**
- `output_path` (str) — Where to write the output file. The parent directory is created if it does not exist.
- `output_data` (list[dict]) — The processed rows.
- `fieldnames` (list[str]) — Column names, in the desired output order.

**Outputs:** `None` (writes a file).

**Why this matters:** Controlling column order in a CSV requires passing an explicit `fieldnames` list to `csv.DictWriter`. This function abstracts that and handles directory creation, which makes the main script cleaner.

---

### `dedupe_preserve_order(items)`

**Description:** Removes duplicates from a list while preserving the order of first occurrence.

**Inputs:** `items` (list) — Any list.

**Outputs:** `list` — The same items with duplicates removed, original order kept.

**Why this matters:** Python's `set()` removes duplicates but does not preserve order. For subject lists, the order matters — template values should come first, followed by source-specific values. This function achieves deduplication without losing order by using a `seen` set alongside a result list.

---

## `codebase/identifier.py`

---

### `sanitize_filename(filename)`

**Description:** Replaces spaces with underscores and strips all characters that are not alphanumeric, hyphens, or underscores.

**Used in:** `generate_identifier()`

**Inputs:** `filename` (str)

**Outputs:** `str`

**Why this matters:** Internet Archive identifiers must use only `[A-Za-z0-9\-_]`. This function enforces that constraint, which prevents invalid identifiers that would be rejected by the IA API.

---

### `smart_truncate(identifier, max_length=80)`

**Description:** Truncates an identifier to at most `max_length` characters, preferring to cut at a word boundary (`-_-`, `_-_`, `-`, or `_`) rather than in the middle of a token.

**Used in:** `generate_identifier()`

**Inputs:**
- `identifier` (str)
- `max_length` (int) — default 80

**Outputs:** `str`

**Why this matters:** IA identifiers have an 80-character limit. Cutting arbitrarily in the middle of a word looks wrong; cutting at a delimiter produces a cleaner result.

---

### `generate_identifier(row, template, identifier_date, existing_identifiers)`

**Description:** Generates a unique, sanitized IA identifier for a metadata row.

**Used in:** `main()`

**Inputs:**
- `row` (dict) — The current metadata row.
- `template` (dict) — Template defaults (used for `identifier-prefix` and `identifier-basename`).
- `identifier_date` (str) — A date string to embed in the identifier, or `""` for none. If `"TRUE"`, the `date` field from the row is used (if it is a valid date).
- `existing_identifiers` (set) — All identifiers already assigned in this run.

**Outputs:** `str` — The generated identifier (also added to `existing_identifiers`).

**Identifier construction:**
```
{prefix}_{date}_{core}
```
- `prefix` comes from `identifier-prefix` (or `identifier_prefix`) in the template.
- `date` is `identifier_date` (if valid), or the row's `date` value if `identifier_date="TRUE"`.
- `core` is `identifier-basename` (if set), otherwise the sanitized base name of the `file` value, or the sanitized existing `identifier` value, or `"item"`.

**Collision handling:** If the generated identifier already exists in `existing_identifiers`, a timestamp-and-counter suffix is appended (`_{timestamp}-{counter:03d}`).

---

## `codebase/fields.py`

---

### `get_repeatable_fields(template, non_repeatable_fields)`

**Description:** Returns the names of all template fields that are lists and not in `non_repeatable_fields`.

**Used in:** `main()`

**Inputs:**
- `template` (dict)
- `non_repeatable_fields` (set)

**Outputs:** `list[str]`

**Why this matters:** The main loop needs to know which fields to expand into indexed columns. By detecting list fields automatically, `ia-templatizer` can handle any new repeatable field added to a template without code changes — just add it as a list in `"defaults"`. The `related` field is an exception: it is also added to `repeatable_fields` at runtime whenever `related-url-base` is set, even if no `"related"` list appears in the template.

---

### `detect_mediatype(filepath)`

**Description:** Infers the IA media type from a file extension.

**Used in:** `main()` (when template `mediatype` is `"DETECT"`)

**Inputs:** `filepath` (str) — A file path or filename.

**Outputs:** `str` — One of `movies`, `audio`, `texts`, `software`, `image`, or `""` if unknown.

**Extension mappings:**

| Extensions | IA mediatype |
|---|---|
| `mp4`, `mov`, `avi`, `mkv` | `movies` |
| `mp3`, `wav`, `flac`, `aac` | `audio` |
| `pdf`, `epub`, `txt`, `doc`, `docx` | `texts` |
| `zip`, `tar`, `gz`, `rar` | `software` |
| `jpg`, `jpeg`, `png`, `gif`, `bmp`, `tiff` | `image` |

Falls back to `mimetypes.guess_type` for extensions not in the above list.

---

### `normalize_rights_statement_field(fieldname)`

**Description:** Normalises variations of "rights-statement" to the canonical form `"rights-statement"`.

**Used in:** `main()` (applied to every row field name after mapping)

**Inputs:** `fieldname` (str)

**Outputs:** `str`

**Matches:** `"rights-statement"`, `"rightsstatement"`, `"rights_statement"` (case-insensitive comparison after replacing `_` with `-`).

---

### `is_valid_rights_statement(url)`

**Description:** Returns `True` if `url` starts with `http://rightsstatements.org/vocab/` or `https://rightsstatements.org/vocab/`.

**Used in:** `validate_metadata_fields()`, `validate_template()`

---

### `is_valid_licenseurl(url)`

**Description:** Returns `True` if `url` starts with `http://creativecommons.org/` or `https://creativecommons.org/`.

**Used in:** `validate_metadata_fields()`, `validate_template()`

---

## `codebase/flatten.py`

This module handles MODS-derived CSVs that use the CONTENTdm compound-object export format: one item-level row followed by one or more `GraphicalPage` child rows, each containing only an image file path and a sequence number.

---

### `_is_page_row(row, type_col, page_type)`

**Description:** Returns `True` if the row's `type_col` value exactly matches `page_type`.

**Used in:** `flatten_compound_objects()`

**Inputs:**
- `row` (dict)
- `type_col` (str) — column name for the row type (default `"type"`)
- `page_type` (str) — value identifying child page rows (default `"GraphicalPage"`)

---

### `flatten_compound_objects(rows, fieldnames, type_col, page_type, images_col, sequence_col)`

**Description:** Transforms a list of item + child-page rows into a flattened list suitable for the main templatizer pipeline.

**Used in:** `main()`

**Inputs:**
- `rows` (list[dict]) — All rows from the input CSV.
- `fieldnames` (list[str]) — The CSV header (used to construct blank continuation rows).
- `type_col` (str) — Column identifying row type. Default: `"type"`.
- `page_type` (str) — Value that marks a child page row. Default: `"GraphicalPage"`.
- `images_col` (str) — Column containing the image path. Default: `"images"`.
- `sequence_col` (str) — Column containing the page sequence number. Default: `"sequence_id"`.

**Outputs:** `list[dict]` — Flattened rows.

**What it does:**

For each item row, it collects all immediately following `GraphicalPage` rows, sorts them by `sequence_col`, and produces:

1. The item row, with its `images_col` replaced by the first child page's image path.
2. One blank continuation row per remaining child page, containing only the image path.

Orphaned `GraphicalPage` rows (with no preceding item row) are silently dropped. Item rows with no child pages are passed through unchanged.

**Why this matters:** CONTENTdm does not export compound objects as single rows — it exports the compound object header plus one row per child page. Without flattening, every child page would be processed as a separate IA item with empty metadata. After flattening, each compound object becomes one "full" row (the item) plus N-1 blank continuation rows that carry only an image path; the main pipeline then gives all of them the same IA identifier.

---

## `codebase/mapping.py`

This module handles translation from MODS-derived column names to IA field names. It also splits multi-value cells on a configurable delimiter.

---

### `load_column_mapping(source)`

**Description:** Loads a column mapping from any of three source types and returns it in canonical form.

**Used in:** `main()`

**Inputs:**
- `source` — One of:
  - A **file path** (str): CSV with columns `SOURCE_COL`, `IA_FIELD[0]`, optional `IA_FIELD[1]`.
  - A **dict**: A raw JSON mapping object (e.g., from `template.py`).
  - A **list**: Already in canonical form (passed through unchanged).

**Outputs:** `list` of `(source_col, [ia_field, ...])` tuples.

**CSV parsing notes:** Uses `csv.QUOTE_NONE` to avoid errors from unclosed quotes in MODS-exported CSVs. Strips stray quote characters, leading/trailing whitespace, and trailing commas from each cell.

**Why this matters:** The same canonical list format is used regardless of whether the mapping came from a CSV file, a JSON template, or an already-parsed structure. This lets the rest of the code handle all three cases identically.

---

### `_mapping_from_dict(mapping_raw)`

**Description:** Normalises a JSON mapping dict (`{ "source_col": "ia_field" }`) to the canonical list-of-tuples form.

**Inputs:** `mapping_raw` (dict)

**Outputs:** `list` of `(source_col, [ia_field, ...])` tuples.

**Rules:** String values are wrapped in a single-element list; list values are used as-is; other types are coerced to strings.

---

### `_is_image_only(row, images_col)`

**Description:** Returns `True` if every field in the row is blank except (possibly) the `images_col`.

**Used in:** `apply_mapping()` — identifies blank continuation rows produced by `flatten_compound_objects()`.

---

### `apply_mapping(rows, column_mapping, images_col, delimiter, source_fieldnames)`

**Description:** Translates source CSV columns to IA field-name buckets and splits multi-value cells.

**Used in:** `main()`

**Inputs:**
- `rows` (list[dict]) — Input rows (after optional flattening).
- `column_mapping` (list) — Canonical `[(source_col, [ia_fields])]` list.
- `images_col` (str) — Column with image/file paths. Default: `"images"`.
- `delimiter` (str) — Multi-value separator. Default: `"|@|"`.
- `source_fieldnames` (list) — Full list of column names from the input CSV header.

**Outputs:** A list of bucket dicts: `{ ia_field: [value, value, ...] }`.

**Rules:**
- Each source column's value is split on `delimiter`; each part becomes a separate bucket entry.
- Multiple source columns can map to the same IA field — values are merged and deduplicated (order preserved).
- A `!`-prefixed target clears the bucket for that field before adding the new values. This gives this source column priority over earlier sources for the same IA field.
- The `images_col` is always carried through to the `"file"` bucket unless the mapping CSV already maps it explicitly.
- Image-only rows (continuation rows) receive the `last_identifier` from the previous item row and a `"_inherited_identifier": "1"` marker.

**The `!` override in depth:**
```
"mods_origininfo_dateissued": "date"       ← appends ISO timestamp to date bucket
"date_full": "!date"                        ← clears date bucket, then adds human-readable date
```
Because the mapping is processed top-to-bottom, when `date_full` has a value it replaces whatever `mods_origininfo_dateissued` put in the bucket. When `date_full` is empty, the timestamp is used. The `!` prefix is stripped from the field name before it is used as a bucket key.

---

### `buckets_to_flat_row(buckets, non_repeatable_fields)`

**Description:** Converts a bucket dict (`{field: [values]}`) to a flat row dict suitable for the main templatizer loop.

**Used in:** `main()` (after `apply_mapping()`)

**Inputs:**
- `buckets` (dict) — `{ia_field: [value, ...]}` from `apply_mapping()`.
- `non_repeatable_fields` (set) — Field names that hold a single value.

**Outputs:** `dict` — Flat row dict.

**Rules:**
- Fields in `non_repeatable_fields` keep only their first bucket value (a single string).
- All other fields are emitted as indexed columns: `field[0]`, `field[1]`, … — so the main loop's repeatable-field expansion code receives them as already-expanded pre-indexed columns.
- Keys starting with `_` (internal markers like `_inherited_identifier`) are passed through as-is.

**Why this matters:** The main loop expects flat row dicts where repeatable fields are either a single string or pre-indexed `field[n]` columns. `apply_mapping()` produces bucket dicts with lists of values; this function bridges that gap.

---

## `codebase/expand_directories.py`

---

### `write_expanded_csv(output_path, dir_path, template, row)`

**Description:** Lists the contents of `dir_path`, generates one metadata row per file (using the template and the original row as defaults), and writes them to a separate output CSV.

**Used in:** `main()` (when `--expand-directories` is active and a `file` cell contains a directory path)

**Inputs:**
- `output_path` (str) — The main output path; the expanded CSV is named by inserting `_{dir_name}` before the extension.
- `dir_path` (str) — The directory to expand.
- `template` (dict) — Template defaults.
- `row` (dict) — The original row from the input CSV (its metadata is inherited by all expanded rows).

**Outputs:** `bool` — `True` if expansion succeeded, `False` otherwise.

**What it excludes:** Hidden files (starting with `.`), subdirectories, and `Thumbs.db`.

---

## Internal Markers

These keys appear in intermediate data structures during processing. They are always stripped before output.

| Key | Where set | Meaning |
|---|---|---|
| `_inherited_identifier` | `apply_mapping()` | Marks a blank continuation row so `main()` knows to keep its (inherited) identifier rather than generating a new one. |

---

## Data Flow Summary

```
sys.argv
    │
    ├── load_template()           → (defaults, column_mapping, options)
    │       template.py
    │
    ├── read related-url-base / related-url-col from defaults
    │
    ├── [apply embedded options; CLI overrides embedded]
    │
    ├── load input CSV            → raw_rows, raw_fieldnames
    │
    ├── flatten_compound_objects()  [if do_flatten]
    │       flatten.py
    │
    ├── apply_mapping()           [if column_mapping]
    │       mapping.py
    ├── buckets_to_flat_row()     [per row]
    │       mapping.py
    │
    ├── UUID-to-URL injection      [if related_url_base]
    │     for each non-continuation row:
    │       uuid = row[related_url_col] (remapped row, then raw row)
    │       shift existing related[n] up; insert derived URL at related[0]
    │
    ├── main loop (per row)
    │   ├── strip _inherited_identifier
    │   ├── expand repeatable fields   (fields.py: get_repeatable_fields)
    │   ├── fill from template defaults
    │   ├── detect mediatype           (fields.py: detect_mediatype)
    │   ├── validate fields            (ia-templatizer.py: validate_metadata_fields)
    │   ├── strip control fields
    │   └── generate_identifier()      (identifier.py)
    │         [or inherit parent ID for continuation rows]
    │
    └── write_output_csv()        → output CSV
            csvutils.py
```
