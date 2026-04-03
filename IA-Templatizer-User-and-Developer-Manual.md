# IA Templatizer 3.1 — User & Developer Manual

## Overview

**IA Templatizer** is a command-line tool for batch-generating metadata CSV files for Internet Archive ingest workflows. It applies a user-defined metadata template (JSON) to an input CSV, filling in missing fields, generating standardized identifiers, expanding repeatable fields, and validating metadata. The output is a CSV formatted for compatibility with the Internet Archive command-line tool and Python library.

The tool supports two usage modes:

- **Standard mode:** Apply a JSON template to a pre-formatted CSV (e.g., a file listing or manually prepared metadata sheet).
- **MODS pipeline mode:** Remap and reformat a MODS-derived CSV (e.g., exported from CONTENTdm) using an embedded or external column-mapping definition, with optional compound-object flattening.

Both modes use the same command and template system. The MODS pipeline is activated by including a `mapping` section in the template or by passing `--mapping` on the command line.

## Features

- **Template-driven metadata:** Fill in missing or default metadata from a JSON template.
- **Combined template format:** Embed column mapping and runtime options directly inside the template JSON for a single-file workflow.
- **MODS column remapping:** Translate MODS-derived CSV column names to IA field names using a mapping definition (embedded in the template or supplied as a separate CSV).
- **Compound object flattening:** Flatten CONTENTdm-style compound objects (item row + child `GraphicalPage` rows) into a sequence of image rows before processing.
- **Multi-value delimiter splitting:** Split cell values containing a configurable delimiter (default `|@|`) into individual repeatable-field values.
- **UUID-to-URL `related` field:** Automatically derive a `related[0]` URL for each item from a UUID column in the source CSV, using a base URL set in the template. Combines with any statically defined `related` list values via the normal repeatable-field merge.
- **Override mapping (`!` prefix):** Mark a mapping target with `!` to give it priority — its values replace any previously collected values for that field, rather than appending.
- **Repeatable fields:** Expand list fields (e.g., `subject`, `collection`) into indexed columns (`subject[0]`, `subject[1]`, etc.), with template values first, then deduplicated input values.
- **Input normalization:** Strips leading/trailing whitespace from all input CSV cell data before processing.
- **Validation:** Checks for valid media types, license URLs, rights statements, and date formats.
- **Custom column ordering:** Output CSV columns are ordered deterministically for Internet Archive workflows.
- **Control fields:** Template control fields (e.g., `identifier-date`, `identifier-prefix`) affect behavior but are not written to the output.
- **Robust error handling:** Clear error messages for missing files, invalid formats, and unsupported values.
- **Directory expansion:** Optionally expand directory paths in the input CSV to generate additional output sheets for their contents.
- **Extensible codebase:** Modular Python scripts for easy customization and extension.

## Usage

### Command Syntax

```
python ia-templatizer.py [options] <template_path> <csv_path> <output_path>
```

| Argument | Description |
|---|---|
| `<template_path>` | Path to your metadata template JSON file (flat or combined format). |
| `<csv_path>` | Path to your input CSV file. |
| `<output_path>` | Where to write the output CSV. |

### Option Flags

| Flag / Option | Argument | Description |
|---|---|---|
| `--expand-directories` / `-E` | — | When a `file` column value is a directory path, generate a separate output CSV for that directory's contents. |
| `--flatten` | — | Flatten compound objects before processing. Requires the input CSV to have a type column distinguishing item rows from child page rows. |
| `--mapping FILE` | CSV path | Load a column-mapping CSV (`SOURCE_COL`, `IA_FIELD[0]`, optional `IA_FIELD[1]`). Overrides any mapping embedded in the template. |
| `--delimiter STR` | string | Multi-value delimiter used in source cells. Default: `\|@\|`. Overrides the `delimiter` option in the template. |
| `--type-col COL` | column name | Column that identifies row type for flattening. Default: `type`. |
| `--page-type VAL` | string | Value in `--type-col` that marks a child page row. Default: `GraphicalPage`. |
| `--images-col COL` | column name | Column containing the image/file path. Default: `images`. |
| `--sequence-col COL` | column name | Column containing the page sequence number used to order child pages. Default: `sequence_id`. |

CLI options always override values embedded in the template `"options"` section.

### Examples

**Standard mode — apply a flat template to a file listing:**
```bash
python ia-templatizer.py templates/sample-template_01.json tests/sample-files-listing.csv tests/list-out.csv
```

**Standard mode with directory expansion:**
```bash
python ia-templatizer.py --expand-directories templates/sample-template_01.json tests/sample-files-listing.csv tests/list-out.csv
```

**MODS pipeline — combined template (mapping and options embedded in JSON):**
```bash
python ia-templatizer.py templates/template_amana.json amana-mods.csv amana-out.csv
```

**MODS pipeline — legacy two-file approach (separate mapping CSV):**
```bash
python ia-templatizer.py --flatten --mapping amana-mapping.csv templates/sample-template_amana.json amana-mods.csv amana-out.csv
```

**MODS pipeline — combined template with a CLI override:**
```bash
python ia-templatizer.py --flatten templates/template_amana.json amana-mods.csv amana-out.csv
```

## Directory Expansion

When `--expand-directories` (or `-E`) is passed:

- If a row in the input CSV has a directory path in its `file` column and the directory exists and is listable:
  - The row is **not** added to the main output CSV.
  - A new output CSV is created, named with `_{last-directory-name}` appended before the extension.
  - Each file in the directory is treated as a new item: a full metadata row is generated for it using the template and the original row metadata.
  - Hidden files, subdirectories, and `Thumbs.db` are excluded.
- If the directory does **not** exist or is not listable:
  - The row is added to the main output CSV as usual, with `mediatype` set to `"data"`.

---

## Template Formats

IA Templatizer supports two template JSON formats.

### Flat Format (legacy)

All keys are IA metadata fields and control fields at the top level. This remains fully supported.

```json
{
  "identifier-prefix": "born-digital",
  "mediatype": "DETECT",
  "collection": ["middleburycollege"],
  "creator": "Middlebury College",
  "rights-statement": "http://rightsstatements.org/vocab/CNE/1.0/",
  "subject": ["Baseball", "Team photos", "Athletes"],
  "inclusive-description-statement": "https://example.edu/language-statement",
  "notes": "Please contact us to report errors."
}
```

### Combined Format (recommended for MODS pipelines)

Introduced in version 3.1. Wraps defaults, column mapping, and runtime options into three named sections. This makes the template self-contained — no separate mapping CSV or CLI flags are required.

```json
{
  "defaults": {
    "mediatype": "texts",
    "collection": ["hamilton"],
    "rights-statement": "http://rightsstatements.org/vocab/NKC/1.0/",
    "subject": ["Hamilton College", "Communal societies"],
    "notes": "Digitized by LITS Digital Collections, Hamilton College"
  },
  "mapping": {
    "mods_identifier_local": "identifier",
    "files": "file",
    "mods_titleinfo_title": "title",
    "mods_origininfo_dateissued": "date",
    "date_full": "!date",
    "mods_subject_topic": "subject",
    "mods_accesscondition_use_and_reproduction": "rights-statement"
  },
  "options": {
    "flatten": false,
    "file_columns": ["files"],
    "delimiter": "|@|"
  }
}
```

The `"defaults"` section is equivalent to the body of a flat-format template. The format is detected automatically; no flag is needed.

### Template Options Reference (`"options"` section)

| Key | Type | Default | Description |
|---|---|---|---|
| `flatten` | boolean | `false` | Flatten compound objects before processing. |
| `images_col` | string | `"images"` | Column containing the image/file path (legacy name; prefer `file_columns`). |
| `file_columns` | array|string | `"images"` | Candidate file-column names (list or comma-separated string). The tool checks candidates in order and uses the first non-empty value. When omitted, the legacy `images_col` (or `images`) is used. |
| `drop_child_pages` | boolean | `true` | When `true` (the default when the template omits an explicit value) child page rows are dropped and only parent item rows are emitted. Set to `false` to use the legacy behaviour that attaches page images to the parent and emits continuation rows. |
| `sequence_col` | string | `"sequence_id"` | Column with page sequence number (used during flattening). |
| `type_col` | string | `"type"` | Column identifying row type (used during flattening). |
| `page_type` | string | `"GraphicalPage"` | Value in `type_col` that marks a child page row. |
| `delimiter` | string | `"\|@\|"` | Multi-value delimiter in source cells. |

CLI options always take precedence over `"options"` values in the template.

### Control Fields

Control fields appear in the `"defaults"` section (or at the top level of a flat template). They affect identifier generation or URL derivation but are **never** written to the output CSV.

| Field | Description |
|---|---|
| `identifier-date` / `identifier_date` | A date string (`YYYY`, `YYYY-MM`, `YYYY-MM-DD`, with `x` for uncertain digits) inserted into generated identifiers. If set to `"TRUE"`, uses the `date` value from each input row. |
| `identifier-prefix` / `identifier_prefix` | Prepended to every generated identifier (e.g., `"hamilton"`). |
| `identifier-basename` / `identifier_basename` | Replaces the file-derived component of the identifier with a fixed string. |
| `related-url-base` | Base URL used to construct a `related[0]` value for each item row. The UUID from `related-url-col` is appended to form the full URL (e.g., `"https://litsdigital.hamilton.edu/do/"`). Must be a valid `https://` or `http://` URL. |
| `related-url-col` | Name of the source column (after mapping) that contains the UUID to append to `related-url-base`. Defaults to `"node_uuid"` when `related-url-base` is set. |

---

## MODS Pipeline

The MODS pipeline handles CSV files exported from CONTENTdm or derived from MODS XML, where column names come from MODS element paths (e.g., `mods_titleinfo_title`) rather than IA field names.

### Column Mapping

A column mapping defines how source CSV columns translate to IA field names. It can be embedded in the template's `"mapping"` section (combined format) or provided as a separate two-column CSV with `--mapping`.

**Mapping CSV format:**
```
SOURCE_COL,IA_FIELD[0],IA_FIELD[1]
mods_titleinfo_title,title
mods_subject_topic,subject
mods_genre_authority_local,genre,subject
```

Each source column maps to one or two IA field names. When two targets are given, the source values are added to both. Multiple source columns may map to the same IA field — their values are merged and deduplicated.

**Mapping JSON format (embedded in template):**
```json
"mapping": {
  "mods_titleinfo_title": "title",
  "mods_subject_topic": "subject",
  "mods_genre_authority_local": ["genre", "subject"]
}
```

### The `!` Override Prefix

By default, when multiple source columns map to the same IA field, their values accumulate. The `!` prefix on a target field name **replaces** any previously collected values for that field rather than appending.

This is used when one source is more authoritative than another. For example:

```json
"mods_origininfo_dateissued": "date",
"date_full": "!date"
```

Here, `mods_origininfo_dateissued` appends its ISO timestamp to the `date` bucket. When `date_full` is reached (and has a value), it **clears** the bucket and replaces the timestamp with the human-readable date value (`1876-03-30` instead of `1876-03-30T00:00:00Z`). The mapping CSV is processed top-to-bottom, so the `!` source must appear **after** the field it is overriding.

### UUID-to-URL `related` Field Derivation

Set `"related-url-base"` in `"defaults"` to automatically generate a `related[0]` URL for each item row:

```json
"defaults": {
  "related-url-base": "https://litsdigital.hamilton.edu/do/",
  ...
}
```

For each non-continuation item row the tool reads the value of `related-url-col` (default: `node_uuid`) from the source data — either from the already-remapped row or from the original raw CSV row — strips trailing slashes from the base URL, appends a `/`, and appends the UUID to form the full URL. The result is placed at `related[0]`.

If the row already contains any `related[n]` values (injected via a mapping entry or carried in from the input), they are renumbered upward (`related[1]`, `related[2]`, …) so the derived URL always occupies `related[0]`.

To use a different UUID column name:

```json
"related-url-base": "https://litsdigital.hamilton.edu/do/",
"related-url-col": "my_uuid_field"
```

To also include static related URLs (e.g., a collection landing page), add a `related` list to `"defaults"`. Those values are merged in as `related[1]`, `related[2]`, etc. after the derived URL:

```json
"related-url-base": "https://litsdigital.hamilton.edu/do/",
"related": ["https://hamilton.edu/communal-societies"]
```

`related-url-base` and `related-url-col` are control fields — they are never written to the output CSV.

Continuation rows (image-only rows produced by compound-object flattening) are skipped during URL derivation; they receive no `related[0]`.

---

### Compound Object Flattening

MODS exports from CONTENTdm represent compound objects as a block of rows: one item-level row followed by N child `GraphicalPage` rows, each with a single image file path. Flattening converts this structure into:

1. The item row receives the first child page's image path (from the first non-empty `file_columns` candidate).
2. Each remaining child page becomes a blank continuation row containing only its image path.

The sequence order of child pages is respected (via `sequence_col`). Continuation rows carry the parent item's identifier so that all pages of a compound object share one IA identifier.

Enable flattening with `--flatten` (CLI) or `"flatten": true` in the template `"options"` section.

---

## Input CSV File Format

A well-formed input CSV must have a header row. The `identifier` column is required unless `file` is present (the script derives an identifier from the file name).

**Standard example:**
```csv
file,title,contributor,notes,date
02baseball/team1.jpg,"Middlebury College Baseball, 2002",,"Team photo",2020-05-01
02baseball/anderson.jpg,"Middlebury College Baseball, 2002: Nate Anderson",Nate Anderson,"Email us!",2020-05-02
```

**MODS-derived example:** Column names are MODS element paths, multi-values are `|@|`-delimited, and compound objects have a `type` column that distinguishes item rows (`CompoundObject`) from child rows (`GraphicalPage`).

### Repeatable Fields in Input

- If the input CSV contains a column named `subject`, `subjects`, or `keywords`, its values are treated as semicolon-delimited entries for the `subject[n]` field.
- If the input CSV contains pre-indexed columns (`subject[0]`, `subject[1]`, etc.), those are used directly.
- The same logic applies to `collection`, `collection[0]`, etc.

---

## Output CSV File Format

The output CSV contains:

- All original columns (except control fields and non-indexed repeatable columns like `subject`, `keywords`, `collection`).
- Any template fields not present in the input, filled with the template's default values.
- Repeatable fields expanded into indexed columns (`subject[0]`, `subject[1]`, …), with template values first, then deduplicated input values.

**Column order:**

1. `identifier`
2. `file`
3. `mediatype`
4. `collection[0]`, `collection[1]`, … (in index order)
5. `title`
6. `date`
7. `creator`
8. `description`
9. `subject[0]`, `subject[1]`, … (in index order)
10. Extra columns, in this preferred order: `rights-statement`, `rights`, `licenseurl`, `alternative_title`, `subtitle`, `genre`, `contributor`, `language`, `extent`, `abstract`, `notes`, `source`, `location`, `publisher`, `summary`, `color`, `related`, `ai-note`, `ai-summary`, `inclusive-description-statement` — then any remaining columns alphabetically.

---

## Best Practices

- Use the **combined template format** for MODS workflows — it keeps mapping, options, and defaults in one place.
- Use the **`!` override prefix** for any field where a more specific source should win (e.g., `date_full` overriding a raw ISO timestamp).
- For uncertain dates, use `x` in place of unknown digits (e.g., `19xx`, `1876-xx`).
- For repeatable fields, always use lists in the `"defaults"` section.
- Validate your template and input CSV before a batch run; check the console output for warnings.
- Keep mapping CSV / template mapping sections in source-column order, with `!` override entries appearing **after** the fields they replace.

---

## Potential Issues & Common Mistakes

- **Wrong date in output:** If a MODS CSV has both a raw ISO timestamp column and a `date_full` column, ensure `date_full` maps to `"!date"` (with the `!` prefix) and appears **after** the timestamp column in the mapping. Without `!`, the timestamp will stay in the output.
- **Compound object pages not in sequence:** Ensure `sequence_col` points to a numeric column in the source CSV. Pages are sorted by that value.
- **Mapping column not found warning:** A `WARNING: mapping references 'col_name' which is not in the input CSV` message means the mapping references a source column that doesn't exist. Check for typos in the mapping or template.
- **Control fields in output:** Control fields (`identifier-date`, `identifier-prefix`, etc.) are never written to output CSVs. If they appear, check that they are in the `"defaults"` section (not a non-control field name).
- **Identifier not generated correctly:** Ensure the template uses `identifier-prefix` (or `identifier_prefix` — both are supported) and that the source CSV has a `file` or pre-existing `identifier` column.
- **Invalid date formats:** Dates must match `YYYY`, `YYYY-MM`, or `YYYY-MM-DD`, with `x` allowed for uncertain digits.
- **Invalid license or rights statement:** Only Creative Commons (`creativecommons.org`) and Rights Statements (`rightsstatements.org/vocab/`) URLs are accepted.
- **File not found:** Script exits with an error if the template or input CSV path does not exist.
- **Repeatable fields not expanded:** List fields must be inside `"defaults"` (combined format) or at the top level (flat format).
- **`creator` indexed as `creator[0]`:** If `creator` is a repeatable field (list) in the mapping output but needs to be a single-value field in IA, add `"creator": ""` to the template `"defaults"` to anchor it as non-repeatable.

---

## Developer Guide

### Codebase Structure

```
ia-templatizer.py          Main CLI — argument parsing, pipeline orchestration, output
codebase/
  template.py              Load and validate template JSON; auto-detect combined vs flat format
  csvutils.py              Load/write CSV; whitespace normalization; deduplication utilities
  identifier.py            Generate unique, sanitized identifiers
  fields.py                Repeatable field detection, mediatype detection, field normalization, validation helpers
  expand_directories.py    Directory expansion logic
  flatten.py               Compound object flattening (MODS pipeline)
  mapping.py               Column remapping and multi-value splitting (MODS pipeline)
templates/
  sample-template_01.json  Flat-format example (standard mode)
  template_amana.json      Combined-format example (MODS pipeline, with flattening)
  template_oneida-american-socialist.json  Combined-format example (MODS pipeline, no flattening)
```

### Module Descriptions

**`template.py`**

`load_template(path)` → `(template_dict, column_mapping, options_dict)`

Returns a 3-tuple. For flat-format templates, `column_mapping` is `None` and `options_dict` is `{}`. For combined-format templates, the `"defaults"` key becomes `template_dict`, `"mapping"` is parsed into the canonical `[(source_col, [ia_fields])]` list, and `"options"` is returned as a plain dict.

`validate_template(template)` runs on the `defaults` dict; warns on invalid `mediatype`, `rights-statement`, `licenseurl`, `inclusive-description-statement`, and `date` values.

---

**`mapping.py`**

`load_column_mapping(source)` accepts a CSV file path (str), a dict (from an already-parsed JSON mapping), or a list (passed through unchanged). Returns the canonical `[(source_col, [ia_fields])]` list.

`apply_mapping(rows, column_mapping, file_columns, delimiter, source_fieldnames)` translates source column names to IA field-name buckets. Multi-value cells are split on `delimiter`. A `!`-prefixed target replaces the bucket contents instead of appending. Image-only continuation rows (all fields blank except the file-column candidate) receive the previous item row's identifier and a `_inherited_identifier` marker.

`buckets_to_flat_row(buckets, non_repeatable_fields)` converts bucket dicts (`{field: [values]}`) to flat row dicts. Non-repeatable fields keep only their first value; repeatable fields are emitted as indexed columns (`field[0]`, `field[1]`, …).

---

**`flatten.py`**

`flatten_compound_objects(rows, fieldnames, type_col, page_type, file_columns, sequence_col)` consumes item + child-page row blocks and emits: the item row (with first child's image), then one blank continuation row per additional child page (image path only), in sequence order.

---

**`identifier.py`**

`generate_identifier(row, template, identifier_date, existing_identifiers)` builds an identifier from prefix, optional date, and either a pre-existing `identifier` value, a file basename, or `"item"`. Sanitizes to `[A-Za-z0-9\-_]`, truncates to 80 characters at a word boundary, and appends a timestamp suffix if a collision occurs.

---

**`fields.py`**

Provides `get_repeatable_fields`, `detect_mediatype`, `normalize_rights_statement_field`, `is_valid_rights_statement`, and `is_valid_licenseurl`.

`detect_mediatype` maps file extensions to IA media types: `mp4/mov/avi/mkv` → `movies`; `mp3/wav/flac/aac` → `audio`; `pdf/epub/txt/doc/docx` → `texts`; `zip/tar/gz/rar` → `software`; `jpg/jpeg/png/gif/bmp/tiff` → `image`. Falls back to `mimetypes.guess_type`.

`DETECT` as the template `mediatype` value triggers automatic detection per row.

---

### Processing Pipeline (data flow)

```
CLI args parsed
  │
  ├─ load_template()  →  (defaults, column_mapping, options)
  │
  ├─ embedded options applied (CLI overrides embedded values)
  │
  ├─ column_mapping resolved (CLI --mapping > embedded > None)
  │
  ├─ input CSV loaded
  │
  ├─ [optional] flatten_compound_objects()        ← if do_flatten
  │
  ├─ [optional] apply_mapping()                   ← if column_mapping
  │             buckets_to_flat_row()
  │
  └─ main processing loop (per row):
       normalize field names
       expand repeatable fields (template values first)
       fill missing fields from template
       detect mediatype (if DETECT)
       strip control fields
       generate_identifier()  (or inherit parent ID for continuation rows)
       → output_data

  write_output_csv()
```

### Adding New Functionality

**New control fields:**
1. Add the field name to the `control_fields` set in `ia-templatizer.py` (and `expand_directories.py` if used there).
2. Implement the logic in the relevant module.
3. Confirm the field is excluded from output rows and headers.

**New validation rules:**
1. Implement the check in `fields.py` or a new module.
2. Call it from `validate_metadata_fields()` in `ia-templatizer.py`.

**New repeatable fields:**
1. Add the field as a list in the template `"defaults"`.
2. `get_repeatable_fields()` in `fields.py` will pick it up automatically.

**New MODS source columns:**
1. Add entries to the template `"mapping"` section (combined format) or to the mapping CSV.
2. Use the `!` prefix on the target if the new source should take priority.

**New non-repeatable mapping fields** (fields that should not become `field[0]` columns):
- Add the field name to `_non_rep_for_mapping` in `ia-templatizer.py`.

**Change output column order:**
1. Update the `EXTRA_FIELD_ORDER` list in `ia-templatizer.py` (the list after the `subject[n]` block).

### Best Practices for Developers

- `load_template()` always returns a 3-tuple; code that previously expected a plain `dict` must be updated to unpack the tuple.
- Keep `_inherited_identifier` internal — strip it before processing and never write it to output.
- The `!` override mechanism depends on mapping order (CSV rows are processed top-to-bottom); document ordering requirements in new mapping files.
- Always exclude control fields from output rows and headers.
- Test new templates with at least one compound-object dataset and one flat dataset to confirm both code paths work.

---

## Example Workflows

### 1. Standard metadata batch (file listing)

```bash
python ia-templatizer.py templates/sample-template_01.json tests/sample-files-listing.csv tests/list-out.csv
```

### 2. Standard metadata batch with directory expansion

```bash
python ia-templatizer.py --expand-directories templates/sample-template_01.json tests/sample-files-listing.csv tests/list-out.csv
```

### 3. MODS pipeline — compound-object images (Amana Society)

The `templates/template_amana.json` combined template embeds the mapping and `"flatten": true`:

```bash
python ia-templatizer.py templates/template_amana.json amana-mods.csv amana-out.csv
```

### 4. MODS pipeline — newspaper issues, no compound objects (Oneida American Socialist)

```bash
python ia-templatizer.py templates/template_oneida-american-socialist.json MODS_Oneida_American_Socialist_ZIPs.csv oneida-out.csv
```

### 5. MODS pipeline — legacy two-file approach

Useful when you want to reuse a flat template with a separate mapping CSV, or override only the mapping:

```bash
python ia-templatizer.py \
  --flatten \
  --mapping amana-mapping.csv \
  templates/sample-template_amana.json \
  amana-mods.csv \
  amana-out.csv
```

### 6. Adapting the pipeline to a new MODS collection

1. Copy `templates/template_amana.json` or `templates/template_oneida-american-socialist.json` as a starting point.
2. Update `"defaults"` with the new collection's base subjects, rights statement, and mediatype.
3. Update `"mapping"` to match the column names in the new MODS CSV (check the CSV header row).
4. Set `"options"` appropriately (`"flatten": true/false`, `"file_columns"`, etc.).
5. Run a test:
   ```bash
   python ia-templatizer.py templates/template_NEW.json SOURCE_MODS.csv test-out.csv
   ```
6. Inspect `test-out.csv` for correct field values, identifier format, and subject list.

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `FileNotFoundError` on template or input | Path is wrong or relative to wrong directory | Use an absolute path or verify `cwd`. |
| `Template 'defaults' must contain a 'subject' field` | `"subject"` key missing from template | Add `"subject": []` (empty list is fine). |
| `Error: Unknown flag '...'` | Unrecognised CLI argument | Check the Option Flags table; note that `--mapping` and `--delimiter` require a value argument. |
| `WARNING: mapping references 'col' which is not in the input CSV` | Source column name typo in mapping | Compare mapping key spelling with the CSV header row exactly. |
| Raw ISO timestamp in `date` output | `date_full` not overriding timestamp | Ensure `date_full` maps to `"!date"` and appears **after** the timestamp-source row in the mapping. |
| Pages out of order in compound object output | `sequence_col` doesn't match actual column name | Pass `--sequence-col ACTUAL_COL` or update `"sequence_col"` in `"options"`. |
| `creator[0]` in output instead of `creator` | `creator` is being treated as repeatable | Add `"creator": ""` to `"defaults"` or add `"creator"` to `_non_rep_for_mapping` in `ia-templatizer.py`. |
| `subject[n]` contains duplicates from template and input | Input CSV also has a subject column with the same values | The deduplication is order-preserving but case-sensitive; ensure values match exactly. |
| Output CSV is empty | All rows were expanded via `--expand-directories` | Check whether the `file` values are directory paths; expansion rows go to separate output files. |
| `related[0]` not in output | `related-url-base` not set, or UUID column is empty/missing | Confirm `"related-url-base"` is in `"defaults"` and the source CSV has a non-empty `node_uuid` column (or set `"related-url-col"` to the correct column name). |
| `related[0]` URL is wrong | `related-url-col` points to the wrong column | Set `"related-url-col"` in `"defaults"` to the exact column name (after any remapping) that holds the UUID. |

---

## Dependencies

IA Templatizer requires only Python 3.7+ and standard library modules:

- `os`, `sys`, `csv`, `re`, `json`, `warnings`, `time`, `collections`, `mimetypes`

No third-party packages are required.

### Optional Tools (development and testing)

- **Visual Studio Code** or any Python-aware IDE
- **pytest** for unit testing
- **Git** for version control
- **pandoc** for converting documentation between formats

### Checking your Python version

```bash
python3 --version
```

If you need to install Python, visit [python.org/downloads](https://www.python.org/downloads/).
