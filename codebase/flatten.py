"""
flatten.py — Flatten compound objects from a MODS-derived CSV.

A compound object consists of one item-level row followed by N child rows
(identified by a type column matching a page-type value, e.g. "GraphicalPage").
This module moves child images onto the item row (first image) or onto
blank continuation rows (remaining images) in sequence order, and discards
the original child rows.
"""


def _is_page_row(row: dict, type_col: str, page_type: str) -> bool:
    return row.get(type_col, "").strip() == page_type


def flatten_compound_objects(
    rows: list,
    fieldnames: list,
    type_col: str = "type",
    page_type: str = "GraphicalPage",
    images_col: str = "images",
    sequence_col: str = "sequence_id",
) -> list:
    """
    Consolidate compound objects:
    - Item row receives the first child page's image path.
    - Remaining child pages become blank rows carrying only their image path,
      inserted immediately after the item row in sequence order.
    - All child page rows are consumed (not passed through as-is).
    - Single-image items and items with no child pages are kept unchanged.
    """
    output = []
    blank = {f: "" for f in fieldnames}

    i = 0
    while i < len(rows):
        row = rows[i]

        if _is_page_row(row, type_col, page_type):
            # Orphaned page row — skip.
            i += 1
            continue

        item = dict(row)
        pages = []
        j = i + 1
        while j < len(rows) and _is_page_row(rows[j], type_col, page_type):
            pages.append(rows[j])
            j += 1

        if pages:
            def _seq(r: dict) -> int:
                try:
                    return int(r.get(sequence_col, 0))
                except (ValueError, TypeError):
                    return 0

            pages.sort(key=_seq)
            item[images_col] = pages[0][images_col]
            output.append(item)
            for page in pages[1:]:
                extra = dict(blank)
                extra[images_col] = page[images_col]
                output.append(extra)
        else:
            output.append(item)

        i = j

    return output
