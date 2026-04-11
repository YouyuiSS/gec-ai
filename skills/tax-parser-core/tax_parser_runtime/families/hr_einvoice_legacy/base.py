from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import pdfplumber


FIELD_ID_RE = re.compile(r"^(?:HR-)?BT-\d+$")
HEADING_RE = re.compile(r"^(?:HR-)?(?:BT|BG)-\d+\b")
RULE_RE = re.compile(r"^(?:HR-)?BR(?:-[A-Z]+)?-\d+\b")


def squash_ws(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def clean_path_value(text: str) -> str:
    text = re.sub(r"\s+", "", text)
    text = text.replace("HRFISK20dana", "HRFISK20Data")
    text = text.replace("HRFISK20data", "HRFISK20Data")
    text = text.replace("/invoice/", "/Invoice/")
    text = text.replace("/creditnote/", "/CreditNote/")
    return text


def split_paths(path_text: str) -> tuple[str, str]:
    cleaned = clean_path_value(path_text)
    invoice_match = re.search(r"(/Invoice/.*?)(?=/CreditNote/|$)", cleaned)
    credit_match = re.search(r"(/CreditNote/.*)$", cleaned)
    invoice_path = invoice_match.group(1) if invoice_match else ""
    credit_note_path = credit_match.group(1) if credit_match else ""
    return invoice_path, credit_note_path


def last_path_token(path_text: str) -> tuple[str, str]:
    invoice_path, credit_note_path = split_paths(path_text)
    primary = invoice_path or credit_note_path
    if not primary:
        return "", ""
    attr_match = re.search(r"/@([A-Za-z0-9_:-]+)$", primary)
    if attr_match:
        return primary.split("/")[-2].split(":")[-1], attr_match.group(1)
    return primary.split("/")[-1].split(":")[-1], ""


@dataclass
class FieldRecord:
    field_id: str
    field_name: str = ""
    field_description: str = ""
    note_on_use: str = ""
    data_type: str = ""
    cardinality: str = ""
    invoice_path: str = ""
    credit_note_path: str = ""
    remark: str = ""
    source_pages: list[int] = field(default_factory=list)
    rules: list[str] = field(default_factory=list)
    sample_value: str = ""
    value_set: str = ""
    interpretation: str = ""
    min_char_length: str = ""
    max_char_length: str = ""
    min_decimal_precision: str = ""
    max_decimal_precision: str = ""
    detail_block: str = ""

    @property
    def report_path(self) -> str:
        parts = []
        if self.invoice_path:
            parts.append(f"Invoice: {self.invoice_path}")
        if self.credit_note_path:
            parts.append(f"CreditNote: {self.credit_note_path}")
        return "\n".join(parts)


def extract_hr_legacy_records(pdf_path: Path, *, profile_name: str) -> list[dict[str, object]]:
    fields = extract_tax_field_records(pdf_path)
    rows: list[dict[str, object]] = []
    for field in fields:
        rows.append(
            {
                "field_id": field.field_id,
                "field_name": field.field_name,
                "field_description": field.field_description,
                "note_on_use": field.note_on_use,
                "data_type": field.data_type,
                "cardinality": field.cardinality,
                "invoice_path": field.invoice_path,
                "credit_note_path": field.credit_note_path,
                "report_path": field.report_path,
                "sample_value": field.sample_value,
                "value_set": field.value_set,
                "interpretation": field.interpretation,
                "rules": list(field.rules),
                "source_pages": sorted({int(page) for page in field.source_pages}),
                "min_char_length": field.min_char_length,
                "max_char_length": field.max_char_length,
                "min_decimal_precision": field.min_decimal_precision,
                "max_decimal_precision": field.max_decimal_precision,
                "extractor_name": profile_name,
            }
        )
    return rows


def extract_tax_field_records(spec_pdf: Path) -> list[FieldRecord]:
    fields = extract_table_fields(spec_pdf)
    spec_text = build_text_dump(spec_pdf)
    enrich_fields(fields, spec_text)
    return fields


def normalize_type(data_type: str) -> str:
    data_type = squash_ws(data_type)
    replacements = {
        "At": "Code",
        "Identifier (code)": "Identifier (code)",
        "Unit price": "Unit price amount",
    }
    return replacements.get(data_type, data_type)


def extract_table_fields(pdf_path: Path) -> list[FieldRecord]:
    fields: list[FieldRecord] = []
    current: FieldRecord | None = None

    with pdfplumber.open(pdf_path) as pdf:
        for page_no, page in enumerate(pdf.pages, start=1):
            for table in page.extract_tables():
                if not table:
                    continue
                has_header = any(
                    row
                    and len(row) >= 2
                    and (row[0] or "").strip() == "ID"
                    and (row[1] or "").strip() == "Business term"
                    for row in table[:5]
                )
                if not has_header:
                    continue

                for row in table:
                    row = [(cell or "").strip() for cell in row]
                    if not any(row):
                        continue
                    c0 = row[0] if len(row) > 0 else ""
                    c1 = row[1] if len(row) > 1 else ""
                    c2 = row[2] if len(row) > 2 else ""
                    c3 = row[3] if len(row) > 3 else ""
                    c4 = row[4] if len(row) > 4 else ""
                    c5 = row[5] if len(row) > 5 else ""

                    if c0 == "ID" and c1 == "Business term":
                        continue
                    if c1 in {"UBL Invoice Path", "UBL CreditNote Path (Approval)"}:
                        continue

                    if FIELD_ID_RE.match(c0):
                        current = FieldRecord(
                            field_id=c0,
                            field_name=squash_ws(c1),
                            field_description=squash_ws(c2),
                            note_on_use=squash_ws(c3),
                            data_type=normalize_type(c4),
                            cardinality=squash_ws(c5),
                            source_pages=[page_no],
                        )
                        fields.append(current)
                        continue

                    if current is None:
                        continue

                    current.source_pages.append(page_no)

                    if c1.startswith("/"):
                        invoice_path, credit_note_path = split_paths(c1)
                        if invoice_path:
                            current.invoice_path = invoice_path
                        if credit_note_path:
                            current.credit_note_path = credit_note_path
                        if c5:
                            current.remark = squash_ws(" ".join(filter(None, [current.remark, c5])))
                        continue

                    if c1:
                        current.field_name = squash_ws(" ".join(filter(None, [current.field_name, c1])))
                    if c2:
                        current.field_description = squash_ws(" ".join(filter(None, [current.field_description, c2])))
                    if c3:
                        current.note_on_use = squash_ws(" ".join(filter(None, [current.note_on_use, c3])))
                    if c4 and not current.data_type:
                        current.data_type = normalize_type(" ".join(filter(None, [current.data_type, c4])))
                    if c5 and not current.cardinality:
                        current.cardinality = squash_ws(" ".join(filter(None, [current.cardinality, c5])))

    return fields


def build_text_dump(pdf_path: Path) -> str:
    with pdfplumber.open(pdf_path) as pdf:
        return "\n".join((page.extract_text() or "") for page in pdf.pages)


def find_detail_block(lines: list[str], field_id: str) -> str:
    candidates: list[tuple[int, str]] = []
    for idx, line in enumerate(lines):
        if line.startswith(f"{field_id} "):
            end = idx + 1
            while end < len(lines):
                if HEADING_RE.match(lines[end]) and not lines[end].startswith(f"{field_id} "):
                    break
                end += 1
            block = "\n".join(line for line in lines[idx:end] if not re.fullmatch(r"\d+", line))
            score = 0
            score += block.count("Business Rule") * 3
            score += block.count("Example of use:") * 2
            score -= 3 if re.search(r"\.{5,}", block.splitlines()[0]) else 0
            score -= 2 if any(item.startswith(("/Invoice", "/invoice", "/CreditNote")) for item in block.splitlines()) else 0
            candidates.append((score, block))

    if not candidates:
        return ""

    _, block = max(candidates, key=lambda item: item[0])
    return block.strip()


def find_table_block(lines: list[str], field_id: str) -> str:
    candidates: list[tuple[int, str]] = []
    for idx, line in enumerate(lines):
        if line.startswith(f"{field_id} "):
            end = idx + 1
            while end < len(lines):
                if HEADING_RE.match(lines[end]) and not lines[end].startswith(f"{field_id} "):
                    break
                end += 1
            block = "\n".join(line for line in lines[idx:end] if not re.fullmatch(r"\d+", line))
            block_lines = block.splitlines()
            has_path = any(candidate.startswith(("/Invoice", "/invoice", "/CreditNote")) for candidate in block_lines)
            has_example = "Example of use:" in block
            has_business_rule = "Business Rule" in block
            score = (5 if has_path else 0) + (1 if has_example else 0) - (2 if has_business_rule else 0)
            score -= 3 if re.search(r"\.{5,}", block_lines[0]) else 0
            candidates.append((score, block))

    if not candidates:
        return ""

    _, block = max(candidates, key=lambda item: item[0])
    return block.strip()


def extract_paths_from_text_block(block: str) -> tuple[str, str]:
    if not block:
        return "", ""

    fragments: list[str] = []
    current = ""
    for raw_line in block.splitlines():
        line = raw_line.strip()
        if not line or line in {"Business Rule", "Description", "Example of use:"}:
            if current:
                fragments.append(current)
                current = ""
            continue
        if line.startswith(("/Invoice", "/invoice", "/CreditNote")):
            if current:
                fragments.append(current)
            current = line
            continue
        if (
            current
            and not HEADING_RE.match(line)
            and not RULE_RE.match(line)
            and not line.startswith("<")
            and " " not in line
            and not line.startswith(("ID", "UBL", "Remark", "Table"))
        ):
            current = f"{current}{line}"
            continue
        if current:
            fragments.append(current)
            current = ""

    if current:
        fragments.append(current)

    joined = "".join(fragments)
    return split_paths(joined)


def repair_extension_path_from_example(field: FieldRecord) -> None:
    if "hrextac:" not in field.report_path or not field.sample_value:
        return

    matches = re.findall(
        rf"<\s*hrextac:([A-Za-z0-9]+)[^>]*>\s*{re.escape(field.sample_value)}\s*</\s*hrextac:\1\s*>",
        field.detail_block,
        re.S,
    )
    unique = list(dict.fromkeys(matches))
    if len(unique) != 1:
        return

    example_tag = unique[0]
    for attr in ("invoice_path", "credit_note_path"):
        path = getattr(field, attr)
        if not path or "hrextac:" not in path:
            continue
        if re.search(r"hrextac:[^/]+$", path):
            fixed = re.sub(r"(hrextac:)[^/]+$", rf"\1{example_tag}", path)
            setattr(field, attr, fixed)


def extract_rules(block: str) -> list[str]:
    rules: list[str] = []
    current = ""
    started = False

    for raw_line in block.splitlines():
        line = raw_line.strip()
        if not line or line in {"Business Rule", "Description"}:
            if current:
                rules.append(squash_ws(current))
                current = ""
            continue
        if HEADING_RE.match(line):
            if not started:
                started = True
                continue
            if current:
                rules.append(squash_ws(current))
            break
        if line.startswith("Example of use:"):
            if current:
                rules.append(squash_ws(current))
            break
        if RULE_RE.match(line):
            if current:
                rules.append(squash_ws(current))
            current = line
            continue
        if current and not line.startswith("<"):
            if current.rstrip().endswith(".") and not re.match(r"^[a-z(]", line):
                rules.append(squash_ws(current))
                current = ""
                continue
            current = f"{current} {line}"

    if current:
        rules.append(squash_ws(current))
    return list(dict.fromkeys(rules))


def extract_heading_name(block: str, field_id: str) -> str:
    if not block:
        return ""
    first_line = block.splitlines()[0].strip()
    if first_line.startswith(f"{field_id} "):
        return squash_ws(first_line[len(field_id) + 1 :])
    return ""


def extract_example_value(block: str, path_text: str) -> str:
    if "Example of use:" in block:
        block = block.split("Example of use:", 1)[1]

    block = re.sub(r"^\d+$", "", block, flags=re.M)
    block = block.replace("…", "")
    tag_name, attr_name = last_path_token(path_text)

    if attr_name:
        attr_match = re.search(rf'{re.escape(attr_name)}="([^"]+)"', block)
        if attr_match:
            return attr_match.group(1).strip()

    if tag_name:
        tag_match = re.search(
            rf"<(?:[A-Za-z0-9_]+:)?{re.escape(tag_name)}(?:\s[^>]*)?>\s*([^<\n]+?)\s*</(?:[A-Za-z0-9_]+:)?{re.escape(tag_name)}>",
            block,
            re.S,
        )
        if tag_match:
            return squash_ws(tag_match.group(1))

    for value in re.findall(r">\s*([^<\n]+?)\s*<", block):
        value = squash_ws(value)
        if value and value not in {"...", "…"}:
            return value
    return ""


def extract_value_set(field: FieldRecord) -> str:
    text = "\n".join(
        part
        for part in [field.note_on_use, field.remark, field.detail_block, field.data_type]
        if part
    )
    values: list[str] = []

    if "true | false" in text.lower() or field.data_type.lower().startswith("boolean"):
        values.append("true|false")

    references = [
        "UNTDID 1001",
        "UNTDID 2005",
        "UNTDID 5305",
        "UNTDID 5153",
        "UNTDID 7143",
        "ISO 4217",
        "ISO 3166-1",
        "ISO 11649:2009",
        "EACT",
        "HRTB-2",
        "HR-TB-2",
    ]
    for ref in references:
        if ref.lower() in text.lower():
            values.append(ref)

    bullet_lines = []
    for raw_line in field.detail_block.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("<") or RULE_RE.match(line):
            continue
        if re.match(r"^[•-]\s*", line) or re.match(r"^\d{1,4}\s*[–-]\s*", line):
            bullet_lines.append(line)

    for line in bullet_lines:
        values.append(squash_ws(line.lstrip("•- ")))

    if field.remark:
        values.append(f"Remark: {field.remark}")

    deduped: list[str] = []
    for value in values:
        value = squash_ws(value)
        if value and value not in deduped:
            deduped.append(value)
    return "; ".join(deduped)


def infer_constraints(field: FieldRecord) -> None:
    text = "\n".join(
        part
        for part in [field.note_on_use, field.remark, field.detail_block]
        if part
    )

    max_chars = re.search(r"maximum of (\d+) characters", text, re.I)
    if max_chars:
        field.max_char_length = max_chars.group(1)

    digits = re.search(r"last (\d+) to (\d+) digits", text, re.I)
    if digits:
        field.min_char_length = digits.group(1)
        field.max_char_length = digits.group(2)

    if re.search(r"format\s+yyyy[-/]mm[-/]dd", text, re.I) or "yyyy-MM-d.d" in text:
        field.min_char_length = field.min_char_length or "10"
        field.max_char_length = field.max_char_length or "10"

    if re.search(r"format\s+hh:mm:ss", text, re.I):
        field.min_char_length = field.min_char_length or "8"
        field.max_char_length = field.max_char_length or "8"

    if re.search(r"(written to|rounded to)\s+(2|two)\s+decimal places", text, re.I):
        field.min_decimal_precision = "2"
        field.max_decimal_precision = "2"

    if re.search(r"multiple decimals", text, re.I):
        field.min_decimal_precision = ""
        field.max_decimal_precision = ""

    if field.data_type == "Date" and not field.max_char_length:
        field.min_char_length = "10"
        field.max_char_length = "10"
    if field.data_type == "Time" and not field.max_char_length:
        field.min_char_length = "8"
        field.max_char_length = "8"
    if field.data_type.startswith("Boolean") and not field.max_char_length:
        field.min_char_length = "4"
        field.max_char_length = "5"
    if field.data_type == "Amount" and not field.max_decimal_precision:
        field.max_decimal_precision = "2"


def build_interpretation(field: FieldRecord) -> str:
    parts = [field.field_description]
    if field.note_on_use:
        parts.append(field.note_on_use)
    if field.remark:
        parts.append(f"Remark: {field.remark}")
    return " ".join(part for part in parts if part).strip()


def enrich_fields(fields: list[FieldRecord], spec_text: str) -> None:
    lines = [line.strip() for line in spec_text.splitlines()]
    for field in fields:
        table_block = find_table_block(lines, field.field_id)
        field.detail_block = find_detail_block(lines, field.field_id)
        heading_name = (
            extract_heading_name(field.detail_block, field.field_id)
            if ("Example of use:" in field.detail_block or "Business Rule" in field.detail_block)
            else ""
        )
        if heading_name:
            field.field_name = heading_name
        invoice_path, credit_note_path = extract_paths_from_text_block(table_block)
        if invoice_path:
            field.invoice_path = invoice_path
        if credit_note_path:
            field.credit_note_path = credit_note_path
        field.rules = extract_rules(field.detail_block)
        field.sample_value = extract_example_value(field.detail_block, field.report_path)
        repair_extension_path_from_example(field)
        field.value_set = extract_value_set(field)
        field.interpretation = build_interpretation(field)
        infer_constraints(field)
