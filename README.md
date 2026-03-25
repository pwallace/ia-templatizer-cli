# IA Templatizer — Usage Guide

**IA Templatizer** is a command-line Python tool for batch-generating metadata CSV files for Internet Archive ingest. It applies a JSON template to an input CSV, fills in default values, generates standardized identifiers, expands repeatable fields, and validates metadata. The output is a correctly formatted CSV for use with the Internet Archive CLI or Python library.

> **Full documentation:** see `IA-Templatizer-User-and-Developer-Manual.md` and `Student-Programmer-Reference.md`

---

## Requirements

- Python 3.7 or newer (standard library only — no third-party packages required)

---

## Command Syntax

```
python ia-templatizer.py [options] <template.json> <input.csv> <output.csv>
```

### Options

| Option | Argument | Description |
|---|---|---|
| `--expand-directories` / `-E` | — | Expand directory paths in `file` column into per-file output sheets |
| `--flatten` | — | Flatten compound objects (item row + child page rows) before processing |
| `--mapping FILE` | CSV path | Load a column-mapping CSV; overrides any mapping embedded in the template |
| `--delimiter STR` | string | Multi-value delimiter in source cells (default: `\|@\|`) |
| `--type-col COL` | column name | Column identifying row type for flattening (default: `type`) |
| `--page-type VAL` | string | Value marking a child page row (default: `GraphicalPage`) |
| `--images-col COL` | column name | Column containing the image/file path (default: `images`) |
| `--sequence-col COL` | column name | Column with page sequence number (default: `sequence_id`) |

CLI options always override values embedded in the template's `"options"` section.

---

## Template Formats

### Flat format (standard mode)

All metadata fields and control fields at the top level. Best for file listings and manually prepared CSVs.

```json
{
  "identifier-prefix": "hamilton",
  "mediatype": "image",
  "collection": ["hamilton"],
  "creator": "Hamilton College",
  "rights-statement": "http://rightsstatements.org/vocab/NKC/1.0/",
  "subject": ["Hamilton College", "Photographs"],
  "notes": "Digitized by LITS Digital Collections, Hamilton College"
}
```

### Combined format (MODS pipeline)

Introduced in v3.1. Wraps defaults, column mapping, and runtime options in three named sections. No separate mapping CSV or CLI flags needed.

```json
{
  "defaults": { ... },
  "mapping": { "source_col": "ia_field", ... },
  "options": { "flatten": false, "images_col": "files", "delimiter": "|@|" }
}
```

The format is detected automatically.

### Control fields (never written to output)

| Field | Effect |
|---|---|
| `identifier-prefix` | Prepended to every generated identifier |
| `identifier-date` | Date string embedded in identifier; `"TRUE"` uses each row's `date` value |
| `identifier-basename` | Fixed string replacing the file-derived identifier component |
| `related-url-base` | Base URL prepended to each row's UUID value to generate `related[0]` (e.g. `"https://litsdigital.hamilton.edu/do/"`) |
| `related-url-col` | Source column name holding the UUID; defaults to `node_uuid` when `related-url-base` is set |

### Repeatable fields

Any template field whose value is a **list** becomes repeatable — the tool expands it into indexed output columns (`subject[0]`, `subject[1]`, …). Template values come first, followed by deduplicated values from the source CSV. This applies to `subject`, `collection`, `source`, `related`, and any other list field in `"defaults"`.

The `related` field is also activated automatically when `related-url-base` is set, even if no static `"related"` list appears in the template.

---

## MODS Pipeline

Use this mode when your source CSV comes from a CONTENTdm/MODS export, where column names are MODS element paths (e.g., `mods_titleinfo_title`) and multi-value cells use a `|@|` delimiter.

### Column mapping

Each entry in `"mapping"` translates a source CSV column to one or two IA field names:

```json
"mapping": {
  "mods_titleinfo_title": "title",
  "mods_subject_topic": "subject",
  "mods_genre_authority_local": ["genre", "subject"]
}
```

Multiple source columns may map to the same IA field — values are merged and deduplicated.

### The `!` override prefix

Prefix a target field with `!` to **replace** any previously collected values for that field rather than appending. Use this when a later, more specific source should win.

```json
"mods_origininfo_dateissued": "date",
"date_full": "!date"
```

`mods_origininfo_dateissued` first puts the raw ISO timestamp (`1876-03-30T00:00:00Z`) into the `date` bucket. When `date_full` is processed, the `!` clears the bucket and replaces it with the human-readable value (`1876-03-30`). The `!` source must appear **after** the field it overrides in the mapping.

### Compound object flattening

MODS exports represent compound objects as one item row followed by N child `GraphicalPage` rows. With `"flatten": true`, the tool:

1. Assigns the first child's image path to the item row.
2. Converts remaining children into blank continuation rows (image path only).

All pages of a compound object share the same IA identifier.

---

## Worked Example: American Socialist Newspapers

The *American Socialist* (1876–1879) is a weekly newspaper held at Hamilton College. The source data is a MODS export (`MODS_Oneida_American_Socialist_ZIPs.csv`) where each row is one issue and file paths point to ZIP archives of page images.

### Run the pipeline

```bash
python ia-templatizer.py \
  templates/template_oneida-american-socialist.json \
  MODS_Oneida_American_Socialist_ZIPs.csv \
  american-socialist-out.csv
```

No additional flags are needed — all options are embedded in the template.

### Template: `templates/template_oneida-american-socialist.json`

```json
{
  "defaults": {
    "mediatype": "texts",
    "collection": ["hamilton"],
    "rights-statement": "http://rightsstatements.org/vocab/NKC/1.0/",
    "rights": "For questions ... Hamilton College Special Collections ...",
    "subject": [
      "Hamilton College", "Oneida Community", "Communal societies",
      "Intentionalism", "Utopian socialism", "Socialism",
      "Noyes, John Humphrey, 1811-1886", "Periodicals", "Newspapers"
    ],
    "notes": "Digitized by LITS Digital Collections, Hamilton College",
    "source": [
      "Hamilton College Library Rare Books and Special Collections",
      "Communal Societies Collection",
      "Oneida Community Collection",
      "Folio HX656.O5 A46",
      "Hamilton College Library, Clinton, New York, United States"
    ]
  },
  "mapping": {
    "mods_identifier_local": "identifier",
    "files": "file",
    "mods_titleinfo_title": "title",
    "mods_name_personal_namepart_refined": "creator",
    "mods_personal_name_author": "creator",
    "mods_origininfo_dateissued": "date",
    "date_full": "!date",
    "mods_language_languageterm_text": "language",
    "mods_physicaldescription_extent": "extent",
    "mods_note": "notes",
    "mods_genre_authority_local": "genre",
    "mods_genre_subgenre_authority_local": "genre",
    "mods_subject_geographic": "subject",
    "mods_subject_topic": "subject",
    "mods_subject_family_name": "subject",
    "mods_origininfo_place_placeterm_text": "location",
    "mods_accesscondition_use_and_reproduction": "rights-statement"
  },
  "options": {
    "flatten": false,
    "images_col": "files",
    "delimiter": "|@|"
  }
}
```

**Key design decisions in this template:**

- `"flatten": false` — no compound objects; each row is a single issue
- `"images_col": "files"` — source CSV uses `files` (not the default `images`) for file paths
- `source` is in `defaults` as a fixed list — the MODS shelf-locator columns produce inconsistently split values, so the correct values are hardcoded once here
- `date_full → "!date"` — overrides the raw ISO timestamp from `mods_origininfo_dateissued`
- `creator` is mapped from two source columns (`mods_name_personal_namepart_refined` and `mods_personal_name_author`); values are deduplicated if both are populated


### Sample output row

| Field | Value |
|---|---|
| `identifier` | `american-socialist-1876-03-30` |
| `file` | `american-socialist-1876-03-30.zip` |
| `mediatype` | `texts` |
| `collection[0]` | `hamilton` |
| `title` | `American socialist, vol. 01, no. 01 (March 30, 1876)` |
| `creator` | `Noyes, John Humphrey, 1811-1886` |
| `date` | `1876-03-30` |
| `subject[0]` | `Hamilton College` |
| `subject[6]` | `Noyes, John Humphrey, 1811-1886` |
| `source[0]` | `Hamilton College Library Rare Books and Special Collections` |
| `rights-statement` | `http://rightsstatements.org/vocab/NKC/1.0/` |

---

## Adapting to a New MODS Collection

1. Copy an existing combined template as a starting point.
2. Update `"defaults"` — subjects, rights statement, mediatype, notes, and any fixed `source` values.
3. Update `"mapping"` — check the source CSV header row and replace column names as needed.
4. Set `"options"` — `"flatten": true` only if the CSV has compound objects; set `"images_col"` to match the file-path column name.
5. Test: `python ia-templatizer.py templates/template_NEW.json SOURCE.csv test-out.csv`
6. Review `test-out.csv` — check identifiers, dates, subject list, and source values.

---

## Output Column Order

`identifier` → `file` → `mediatype` → `collection[n]` → `title` → `date` → `creator` → `description` → `subject[n]` → `rights-statement` → `rights` → `genre[n]` → `language[n]` → `extent[n]` → `notes` → `source[n]` → `location[n]` → `related[n]` → *(remaining columns alphabetically)*

---

## Common Issues

| Symptom | Fix |
|---|---|
| Raw ISO timestamp in `date` output | Map the date-full column to `"!date"` and place it **after** the timestamp column in the mapping |
| `creator[0]` instead of `creator` | Add `"creator": ""` to `"defaults"` to anchor it as non-repeatable |
| `source` values split incorrectly from `\|@\|` cells | Move `source` out of `mapping` and into `defaults` as a hardcoded list |
| `WARNING: mapping references 'col'...` | Column name in mapping doesn't match CSV header — check for typos |
| Pages out of order (compound objects) | Verify `"sequence_col"` matches the actual numeric column in the source CSV |
| Identifier not generated | Ensure `file` or `identifier` column is present in source, or set `identifier-prefix` in defaults |
| `related[0]` not in output | Ensure `"related-url-base"` is set in `"defaults"` and the source CSV has a `node_uuid` column (or set `"related-url-col"` to the correct column name) |

---

## Features

- **Template-driven metadata:** Fill in missing or default metadata from a JSON template.
- **Identifier generation:** Automatically create standardized identifiers using template rules and file names.
- **Repeatable fields:** Expand list fields (e.g., `subject`, `collection`) into indexed columns (`subject[0]`, `subject[1]`, etc.), with template values first, then deduplicated input values.
- **Input normalization:** Strips leading/trailing whitespace from all input CSV cell data before processing.
- **Validation:** Checks for valid media types, license URLs, rights statements, and date formats.
- **Custom column ordering:** Output CSV columns are ordered for Internet Archive workflows.
- **Control fields:** Template control fields (e.g., `identifier-date`, `identifier-prefix`) affect behavior but are not included in the output unless explicitly specified.
- **Robust error handling:** Clear error messages for missing files, invalid formats, and unsupported values.
- **Directory expansion:** Optionally expand directory paths in the input CSV to generate additional output sheets for their contents.
- **Extensible codebase:** Modular Python scripts for easy customization and extension.

---

## Usage

### Command

```bash
python ia-templatizer.py [flags] <template_path> <csv_path> <output_path>
```

- `<template_path>`: Path to your metadata template JSON file.
- `<csv_path>`: Path to your input CSV file.
- `<output_path>`: Path for the output CSV file.
- `[flags]`: Optional flags to control program behavior (see below).

### Example

```bash
python ia-templatizer.py --expand-directories templates/sample-template_01.json tests/sample-files-listing.csv tests/list-out.csv
```

### Option Flags

| Flag                   | Description                                                                                   |
|------------------------|-----------------------------------------------------------------------------------------------|
| `--expand-directories` | When a directory path is found in the `file` column, generate an additional output CSV sheet  |
| `-E`                   | Same as `--expand-directories`                                                               |

**Note:** Only the above flags are currently supported. Any other flags will result in an error.

---

## Directory Expansion

When the `--expand-directories` or `-E` flag is used:

- If a row in the input CSV has a directory path in its `file` column and the directory exists and is listable:
  - The row is **not** added to the main output CSV.
  - A new output CSV is created, named with `_{last-directory-name}` appended before the extension.
  - Each file in the directory is treated as a new item: a full metadata row is generated for it using the template and original row, and written to the directory output sheet.
  - Hidden files, subdirectories, and `Thumbs.db` are excluded.
  - After processing the directory, the script continues with the next row in the input CSV.
- If the directory does **not** exist or is not listable:
  - The row is added to the main output CSV as usual, with its `mediatype` set to `"data"`.

---

## Template File Format (JSON)

A well-formed template JSON file contains metadata fields and control fields. Example:

```json
{
  "identifier-prefix": "born-digital",
  "mediatype": "DETECT",
  "collection": ["middleburycollege"],
  "creator": "Middlebury College",
  "rights-statement": "http://rightsstatements.org/vocab/CNE/1.0/",
  "subject": ["Baseball", "Team photos", "Athletes"],
  "inclusive-description-statement": "This collection aims to represent diverse communities and experiences."
}
```

#### Control Fields

- `identifier-date`: If a valid date (YYYY, YYYY-MM, YYYY-MM-DD, or with 'x' for uncertainty), it is inserted in the identifier. If `"TRUE"`, the value from the input CSV's `date` column is used (if valid).
- `identifier-prefix` or `identifier_prefix`: Used to construct identifiers. Hyphen and underscore are both supported.
- `identifier-basename` or `identifier_basename`: Used as the core part of the identifier.
- Repeatable fields (lists) such as `subject`, `collection`, etc., are expanded into indexed columns.
- Control fields are **never** written to output CSVs.

---

## Input CSV File Format

A well-formed input CSV must have a header row. The `identifier` column is required unless `file` is present.

Example:

```csv
file,title,contributor,notes,date
02baseball/team1.jpg,"Middlebury College Baseball, 2002",,"Team photo",2020-05-01
02baseball/anderson.jpg,"Middlebury College Baseball, 2002: Nate Anderson",Nate Anderson,"Do you know something about this photograph? Email us!",2020-05-02
```

### Repeatable Fields in Input

- If the input CSV contains a column named (case-insensitive) `subject`, `subjects`, or `keywords`, its contents are treated as individual semicolon-delimited values for the repeatable field `subject[n]`.
- If the input CSV contains columns named `subject[0]`, `subject[1]`, etc., those are used directly.
- The same logic applies for other repeatable fields (e.g., `collection`, `collection[0]`, etc.).

---

## Output CSV File Format

The output CSV will contain:

- All original columns from the input CSV, except for control fields and non-indexed repeatable fields (e.g., `subject`, `keywords`, `subjects`, `collection`).
- Any fields from the template not present in the input (except control fields).
- Repeatable fields expanded into indexed columns (e.g., `subject[0]`, `subject[1]`), with template values first, then deduplicated input values.
- Columns ordered as follows:
  1. `identifier`
  2. `file`
  3. `mediatype`
  4. All `collection[n]` columns (in order)
  5. `title`
  6. `date`
  7. `creator`
  8. `description`
  9. All `subject[n]` columns (in order)
  10. Any other columns (in no particular order)

Example output:

```csv
identifier,file,mediatype,collection[0],collection[1],title,date,creator,description,subject[0],subject[1],subject[2],rights,notes,rights-statement,inclusive-description-statement
born-digital_middmag_finals-week_2011,a10_middmag_finals-week_2011.mp4,movies,middleburycollege,specialcollection,"Finals Week",2011,"Middlebury College","Description here","Baseball","Team photos","Athletes",...,...,http://rightsstatements.org/vocab/CNE/1.0/,"This collection aims to represent diverse communities and experiences."
```

---

## Best Practices

- **Validate your template and input CSV before running the script.**
- Use clear, consistent field names in your template and CSV.
- For repeatable fields, use lists in the template to ensure proper expansion.
- For uncertain dates, use 'x' in place of unknown digits (e.g., `19xx`).
- Always use supported flags and check error messages for guidance.
- Keep your codebase modular for easier maintenance and extension.

---

## Potential Issues & Common Mistakes

- **Control fields in output:** Control fields (e.g., `identifier-date`, `identifier-prefix`) should never appear in output CSVs. If they do, update your codebase to exclude them.
- **Identifier not generated correctly:** Ensure your template uses either `identifier-prefix` or `identifier_prefix`, and your code supports both.
- **Invalid date formats:** Dates must be in `YYYY`, `YYYY-MM`, or `YYYY-MM-DD` format, with 'x' allowed for uncertainty (e.g., `19xx`).
- **Invalid license or rights statement:** Only current Creative Commons licenses and rightsstatements.org statements are accepted.
- **File not found:** If the input CSV or template file does not exist, the script will exit with an error.
- **Output directory does not exist:** The script will create the output directory if needed.
- **Invalid flags:** If an unsupported flag is provided, the script will exit with an error and display allowed flags.
- **Repeatable fields not expanded:** Ensure repeatable fields are lists in the template.
- **Duplicate values in repeatable fields:** The script automatically deduplicates values for each repeatable field per row.

---

## Developer Guide

### Codebase Structure

- `ia-templatizer.py`: Main CLI script. Handles argument parsing, template and CSV loading, main processing loop, and output writing.
- `codebase/template.py`: Functions for loading and validating template files.
- `codebase/csvutils.py`: Functions for loading and writing CSV files, including whitespace normalization and deduplication utilities.
- `codebase/identifier.py`: Identifier generation logic. Handles control fields, uniqueness, and formatting.
- `codebase/fields.py`: Utility functions for repeatable fields, mediatype detection, and field normalization.
- `codebase/expand_directories.py`: Handles directory expansion logic and writing expanded output sheets.

### Adding New Functionality

- **Add new control fields:**  
  - Update the `control_fields` set in both `ia-templatizer.py` and `expand_directories.py`.
  - Implement logic for the new control field in the relevant module (e.g., identifier generation, field expansion).
  - Ensure new control fields are excluded from output CSVs unless explicitly required.

- **Add new validation rules:**  
  - Implement validation logic in `fields.py` or a new module.
  - Call validation functions from the main script as needed.

- **Add new repeatable fields:**  
  - Add the field to your template as a list.
  - Ensure `get_repeatable_fields` in `fields.py` recognizes it.
  - The main script will automatically expand it into indexed columns.

- **Change output column order:**  
  - Update the output column logic in `ia-templatizer.py` and `expand_directories.py`.

- **Integrate with other tools:**  
  - Add new modules to the `codebase/` directory.
  - Import and use them in the main script as needed.

### Best Practices for Developers

- Keep logic for control fields centralized and consistent.
- Always exclude control fields from output unless explicitly required.
- Use modular functions for validation, identifier generation, and field expansion.
- Document new features and changes in this README and in code comments.
- Test with a variety of templates and input CSVs to ensure robust behavior.

---

## Example Workflow

1. Prepare your template JSON and input CSV.
2. Run the script:

   ```bash
   python ia-templatizer.py --expand-directories templates/sample-template_01.json tests/sample-files-listing.csv tests/list-out.csv
   ```

3. Review the output CSV and any expanded directory sheets for completeness and accuracy.
4. Use the output CSV with Internet Archive CLI tools or other metadata workflows.

---

## Troubleshooting

- **Script fails to run:** Check that all dependencies are installed and the `codebase/` directory is present.
- **Unexpected output:** Verify your template and input CSV for correct field names and formats.
- **Validation errors:** Read the error message for details on which field or value is invalid.
- **Invalid flag error:** Ensure you are only using supported flags (`--expand-directories`, `-E`).
- **Control fields in output:** Update your codebase to exclude control fields from output rows and headers.

---

## Contact & Support

If you have questions about using IA Templatizer for your archival project, or need help with advanced configuration, please submit an issue to the project repository.

---

## Further Customization

IA Templatizer is designed to be modular and extensible. You can add new modules to the `codebase/` directory to support additional metadata standards, custom validation, or integration with other archival tools.

---

## Dependencies

IA Templatizer is written in Python 3 and relies only on standard Python libraries for its core functionality.  
To run the script successfully, you must have:

- **Python 3.7 or newer** installed on your system.
- The following standard Python modules (included with Python):
  - `os`
  - `sys`
  - `csv`
  - `re`
  - `json`
  - `warnings`
  - `time`

No third-party packages are required for basic operation.

### Optional: Development & Testing

For code editing, testing, and debugging, you may find these tools helpful:

- **Visual Studio Code** or another Python-aware IDE
- **pytest** (for unit testing, if you wish to add tests)
- **Git** (for version control)

### Installation

To check your Python version:

```bash
python3 --version
```

If you need to install Python, visit [python.org/downloads](https://www.python.org/downloads/).

---

**Note:**  
If you add new modules or features that require third-party packages, update this section to list those dependencies and provide installation instructions (e.g., using `pip install <package>`).