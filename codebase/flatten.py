
"""
flatten.py — Flatten compound objects from a MODS-derived CSV.

A compound object consists of one item-level row followed by N child rows
(identified by a type column matching a page-type value, e.g. "GraphicalPage").
This module moves child images onto the item row (first image) or onto
blank continuation rows (remaining images) in sequence order, and discards
the original child rows.

This module also includes a heuristic to recognise page rows when the input
CSV uses a different type label (for example many exports use "Page"). It
looks for an identifier-like column (e.g. "local_identifier" or
"identifier") that ends with the suffix `_s<digits>` which is a common
pattern for child page rows. This makes flattening robust when the
`page_type` value doesn't match the CSV.
"""

import re


def _is_page_row(row: dict, type_col: str, page_type: str, fieldnames: list = None) -> bool:
    """Return True if the row is a page/child row.

    Detection order:
    1. Exact match of the `type_col` value to `page_type`.
    2. Heuristic match: any column name ending with 'identifier' whose value
       ends with the suffix `_s<digits>` (e.g. `spec-1947-10-06_s001`).
    """
    # 1) explicit type match
    try:
        val = row.get(type_col, "")
    except Exception:
        val = ""
    if isinstance(val, str) and val.strip() == page_type:
        return True

    # 2) identifier-suffix heuristic
    for k, v in row.items():
        if not k or not isinstance(k, str):
            continue
        if k.lower().endswith('identifier') and isinstance(v, str):
            # Match common child-page identifier patterns such as
            # `..._s001`, `..._s004A`, or `..._s004B-humor-slobb` by looking
            # for the `_s<digits>` sequence anywhere in the identifier.
            if re.search(r'_s\d+', v.strip()):
                return True

    return False


def flatten_compound_objects(
    rows: list,
    fieldnames: list,
    type_col: str = "type",
    page_type: str = "GraphicalPage",
    images_col = "images",
    sequence_col: str = "sequence_id",
    drop_child_pages: bool = True,
) -> list:
    """
    Consolidate compound objects:
    - Item row receives the first child page's image path.
    - Remaining child pages become blank rows carrying only their image path,
      inserted immediately after the item row in sequence order.
    - All child page rows are consumed (not passed through as-is).
    - Single-image items and items with no child pages are kept unchanged.
    """
    # Normalise images_col to a list of candidate file columns. The first
    # candidate is treated as the primary column to which page file paths are
    # copied when consolidating pages onto the parent item row.
    if isinstance(images_col, str):
        images_cols = [images_col]
    else:
        try:
            images_cols = list(images_col)
        except Exception:
            images_cols = [images_col]
    primary_col = images_cols[0]

    output = []
    blank = {f: "" for f in fieldnames}

    i = 0
    while i < len(rows):
        row = rows[i]

        if _is_page_row(row, type_col, page_type, fieldnames):
            # Orphaned page row — skip.
            i += 1
            continue

        item = dict(row)
        pages = []
        j = i + 1
        while j < len(rows) and _is_page_row(rows[j], type_col, page_type, fieldnames):
            pages.append(rows[j])
            j += 1

        if pages:
            def _seq(r: dict) -> int:
                try:
                    return int(r.get(sequence_col, 0))
                except (ValueError, TypeError):
                    return 0

            pages.sort(key=_seq)
            # If the caller requests that child page rows be dropped entirely
            # (e.g. for Archipelago-style pipelines), preserve the parent item
            # row as-is and discard the child page rows. Otherwise, attach the
            # first page image to the item and create continuation rows for
            # remaining pages (legacy behaviour).
            if drop_child_pages:
                output.append(item)
            else:
                # Pick the first non-empty file value from the candidate
                # columns on the first page and copy it to the primary column
                # on the parent item. Then create continuation rows for the
                # remaining pages using the same primary column.
                def _first_file_val(r: dict) -> str:
                    for c in images_cols:
                        v = (r.get(c, "") or "").strip()
                        if v:
                            return v
                    return ""

                first_val = _first_file_val(pages[0])
                item[primary_col] = first_val
                output.append(item)
                for page in pages[1:]:
                    extra = dict(blank)
                    extra[primary_col] = _first_file_val(page)
                    output.append(extra)
        else:
            output.append(item)

        i = j

    return output
