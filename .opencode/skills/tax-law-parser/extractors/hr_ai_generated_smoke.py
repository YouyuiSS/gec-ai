from __future__ import annotations

from pathlib import Path
import re
from typing import Any

PROFILE_NAME = "hr-ai-generated-smoke"

_REQUIRED_KEYS: list[str] = [
    "field_id",
    "field_name",
    "field_description",
    "note_on_use",
    "data_type",
    "cardinality",
    "invoice_path",
    "credit_note_path",
    "report_path",
    "sample_value",
    "value_set",
    "interpretation",
    "rules",
    "source_pages",
    "min_char_length",
    "max_char_length",
    "min_decimal_precision",
    "max_decimal_precision",
    "extractor_name",
]

_FIELD_ID_RE = re.compile(r"\b(?:HR-)?(?:BG|BT)-\d+(?:\.\d+)?\b")
_BT_ID_RE = re.compile(r"\b(?:HR-)?BT-\d+(?:\.\d+)?\b")
_RULE_ID_RE = re.compile(r"\b(?:HR-)?BR-\d+\b")
_FIELD_HEADING_RE = re.compile(
    r"^\s*(?P<field_id>(?:HR-)?(?:BG|BT)-\d+(?:\.\d+)?)\b\s*(?:[-–—:]?\s*)?(?P<rest>.*)$",
    re.IGNORECASE,
)
_TOC_TRAIL_RE = re.compile(r"\.{3,}\s*\d+\s*$")
_TOC_SPLIT_RE = re.compile(r"\s*\.{3,}\s*\d+\s*$")
_CARDINALITY_RE = re.compile(r"\b([01])\s*\.{2}\s*(1|n|\*|\d+)\b", re.IGNORECASE)
_MIN_CHAR_RE = re.compile(
    r"\b(?:min(?:imum)?\s*(?:char(?:acter)?\s*)?(?:length|len)?)\s*[:=]?\s*(\d+)\b",
    re.IGNORECASE,
)
_MAX_CHAR_RE = re.compile(
    r"\b(?:max(?:imum)?\s*(?:char(?:acter)?\s*)?(?:length|len)?)\s*[:=]?\s*(\d+)\b",
    re.IGNORECASE,
)
_BETWEEN_CHAR_RE = re.compile(
    r"\bbetween\s+(\d+)\s+and\s+(\d+)\s+(?:chars?|characters)\b",
    re.IGNORECASE,
)
_MIN_PRECISION_RE = re.compile(
    r"\b(?:min(?:imum)?\s*)?(?:decimal\s*)?(?:precision|scale|digits?)\s*[:=]?\s*(\d+)\b",
    re.IGNORECASE,
)
_MAX_PRECISION_RE = re.compile(
    r"\b(?:max(?:imum)?\s*)?(?:decimal\s*)?(?:precision|scale|digits?)\s*[:=]?\s*(\d+)\b",
    re.IGNORECASE,
)
_BETWEEN_PRECISION_RE = re.compile(
    r"\bbetween\s+(\d+)\s+and\s+(\d+)\s*(?:decimal\s*)?(?:digits?|places|precision)\b",
    re.IGNORECASE,
)

_HEADER_PATTERNS = [
    ("field_id", re.compile(r"\b(?:field\s*id|business\s*term|term\s*id|id)\b", re.IGNORECASE)),
    ("field_name", re.compile(r"\bfield\s*name\b", re.IGNORECASE)),
    ("field_description", re.compile(r"\b(?:description|definition|meaning)\b", re.IGNORECASE)),
    ("note_on_use", re.compile(r"\bnote(?:\s+on\s+use)?\b", re.IGNORECASE)),
    ("data_type", re.compile(r"\b(?:data\s*type|datatype|type)\b", re.IGNORECASE)),
    ("cardinality", re.compile(r"\bcardinality\b", re.IGNORECASE)),
    ("invoice_path", re.compile(r"\binvoice(?:\s*note)?\s*path\b", re.IGNORECASE)),
    ("credit_note_path", re.compile(r"\bcredit\s*note\s*path\b", re.IGNORECASE)),
    ("report_path", re.compile(r"\breport(?:ing)?\s*path\b", re.IGNORECASE)),
    ("sample_value", re.compile(r"\bsample\s*value\b", re.IGNORECASE)),
    ("value_set", re.compile(r"\b(?:value\s*set|allowed\s*values?)\b", re.IGNORECASE)),
    ("interpretation", re.compile(r"\binterpretation\b", re.IGNORECASE)),
    ("rules", re.compile(r"\b(?:business\s*rule|rules?)\b", re.IGNORECASE)),
]

_KEY_PATTERNS = [
    ("field_name", re.compile(r"^\s*(?:field\s*name|name)\s*:\s*(.+)$", re.IGNORECASE)),
    ("field_description", re.compile(r"^\s*(?:description|definition|meaning)\s*:\s*(.+)$", re.IGNORECASE)),
    ("note_on_use", re.compile(r"^\s*(?:note\s*on\s*use|note)\s*:\s*(.+)$", re.IGNORECASE)),
    ("data_type", re.compile(r"^\s*(?:data\s*type|datatype|type)\s*:\s*(.+)$", re.IGNORECASE)),
    ("cardinality", re.compile(r"^\s*cardinality\s*:\s*(.+)$", re.IGNORECASE)),
    ("invoice_path", re.compile(r"^\s*(?:invoice\s*path|invoice\s*xpath|ubl\s*path)\s*:\s*(.+)$", re.IGNORECASE)),
    ("credit_note_path", re.compile(r"^\s*(?:credit\s*note\s*path|cn\s*path)\s*:\s*(.+)$", re.IGNORECASE)),
    ("report_path", re.compile(r"^\s*(?:report(?:ing)?\s*path|report\s*path)\s*:\s*(.+)$", re.IGNORECASE)),
    ("sample_value", re.compile(r"^\s*(?:sample\s*value|example)\s*:\s*(.+)$", re.IGNORECASE)),
    ("value_set", re.compile(r"^\s*(?:value\s*set|allowed\s*values?)\s*:\s*(.+)$", re.IGNORECASE)),
    ("interpretation", re.compile(r"^\s*interpretation\s*:\s*(.+)$", re.IGNORECASE)),
    ("rules", re.compile(r"^\s*(?:business\s*rule[s]?|rules?)\s*:\s*(.+)$", re.IGNORECASE)),
]

_TABLE_SETTINGS = {
    "vertical_strategy": "lines",
    "horizontal_strategy": "lines",
    "snap_tolerance": 3,
    "join_tolerance": 3,
    "intersection_x_tolerance": 5,
    "intersection_y_tolerance": 5,
    "edge_min_length": 3,
}


def extract(pdf_path: Path) -> list[dict[str, object]]:
    records: dict[str, dict[str, object]] = {}

    import pdfplumber

    with pdfplumber.open(str(pdf_path)) as pdf:
        for page in pdf.pages:
            page_number = int(page.page_number)
            text = page.extract_text() or ""
            _collect_from_tables(page, page_number, records)
            _collect_from_lines(text, page_number, records)

    return _finalize_records(records)


def _collect_from_tables(page: Any, page_number: int, records: dict[str, dict[str, object]]) -> None:
    tables = page.extract_tables(_TABLE_SETTINGS) or []
    for table in tables:
        if not table:
            continue
        rows = [_normalize_row(row) for row in table]
        rows = [row for row in rows if any(cell for cell in row)]
        if len(rows) < 2:
            continue

        header_info = _extract_header_map(rows)
        if header_info is None:
            continue
        header_idx, mapping = header_info

        for row in rows[header_idx + 1 :]:
            combined = " ".join(cell for cell in row if cell)
            if not combined:
                continue

            bt_ids = _extract_bt_ids(combined)
            if not bt_ids:
                continue

            field_id = bt_ids[0]
            if not _is_bt_identifier(field_id):
                continue

            record = _blank_record(field_id)
            record["source_pages"] = {page_number}

            for key, col_idx in mapping.items():
                if col_idx >= len(row):
                    continue
                value = row[col_idx]
                if not value:
                    continue
                _set_field_value(record, key, value)

            _fill_derived_values(record, combined)
            _upsert_record(records, record)


def _extract_header_map(rows: list[list[str]]) -> tuple[int, dict[str, int]] | None:
    for idx, row in enumerate(rows[:6]):
        if not row or _row_is_toc_like(row):
            continue
        mapping: dict[str, int] = {}
        for col, cell in enumerate(row):
            canonical = _canonical_header_key(cell)
            if canonical and canonical not in mapping:
                mapping[canonical] = col
        if "field_id" in mapping and len(mapping) >= 2:
            return idx, mapping
    return None


def _row_is_toc_like(row: list[str]) -> bool:
    for cell in row:
        if _TOC_TRAIL_RE.search(cell or ""):
            return True
    return False


def _canonical_header_key(cell: str) -> str | None:
    if not cell:
        return None
    normalized = cell.lower()
    for key, pattern in _HEADER_PATTERNS:
        if pattern.search(normalized):
            return key
    return None


def _collect_from_lines(text: str, page_number: int, records: dict[str, dict[str, object]]) -> None:
    lines = [_clean_line(line) for line in text.splitlines() if _clean_line(line)]
    if not lines:
        return

    i = 0
    while i < len(lines):
        line = lines[i]
        match = _FIELD_HEADING_RE.match(line)
        if not match:
            i += 1
            continue

        raw_id = _normalize_identifier(match.group("field_id"))
        if not _is_bt_identifier(raw_id):
            i += 1
            continue

        if _is_toc_heading_line(line):
            i += 1
            continue

        block: list[str] = []
        heading_rest = (match.group("rest") or "").strip()
        if heading_rest:
            block.append(heading_rest)

        i += 1
        while i < len(lines):
            nxt = lines[i]
            nxt_match = _FIELD_HEADING_RE.match(nxt)
            if nxt_match and (_is_bt_identifier(_normalize_identifier(nxt_match.group("field_id"))) or _is_group_identifier(_normalize_identifier(nxt_match.group("field_id")))):
                break
            if _is_toc_heading_line(nxt):
                break
            block.append(_clean_line(nxt))
            i += 1

        parsed = _parse_field_block(raw_id, block)
        if parsed["field_id"]:
            parsed["source_pages"] = {page_number}
            _upsert_record(records, parsed)


def _parse_field_block(field_id: str, lines: list[str]) -> dict[str, object]:
    record = _blank_record(field_id)
    free_lines: list[str] = []

    if lines:
        heading_name = _clean_heading_name(lines[0])
        if heading_name:
            _set_field_value(record, "field_name", heading_name)

    for line in lines:
        if not line:
            continue

        line_matched = False
        for key, pattern in _KEY_PATTERNS:
            m = pattern.match(line)
            if m:
                _set_field_value(record, key, m.group(1))
                line_matched = True
                break
        if line_matched:
            continue

        if _CARDINALITY_RE.search(line):
            _set_field_value(record, "cardinality", line)
            continue

        if _is_toc_heading_line(line):
            continue

        free_lines.append(line)

    raw = " ".join(lines)
    _fill_derived_values(record, raw)
    if not record["field_name"]:
        for item in free_lines:
            item = _clean_heading_name(item)
            if item and len(item) <= 150:
                _set_field_value(record, "field_name", item)
                break

    if not record["field_description"]:
        description = _merge_free_lines_for_description(free_lines, str(record["field_name"]))
        if description:
            _set_field_value(record, "field_description", description)

    rules = _extract_rules(raw)
    if rules:
        merged_rules = _unique_preserve_order(list(_to_rules_list(record.get("rules"))) + rules)
        record["rules"] = merged_rules

    return record


def _merge_free_lines_for_description(free_lines: list[str], field_name: str) -> str:
    parts: list[str] = []
    lowered_name = field_name.lower()
    for line in free_lines:
        candidate = _clean_line(line)
        if not candidate or candidate.lower() == lowered_name:
            continue
        if candidate.lower().startswith("bt-") or candidate.lower().startswith("hr-bt-"):
            continue
        if _TOC_TRAIL_RE.search(candidate):
            candidate = _TOC_SPLIT_RE.sub("", candidate)
        if candidate:
            parts.append(candidate)
    return _clean_line(" ".join(parts))


def _fill_derived_values(record: dict[str, object], text: str) -> None:
    text_lower = text.lower()

    if not record["cardinality"]:
        cardinality = _parse_cardinality(text)
        _set_field_value(record, "cardinality", cardinality)

    if record["min_char_length"] == "" and record["max_char_length"] == "":
        min_len, max_len = _parse_char_length_bounds(text)
        if min_len is not None:
            _set_field_value(record, "min_char_length", min_len)
        if max_len is not None:
            _set_field_value(record, "max_char_length", max_len)

    if record["min_decimal_precision"] == "" and record["max_decimal_precision"] == "":
        min_precision, max_precision = _parse_precision_bounds(text)
        if min_precision is not None:
            _set_field_value(record, "min_decimal_precision", min_precision)
        if max_precision is not None:
            _set_field_value(record, "max_decimal_precision", max_precision)

    if record["rules"] is None:
        record["rules"] = []
    rules = _extract_rules(text_lower)
    if rules:
        merged = _unique_preserve_order(list(_to_rules_list(record["rules"])) + rules)
        record["rules"] = merged

    # Keep value_set, interpretation from unstructured text only when we have no explicit label.
    if not record["value_set"]:
        value_set_match = re.search(r"\b(?:allowed\s*values?|value\s*set)\b\s*:\s*([A-Za-z0-9_,\-\s]+)", text, re.IGNORECASE)
        if value_set_match:
            _set_field_value(record, "value_set", value_set_match.group(1))


def _parse_char_length_bounds(text: str) -> tuple[int | None, int | None]:
    between = _BETWEEN_CHAR_RE.search(text)
    if between:
        return _to_int(between.group(1)), _to_int(between.group(2))

    min_len = _to_int(_MIN_CHAR_RE.search(text).group(1)) if _MIN_CHAR_RE.search(text) else None
    max_len = _to_int(_MAX_CHAR_RE.search(text).group(1)) if _MAX_CHAR_RE.search(text) else None
    return min_len, max_len


def _parse_precision_bounds(text: str) -> tuple[int | None, int | None]:
    between = _BETWEEN_PRECISION_RE.search(text)
    if between:
        return _to_int(between.group(1)), _to_int(between.group(2))

    min_prec = _to_int(_MIN_PRECISION_RE.search(text).group(1)) if _MIN_PRECISION_RE.search(text) else None
    max_prec = _to_int(_MAX_PRECISION_RE.search(text).group(1)) if _MAX_PRECISION_RE.search(text) else None
    return min_prec, max_prec


def _parse_cardinality(text: str) -> str:
    m = _CARDINALITY_RE.search(text)
    if not m:
        lower = text.lower()
        if "mandatory" in lower:
            return "1..1"
        if "optional" in lower or "non-mandatory" in lower:
            return "0..1"
        return ""

    first = m.group(1)
    second = m.group(2)
    if second == "*":
        second = "n"
    return f"{first}..{second}"


def _upsert_record(records: dict[str, dict[str, object]], incoming: dict[str, object]) -> None:
    field_id = _normalize_identifier(str(incoming.get("field_id", "")))

    if not _is_bt_identifier(field_id):
        return

    incoming["field_id"] = field_id
    existing = records.get(field_id)
    if existing is None:
        records[field_id] = incoming
        return
    _merge_records(existing, incoming)


def _merge_records(existing: dict[str, object], incoming: dict[str, object]) -> None:
    for key in _REQUIRED_KEYS:
        if key == "rules":
            existing_rules = _to_rules_list(existing.get("rules"))
            merged = _unique_preserve_order(existing_rules + _to_rules_list(incoming.get("rules")))
            existing["rules"] = merged
            continue

        if key == "source_pages":
            pages = set()
            for page in existing.get("source_pages", []) or []:
                if isinstance(page, int):
                    pages.add(page)
            for page in incoming.get("source_pages", []) or []:
                if isinstance(page, int):
                    pages.add(page)
            existing["source_pages"] = pages
            continue

        incoming_value = incoming.get(key, "")
        existing_value = existing.get(key, "")
        if _is_empty_value(existing_value):
            if not _is_empty_value(incoming_value):
                existing[key] = incoming_value
            continue
        if _is_noisy_value(existing_value, key) and not _is_noisy_value(incoming_value, key):
            existing[key] = incoming_value


def _finalize_records(records: dict[str, dict[str, object]]) -> list[dict[str, object]]:
    output: list[dict[str, object]] = []

    for field_id in sorted(records.keys(), key=_field_sort_key):
        rec = records[field_id]
        final = {
            "field_id": _normalize_identifier(str(rec.get("field_id", field_id))),
            "field_name": _clean_heading_name(str(rec.get("field_name", ""))),
            "field_description": _clean_paragraph_text(str(rec.get("field_description", ""))),
            "note_on_use": _clean_paragraph_text(str(rec.get("note_on_use", ""))),
            "data_type": _clean_paragraph_text(str(rec.get("data_type", ""))),
            "cardinality": _clean_paragraph_text(str(rec.get("cardinality", ""))),
            "invoice_path": _clean_report_like_path(str(rec.get("invoice_path", ""))),
            "credit_note_path": _clean_report_like_path(str(rec.get("credit_note_path", ""))),
            "report_path": _clean_report_like_path(str(rec.get("report_path", ""))),
            "sample_value": _clean_paragraph_text(str(rec.get("sample_value", ""))),
            "value_set": _clean_paragraph_text(str(rec.get("value_set", ""))),
            "interpretation": _clean_paragraph_text(str(rec.get("interpretation", ""))),
            "rules": _to_rules_list(rec.get("rules")),
            "source_pages": sorted(_page_values(rec.get("source_pages", []))),
            "min_char_length": rec.get("min_char_length", ""),
            "max_char_length": rec.get("max_char_length", ""),
            "min_decimal_precision": rec.get("min_decimal_precision", ""),
            "max_decimal_precision": rec.get("max_decimal_precision", ""),
            "extractor_name": PROFILE_NAME,
        }

        if not final["field_id"] or not _is_bt_identifier(final["field_id"]):
            continue
        if _is_noisy_value(final["field_name"], "field_name") and not final["field_description"]:
            continue

        # Keep business rule identifiers out of report_path.
        if _RULE_ID_RE.fullmatch(final["report_path"].replace(" ", "").upper()):
            final["report_path"] = ""

        output.append(final)

    return output


def _page_values(value: object) -> set[int]:
    pages: set[int] = set()
    if isinstance(value, set):
        iterable = value
    elif isinstance(value, list):
        iterable = value
    else:
        iterable = []
    for page in iterable:
        if isinstance(page, int):
            pages.add(page)
        elif isinstance(page, str) and page.isdigit():
            pages.add(int(page))
    return pages


def _blank_record(field_id: str) -> dict[str, object]:
    return {
        "field_id": _normalize_identifier(field_id),
        "field_name": "",
        "field_description": "",
        "note_on_use": "",
        "data_type": "",
        "cardinality": "",
        "invoice_path": "",
        "credit_note_path": "",
        "report_path": "",
        "sample_value": "",
        "value_set": "",
        "interpretation": "",
        "rules": [],
        "source_pages": set(),
        "min_char_length": "",
        "max_char_length": "",
        "min_decimal_precision": "",
        "max_decimal_precision": "",
        "extractor_name": PROFILE_NAME,
    }


def _normalize_row(row: list[Any]) -> list[str]:
    return [_clean_line(str(cell) if cell is not None else "") for cell in row]


def _clean_line(value: str) -> str:
    value = value.replace("\u00a0", " ")
    value = re.sub(r"\s+", " ", value).strip()
    return value


def _clean_heading_name(value: str) -> str:
    value = _clean_line(value)
    if not value:
        return ""
    value = _TOC_SPLIT_RE.sub("", value).strip()
    value = value.strip(" .")
    if _is_toc_heading_line(value):
        return ""
    if _TOC_TRAIL_RE.search(value):
        value = _TOC_SPLIT_RE.sub("", value).strip(" .")
    return value


def _clean_paragraph_text(value: str) -> str:
    value = _clean_line(value)
    if not value:
        return ""
    if _TOC_TRAIL_RE.search(value):
        value = _TOC_SPLIT_RE.sub("", value).strip()
    return value


def _extract_bt_ids(text: str) -> list[str]:
    return _unique_preserve_order(_normalize_identifier(m.group(0)) for m in _BT_ID_RE.finditer(text))


def _extract_rules(text: str) -> list[str]:
    return _unique_preserve_order(_normalize_identifier(m.group(0)) for m in _RULE_ID_RE.finditer(text))


def _normalize_identifier(value: str) -> str:
    value = value.strip().upper()
    value = value.replace("—", "-").replace("–", "-")
    value = re.sub(r"\s+", "", value)
    return value


def _is_bt_identifier(value: str) -> bool:
    return bool(_BT_ID_RE.fullmatch(_normalize_identifier(value)))


def _is_group_identifier(value: str) -> bool:
    return bool(re.fullmatch(r"\b(?:HR-)?BG-\d+(?:\.\d+)?\b", _normalize_identifier(value)))


def _is_toc_heading_line(line: str) -> bool:
    match = _FIELD_HEADING_RE.match(line.strip())
    if not match:
        return False

    raw_id = _normalize_identifier(match.group("field_id"))
    if not (_is_bt_identifier(raw_id) or _is_group_identifier(raw_id)):
        return False

    return bool(_TOC_TRAIL_RE.search(line))


def _set_field_value(record: dict[str, object], key: str, value: Any) -> None:
    if key not in record:
        return

    text = _clean_line(str(value))
    if not text:
        return

    if key == "rules":
        rules = _extract_rules(text)
        if rules:
            existing = _to_rules_list(record.get("rules"))
            record["rules"] = _unique_preserve_order(existing + rules)
        return

    if _is_noisy_value(text, key):
        return

    if key == "field_id":
        normalized = _normalize_identifier(text)
        if _is_bt_identifier(normalized):
            record[key] = normalized
        return

    if key in {"invoice_path", "credit_note_path", "report_path"}:
        text = _clean_report_like_path(text)
        if not text:
            return

    if key == "cardinality":
        text = _parse_cardinality(text)

    if key in {"min_char_length", "max_char_length", "min_decimal_precision", "max_decimal_precision"}:
        as_int = _to_int(text)
        if as_int is not None:
            record[key] = as_int
        return

    if key == "field_name":
        text = _clean_heading_name(text)
    elif key in {"field_description", "note_on_use", "interpretation", "sample_value", "value_set", "data_type"}:
        text = _clean_paragraph_text(text)

    if key not in {"invoice_path", "credit_note_path", "report_path"} and isinstance(record.get(key), str) and record.get(key):
        return

    record[key] = text


def _clean_report_like_path(value: str) -> str:
    value = _clean_line(value)
    if not value:
        return ""

    # Ignore obvious non-path identifiers.
    normalized = _normalize_identifier(value)
    if _RULE_ID_RE.fullmatch(normalized):
        return ""
    if _FIELD_ID_RE.fullmatch(normalized):
        return ""
    if normalized.startswith("BR-") or normalized.startswith("HR-BR-"):
        return ""

    # Keep only first compact token in cases where OCR/table extraction concatenates extra text.
    token = value.split()[0].strip().strip(";,:")
    if token.count("/") == 0:
        return ""
    if token.startswith("/"):
        return token
    # Accept namespace-like report paths only if they still indicate a path.
    if token.lower().startswith(("cbc:", "cac:", "ext:", "qdt:")):
        return ""
    return token


def _is_empty_value(value: object) -> bool:
    if value is None:
        return True
    if value == "" or value == [] or value == {} or value == set():
        return True
    if isinstance(value, int):
        return False
    if isinstance(value, str):
        return not value.strip()
    return False


def _is_noisy_value(value: object, key: str = "") -> bool:
    if _is_empty_value(value):
        return True
    if not isinstance(value, str):
        return False
    normalized = _clean_line(value)
    if not normalized:
        return True

    if key in {"field_name", "field_description", "note_on_use", "interpretation", "data_type", "sample_value", "value_set"}:
        if _TOC_TRAIL_RE.search(normalized):
            return True
        if len(normalized) > 300 and normalized.count(".") >= 4:
            return True

    if key in {"invoice_path", "credit_note_path", "report_path"}:
        if _RULE_ID_RE.fullmatch(normalized.upper()):
            return True
        if not ("/" in normalized or ":" in normalized):
            return True

    if key == "field_id":
        return not _is_bt_identifier(normalized)

    return False


def _to_rules_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return _unique_preserve_order([_normalize_identifier(str(item)) for item in value if isinstance(item, str)])
    if isinstance(value, tuple):
        return _unique_preserve_order([_normalize_identifier(str(item)) for item in value if isinstance(item, str)])
    if isinstance(value, str):
        return _extract_rules(value)
    return []


def _to_int(value: str | None) -> int | None:
    if not value:
        return None
    if value.isdigit():
        return int(value)
    try:
        return int(value)
    except Exception:
        return None


def _unique_preserve_order(values: list[str] | tuple[str, ...] | list[Any]) -> list[str]:
    ordered: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value).strip()
        if not text or text in seen:
            continue
        seen.add(text)
        ordered.append(text)
    return ordered


def _field_sort_key(field_id: str) -> tuple[int, int, int, int, str]:
    m = re.match(r"^(HR-)?(BT)-(\d+)(?:\.(\d+))?$", field_id)
    if not m:
        return (2, 1, 0, 0, field_id)
    is_hr = 0 if m.group(1) == "HR-" else 1
    major = int(m.group(3))
    minor = int(m.group(4) or 0)
    return (is_hr, 0, major, minor, field_id)
