import json
import os
import re
import warnings


def load_template(template_path):
    """
    Load a template JSON file.

    Supports two formats:

    **Flat format** (original) — all keys are IA metadata fields:
        { "mediatype": "image", "subject": [...], ... }

    **Combined format** — wraps defaults, mapping, and options in named sections:
        {
          "defaults": { "mediatype": "texts", "subject": [...], ... },
          "mapping":  { "source_col": "ia_field", ... },
          "options":  { "images_col": "files", "flatten": true, ... }
        }

    Returns a tuple: (template_dict, column_mapping, options_dict)

    - template_dict    : flat metadata defaults (always a plain dict)
    - column_mapping   : list of (source_col, [ia_field, ...]) tuples, or None
    - options_dict     : dict of runtime option overrides, or {}
    """
    if not os.path.exists(template_path):
        raise FileNotFoundError(f"Template file '{template_path}' does not exist.")
    with open(template_path, 'r', encoding='utf-8') as f:
        raw = json.load(f)

    if _is_combined_format(raw):
        template    = raw.get("defaults", {})
        mapping_raw = raw.get("mapping", None)
        options     = raw.get("options", {})
        column_mapping = _parse_mapping_dict(mapping_raw) if mapping_raw is not None else None
    else:
        template       = raw
        column_mapping = None
        options        = {}

    validate_template(template)
    return template, column_mapping, options


def _is_combined_format(raw: dict) -> bool:
    """True when the JSON uses the combined format (has 'defaults' or 'mapping' key)."""
    return "defaults" in raw or "mapping" in raw


def _parse_mapping_dict(mapping_raw: dict) -> list:
    """
    Convert the JSON ``mapping`` section to the canonical
    ``[(source_col, [ia_field, ...])]`` list used by apply_mapping().

    Each entry in the JSON object is one of:
      - "source_col": "ia_field"              → single target
      - "source_col": ["ia_field1", "ia_field2"] → multiple targets

    The ``!`` override prefix is preserved on target field names.
    """
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

def is_valid_date(val):
    if not isinstance(val, str):
        return False
    pattern = r"^\d{2}[0-9x]{2}(-[0-9x]{2}){0,2}$"
    return bool(re.match(pattern, val))

def is_valid_url(url):
    url_pattern = r"^https?://[^\s]+$"
    return isinstance(url, str) and bool(re.match(url_pattern, url))

def validate_template(template):
    if not template:
        return
    if "subject" not in template:
        raise ValueError("Template 'defaults' must contain a 'subject' field.")
    if not isinstance(template["subject"], list):
        raise ValueError("Template 'subject' field must be a list (even if empty).")
    valid_mediatypes = ['movies', 'audio', 'texts', 'software', 'image', 'data', 'DETECT']
    if "mediatype" in template and template["mediatype"] not in valid_mediatypes:
        warnings.warn(f"Invalid mediatype '{template['mediatype']}' in template. Must be one of {valid_mediatypes}.")

    # Validate rights-statement
    if 'rights-statement' in template:
        from fields import is_valid_rights_statement
        if not is_valid_rights_statement(template['rights-statement']):
            warnings.warn(f"Invalid rights statement '{template['rights-statement']}' in template.")

    # Validate inclusive-description-statement
    if 'inclusive-description-statement' in template:
        val = template['inclusive-description-statement']
        if not is_valid_url(val):
            warnings.warn(f"Inclusive description statement must be a valid URL. Got '{val}'.")

    # Validate date format
    if 'date' in template and not is_valid_date(template['date']):
        warnings.warn(f"Invalid date format '{template['date']}' in template. Expected format is YYYY-MM-DD, YYYY-MM, or YYYY, with 'x' allowed for digits.")

    # Validate licenseurl
    if 'licenseurl' in template:
        from fields import is_valid_licenseurl
        if not is_valid_licenseurl(template['licenseurl']):
            warnings.warn(f"Invalid license URL '{template['licenseurl']}' in template.")

    # Validate identifier-date
    if 'identifier-date' in template:
        val = template['identifier-date']
        if not (is_valid_date(val) or (isinstance(val, str) and val.upper() == "TRUE")):
            warnings.warn("identifier-date must be a date in YYYY, YYYY-MM, or YYYY-MM-DD format, or the string 'TRUE'.")

    # Validate related-url-base
    if 'related-url-base' in template:
        val = template['related-url-base']
        if not is_valid_url(val):
            warnings.warn(f"related-url-base must be a valid URL. Got '{val}'.")

    # Validate related field type
    if 'related' in template and not isinstance(template['related'], list):
        warnings.warn("Template 'related' field must be a list if present.")