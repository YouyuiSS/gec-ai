from __future__ import annotations

import re
from dataclasses import asdict
from pathlib import Path
from typing import TYPE_CHECKING

from .models import (
    CodeListDefinition,
    CodeListEntry,
    Evidence,
    ExtractionBundle,
    FieldConstraints,
    FieldDefinition,
    PathMap,
    RuleDefinition,
)

if TYPE_CHECKING:
    from scripts.extract_tax_fields import FieldRecord


RULE_CODE_RE = re.compile(r"^(?P<code>(?:HR-)?BR(?:-[A-Z]+)?-\d+)\b")
FIELD_REF_RE = re.compile(r"\b(?:HR-)?(?:BT|BG)-\d+\b")


def parse_cardinality(value: str) -> tuple[int | None, int | str | None]:
    text = value.strip()
    if not text or ".." not in text:
        return None, None
    left, right = text.split("..", 1)
    occurrence_min = int(left) if left.isdigit() else None
    if right.isdigit():
        occurrence_max: int | str | None = int(right)
    elif right:
        occurrence_max = right
    else:
        occurrence_max = None
    return occurrence_min, occurrence_max


def to_int_or_none(value: str) -> int | None:
    return int(value) if value and value.isdigit() else None


def classify_rule(rule_text: str) -> str:
    lowered = rule_text.lower()
    if "=" in rule_text or "sum of" in lowered or "multiplied by" in lowered:
        return "arithmetic"
    if "mutually exclusive" in lowered or "must not both" in lowered:
        return "exclusive"
    if lowered.startswith("if ") or " if " in lowered:
        return "dependency"
    if "must be equal to" in lowered or "equal to" in lowered:
        return "equality"
    if "must contain" in lowered or "must have" in lowered or "must be provided" in lowered:
        return "presence"
    if "code list" in lowered or "list are used" in lowered or "values from table" in lowered:
        return "code_list"
    if "format" in lowered or "decimal places" in lowered or "whitespace characters" in lowered:
        return "format"
    return "other"


def build_evidence(field: "FieldRecord", quote_text: str | None = None) -> list[Evidence]:
    page_numbers = sorted(set(field.source_pages)) or [1]
    quote = quote_text or field.detail_block or field.field_description or field.field_name
    quote = re.sub(r"\s+", " ", quote).strip()[:280]
    return [
        Evidence(
            page_number=page_number,
            source_kind="table",
            quote_text=quote,
        )
        for page_number in page_numbers[:3]
    ]


def value_set_refs(field: "FieldRecord") -> list[str]:
    refs: list[str] = []
    for item in (part.strip() for part in field.value_set.split(";")):
        if not item:
            continue
        if item.startswith("Remark:"):
            continue
        refs.append(item)
    return refs


def field_definition_from_record(record: "FieldRecord") -> FieldDefinition:
    occurrence_min, occurrence_max = parse_cardinality(record.cardinality)
    return FieldDefinition(
        field_code=record.field_id,
        field_name=record.field_name,
        field_kind="atomic",
        field_description=record.field_description or None,
        data_type=record.data_type or None,
        occurrence_min=occurrence_min,
        occurrence_max=occurrence_max,
        sample_value=record.sample_value or None,
        value_set_refs=value_set_refs(record),
        semantic_notes=record.interpretation or None,
        paths=PathMap(
            invoice=record.invoice_path or None,
            credit_note=record.credit_note_path or None,
            remark=record.remark or None,
        ),
        constraints=FieldConstraints(
            min_char_length=to_int_or_none(record.min_char_length),
            max_char_length=to_int_or_none(record.max_char_length),
            min_decimal_scale=to_int_or_none(record.min_decimal_precision),
            max_decimal_scale=to_int_or_none(record.max_decimal_precision),
            format_hint=None,
        ),
        origin="explicit",
        confidence=0.98,
        evidence=build_evidence(record),
    )


def rule_definitions_from_record(record: "FieldRecord") -> list[RuleDefinition]:
    rules: list[RuleDefinition] = []
    for rule_text in record.rules:
        match = RULE_CODE_RE.match(rule_text)
        if not match:
            continue
        rules.append(
            RuleDefinition(
                rule_code=match.group("code"),
                rule_type=classify_rule(rule_text),
                expression_text=rule_text,
                referenced_fields=sorted(set(FIELD_REF_RE.findall(rule_text))),
                severity="error",
                origin="explicit",
                confidence=0.95,
                evidence=build_evidence(record, quote_text=rule_text),
            )
        )
    return rules


def build_code_lists(records: list["FieldRecord"]) -> list[CodeListDefinition]:
    grouped: dict[str, CodeListDefinition] = {}
    for record in records:
        refs = value_set_refs(record)
        ref_names = [ref for ref in refs if re.match(r"^(?:UNTDID|ISO|EACT|HR-TB-2|HRTB-2)", ref)]
        entry_candidates = [ref for ref in refs if ref not in ref_names]
        for ref_name in ref_names:
            code_list = grouped.setdefault(
                ref_name,
                CodeListDefinition(
                    code_list_name=ref_name,
                    origin="explicit",
                    confidence=0.9,
                    evidence=build_evidence(record),
                ),
            )
            existing_codes = {entry.code for entry in code_list.entries}
            for candidate in entry_candidates:
                match = re.match(r"^(?P<code>[^-–]+?)\s*[–-]\s*(?P<label>.+)$", candidate)
                if not match:
                    continue
                code = match.group("code").strip()
                label = match.group("label").strip()
                if code in existing_codes:
                    continue
                code_list.entries.append(CodeListEntry(code=code, label=label))
                existing_codes.add(code)
    return list(grouped.values())


def _fallback_field_definitions_from_rules(
    parsed,
    source_path: Path,
    existing_field_codes: set[str],
    rules: list[RuleDefinition],
) -> list[FieldDefinition]:
    missing_field_codes = sorted(
        {
            ref
            for rule in rules
            for ref in rule.referenced_fields
            if ref.startswith(("BT-", "HR-BT-")) and ref not in existing_field_codes
        }
    )
    if not missing_field_codes:
        return []

    from scripts.extract_tax_fields import (
        extract_example_value,
        extract_heading_name,
        extract_paths_from_text_block,
        find_detail_block,
        find_table_block,
    )

    fallback_fields: list[FieldDefinition] = []

    for field_code in missing_field_codes:
        page_number, table_block, detail_block = _locate_fallback_blocks(
            parsed=parsed,
            source_path=source_path,
            field_code=field_code,
            find_table_block=find_table_block,
            find_detail_block=find_detail_block,
        )
        if not table_block and not detail_block:
            continue

        field_name = _clean_inferred_field_name(
            (
            extract_heading_name(detail_block, field_code)
            or extract_heading_name(table_block, field_code)
            or field_code
            )
        )
        invoice_path, credit_note_path = extract_paths_from_text_block(table_block)
        report_path = "\n".join(
            filter(
                None,
                [
                    f"Invoice: {invoice_path}" if invoice_path else "",
                    f"CreditNote: {credit_note_path}" if credit_note_path else "",
                ],
            )
        )
        sample_value = extract_example_value(detail_block, report_path)
        evidence_quote = (table_block or detail_block or field_name).replace("\n", " ")[:280]

        fallback_fields.append(
            FieldDefinition(
                field_code=field_code,
                field_name=field_name,
                field_kind="atomic",
                field_description=None,
                data_type=None,
                occurrence_min=None,
                occurrence_max=None,
                sample_value=sample_value or None,
                semantic_notes="Recovered from rule reference fallback.",
                paths=PathMap(
                    invoice=invoice_path or None,
                    credit_note=credit_note_path or None,
                    remark=None,
                ),
                origin="inferred",
                confidence=0.65,
                evidence=[
                    Evidence(
                        page_number=page_number,
                        source_kind="paragraph",
                        quote_text=evidence_quote,
                    )
                ],
            )
        )

    return fallback_fields


def _locate_fallback_blocks(
    parsed,
    source_path: Path,
    field_code: str,
    find_table_block,
    find_detail_block,
) -> tuple[int, str, str]:
    candidates: list[tuple[int, int, str, str]] = []

    for page in parsed.pages:
        if field_code not in page.text:
            continue

        lines = [line.strip() for line in page.text.splitlines()]
        table_block = find_table_block(lines, field_code)
        detail_block = find_detail_block(lines, field_code)
        merged = "\n".join(part for part in [table_block, detail_block] if part)
        if not merged:
            continue

        score = 0
        score += 5 if "Example of use:" in merged else 0
        score += 4 if "Business Rule" in merged else 0
        score += 4 if "/Invoice/" in merged or "/CreditNote/" in merged else 0
        score += 3 if "<cbc:" in merged or "<cac:" in merged else 0
        score -= 6 if re.search(r"\.{5,}", merged.splitlines()[0]) else 0
        score -= 2 if len(merged) < 120 else 0
        candidates.append((score, page.page_number, table_block, detail_block))

    if not candidates:
        from scripts.extract_tax_fields import build_text_dump

        lines = [line.strip() for line in build_text_dump(Path(source_path)).splitlines()]
        return 1, find_table_block(lines, field_code), find_detail_block(lines, field_code)

    _, page_number, table_block, detail_block = max(candidates, key=lambda item: (item[0], item[1]))
    return page_number, table_block, detail_block


def _clean_inferred_field_name(value: str) -> str:
    cleaned = re.sub(r"\s+", " ", value).strip()
    for marker in (" Example of use", " Business Rule", " Description", " The ", " At "):
        if marker in cleaned:
            cleaned = cleaned.split(marker, 1)[0].strip()
            break
    return cleaned[:120].strip(" -:") or value


class PdfTaxFieldDeterministicExtractor:
    def __init__(self, source_path: Path | None = None) -> None:
        self.source_path = source_path

    def extract(self, parsed) -> ExtractionBundle:
        from scripts.extract_tax_fields import extract_tax_field_records

        source_path = parsed.document.source_path or self.source_path
        if source_path is None:
            raise ValueError("A PDF source path is required for deterministic extraction.")

        records = extract_tax_field_records(Path(source_path))
        field_definitions = [field_definition_from_record(record) for record in records]

        rule_map: dict[str, RuleDefinition] = {}
        for record in records:
            for rule in rule_definitions_from_record(record):
                if rule.rule_code not in rule_map:
                    rule_map[rule.rule_code] = rule

        fallback_fields = _fallback_field_definitions_from_rules(
            parsed=parsed,
            source_path=Path(source_path),
            existing_field_codes={field.field_code for field in field_definitions},
            rules=list(rule_map.values()),
        )
        field_definitions.extend(fallback_fields)

        code_lists = build_code_lists(records)

        return ExtractionBundle(
            document=parsed.document,
            fields=field_definitions,
            rules=list(rule_map.values()),
            code_lists=code_lists,
        )
