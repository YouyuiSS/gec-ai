from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import re
from typing import Callable


TYPE_MAP = {
    "A": "Amount",
    "B": "Binary Object",
    "C": "Code",
    "D": "Date",
    "I": "Identifier",
    "O": "Document Reference Identifier",
    "P": "Percent",
    "Q": "Quantity",
    "S": "Attribute",
    "T": "Text",
    "U": "Unit Price Amount",
}


SemanticNameParser = Callable[[str], tuple[str, str]]


def default_semantic_name_parser(value: str) -> tuple[str, str]:
    lines = [line.strip().lstrip("+").strip() for line in value.splitlines() if line.strip()]
    if not lines:
        return "", ""

    english_lines = [line for line in lines if not _contains_cyrillic(line)]
    local_lines = [line for line in lines if _contains_cyrillic(line)]

    if english_lines or local_lines:
        return " ".join(english_lines).strip(), " ".join(local_lines).strip()

    if len(lines) == 1:
        return lines[0], lines[0]
    return lines[0], " ".join(lines[1:])


def _contains_cyrillic(text: str) -> bool:
    return bool(re.search(r"[\u0400-\u04FF]", text))


@dataclass
class En16931UblConfig:
    profile_name: str
    field_id_pattern: re.Pattern[str] = field(
        default_factory=lambda: re.compile(r"^(?:[A-Z]{2,}-)?BT-\d+(?:\.\d+)?$")
    )
    group_id_pattern: re.Pattern[str] = field(
        default_factory=lambda: re.compile(r"^(?:[A-Z]{2,}-)?BG-\d+(?:\.\d+)?$")
    )
    path_pattern: re.Pattern[str] = field(
        default_factory=lambda: re.compile(r"^/(?:Invoice|CreditNote)/")
    )
    note_prefixes: tuple[str, ...] = ("Напомена:", "Note:")
    header_markers: tuple[str, ...] = (
        "иден.",
        "оригинални термин",
        "додатна напомена",
        "ubl путања",
        "business term",
        "ubl invoice path",
    )
    semantic_name_parser: SemanticNameParser = default_semantic_name_parser


class En16931UblTableParser:
    def __init__(self, config: En16931UblConfig) -> None:
        self.config = config

    def extract(self, pdf_path: Path) -> list[dict[str, object]]:
        import pdfplumber

        records: dict[str, dict[str, object]] = {}
        current: dict[str, object] | None = None
        current_table_key: tuple[int, int] | None = None

        with pdfplumber.open(str(pdf_path)) as pdf:
            for page in pdf.pages:
                tables = page.extract_tables() or []
                for table_index, table in enumerate(tables):
                    table_key = (int(page.page_number), table_index)
                    pending_note_lines: list[str] = []
                    rows = [self._normalize_row(row) for row in table]
                    for row in rows:
                        if not any(row):
                            continue
                        if self._is_header_row(row):
                            pending_note_lines.clear()
                            continue

                        field_match = self._find_identifier(row, self.config.field_id_pattern)
                        if field_match:
                            if current:
                                self._store_record(records, current)
                            field_index, field_id = field_match
                            current = self._build_record(
                                field_id=field_id,
                                row=row,
                                field_index=field_index,
                                page_number=int(page.page_number),
                            )
                            current_table_key = table_key
                            if pending_note_lines:
                                self._append_note_text(
                                    current,
                                    "\n".join(pending_note_lines),
                                    page_number=int(page.page_number),
                                )
                                pending_note_lines.clear()
                            continue

                        group_match = self._find_identifier(row, self.config.group_id_pattern)
                        if group_match:
                            if current:
                                self._store_record(records, current)
                                current = None
                                current_table_key = None
                            pending_note_lines.clear()
                            continue

                        if current and current_table_key == table_key and self._looks_like_anonymous_subfield_row(row):
                            self._store_record(records, current)
                            current = None
                            current_table_key = None
                            continue

                        if current and current_table_key == table_key and self._looks_like_path_row(row):
                            self._apply_path_row(current, row, page_number=int(page.page_number))
                            continue

                        note_text = self._extract_single_cell_note_text(row)
                        if note_text:
                            if current and current_table_key == table_key:
                                self._append_note_text(current, note_text, page_number=int(page.page_number))
                            elif self._starts_with_note_prefix(note_text):
                                pending_note_lines.append(note_text)
                            continue

                        if current and current_table_key == table_key and self._looks_like_continuation_row(row):
                            self._apply_continuation_row(current, row, page_number=int(page.page_number))

            if current:
                self._store_record(records, current)

        return [
            self._finalize_record(record)
            for _, record in sorted(records.items())
            if str(record.get("field_id", "")).strip()
        ]

    def _normalize_row(self, row: list[str | None]) -> list[str]:
        cells = [(cell or "").replace("\r", "\n").strip() for cell in row]
        while len(cells) < 5:
            cells.append("")
        return cells[:5]

    def _is_header_row(self, row: list[str]) -> bool:
        cells = [part.lower() for part in row if part]
        hits = 0
        for marker in self.config.header_markers:
            normalized_marker = marker.lower()
            if any(normalized_marker in cell for cell in cells):
                hits += 1
        required_hits = min(2, len(self.config.header_markers))
        return hits >= required_hits

    def _find_identifier(self, row: list[str], pattern: re.Pattern[str]) -> tuple[int, str] | None:
        for index, cell in enumerate(row[:2]):
            value = cell.strip()
            if value and pattern.fullmatch(value):
                return index, value
        return None

    def _build_record(self, field_id: str, row: list[str], field_index: int, page_number: int) -> dict[str, object]:
        semantic_cell = self._extract_semantic_cell(row, field_index)
        english_name, local_name = self.config.semantic_name_parser(semantic_cell)
        return {
            "field_id": field_id,
            "field_name": local_name or english_name,
            "field_description": english_name,
            "note_on_use": self._extract_inline_note(row, field_index),
            "data_type": TYPE_MAP.get(self._extract_data_type_cell(row, field_index), self._extract_data_type_cell(row, field_index)),
            "cardinality": self._extract_cardinality_cell(row, field_index),
            "invoice_path": "",
            "credit_note_path": "",
            "report_path": "",
            "sample_value": "",
            "value_set": "",
            "interpretation": "",
            "rules": [],
            "source_pages": {page_number},
            "min_char_length": "",
            "max_char_length": "",
            "min_decimal_precision": "",
            "max_decimal_precision": "",
            "extractor_name": self.config.profile_name,
        }

    def _extract_semantic_cell(self, row: list[str], field_index: int) -> str:
        if field_index <= 0:
            return row[1] if len(row) > 1 else ""
        return row[field_index - 1]

    def _extract_data_type_cell(self, row: list[str], field_index: int) -> str:
        if field_index == 0:
            return row[3] if len(row) > 3 else ""
        index = field_index + 1
        return row[index] if index < len(row) else ""

    def _extract_cardinality_cell(self, row: list[str], field_index: int) -> str:
        if field_index == 0:
            return row[2] if len(row) > 2 else ""
        index = field_index + 2
        return row[index] if index < len(row) else ""

    def _extract_inline_note(self, row: list[str], field_index: int) -> str:
        if field_index == 0:
            candidate = row[4] if len(row) > 4 else ""
        else:
            index = field_index + 3
            candidate = row[index] if index < len(row) else ""
        return "" if self._looks_like_page_reference(candidate) else candidate

    def _looks_like_page_reference(self, value: str) -> bool:
        return bool(re.fullmatch(r"\d+(?:\s*[-–]\s*\d+)?", value.strip()))

    def _normalize_path_line(self, value: str) -> str:
        normalized = value.strip()
        if normalized.startswith(("Invoice/", "CreditNote/")):
            return "/" + normalized
        return normalized

    def _is_document_path_root(self, value: str) -> bool:
        normalized = self._normalize_path_line(value)
        return normalized.startswith("/Invoice/") or normalized.startswith("/CreditNote/")

    def _is_path_like_line(self, value: str) -> bool:
        return bool(self.config.path_pattern.match(self._normalize_path_line(value)))

    def _looks_like_path_row(self, row: list[str]) -> bool:
        path_block = row[2]
        return any(self._is_path_like_line(line) for line in path_block.splitlines() if line.strip())

    def _looks_like_anonymous_subfield_row(self, row: list[str]) -> bool:
        return bool(row[1]) and bool(row[3]) and not row[0] and not self._looks_like_path_row(row)

    def _apply_path_row(self, record: dict[str, object], row: list[str], page_number: int) -> None:
        semantic_cell = row[1].strip()
        if semantic_cell:
            english_name, local_name = self.config.semantic_name_parser(semantic_cell)
            if not str(record.get("field_name", "")).strip() and (local_name or english_name):
                record["field_name"] = local_name or english_name
            if not str(record.get("field_description", "")).strip() and english_name:
                record["field_description"] = english_name

        invoice_paths, credit_paths, notes = self._split_path_block(row[2])

        if invoice_paths:
            record["invoice_path"] = "\n".join(invoice_paths)
        if credit_paths:
            record["credit_note_path"] = "\n".join(credit_paths)
        if invoice_paths or credit_paths:
            combined = []
            if invoice_paths:
                combined.append("Invoice: " + "\n".join(invoice_paths))
            if credit_paths:
                combined.append("CreditNote: " + "\n".join(credit_paths))
            record["report_path"] = "\n".join(combined)
        if notes:
            existing = str(record.get("note_on_use", "")).strip()
            extra = "\n".join(notes).strip()
            record["note_on_use"] = extra if not existing else f"{existing}\n{extra}"
        source_pages = set(record.get("source_pages", []))
        source_pages.add(page_number)
        record["source_pages"] = source_pages

    def _looks_like_continuation_row(self, row: list[str]) -> bool:
        return bool(row[4]) and not row[0] and not row[1] and not row[2] and not row[3]

    def _apply_continuation_row(self, record: dict[str, object], row: list[str], page_number: int) -> None:
        extra = row[4].strip()
        if not extra:
            return
        self._append_note_text(record, extra, page_number=page_number)

    def _extract_single_cell_note_text(self, row: list[str]) -> str:
        values = [cell.strip() for cell in row if cell.strip()]
        if len(values) != 1:
            return ""
        value = values[0]
        if value.lower() == "attribute":
            return ""
        if value.lstrip().startswith("- "):
            return ""
        return value

    def _starts_with_note_prefix(self, value: str) -> bool:
        return any(value.startswith(prefix) for prefix in self.config.note_prefixes)

    def _append_note_text(self, record: dict[str, object], extra: str, page_number: int) -> None:
        extra = extra.strip()
        if not extra:
            return
        existing = str(record.get("note_on_use", "")).strip()
        record["note_on_use"] = extra if not existing else f"{existing}\n{extra}"
        source_pages = set(record.get("source_pages", []))
        source_pages.add(page_number)
        record["source_pages"] = source_pages

    def _store_record(self, records: dict[str, dict[str, object]], record: dict[str, object]) -> None:
        field_id = str(record.get("field_id", "")).strip()
        if not field_id:
            return
        existing = records.get(field_id)
        if existing is None:
            records[field_id] = record
            return

        for key in [
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
            "min_char_length",
            "max_char_length",
            "min_decimal_precision",
            "max_decimal_precision",
        ]:
            current_value = str(existing.get(key, "")).strip()
            incoming_value = str(record.get(key, "")).strip()
            if not current_value and incoming_value:
                existing[key] = incoming_value
                continue
            if current_value and incoming_value and self._should_prefer_incoming_value(
                key,
                current_value=current_value,
                incoming_value=incoming_value,
            ):
                existing[key] = incoming_value

        existing_pages = set(existing.get("source_pages", []))
        existing_pages.update(record.get("source_pages", []))
        existing["source_pages"] = existing_pages

    def _should_prefer_incoming_value(self, key: str, *, current_value: str, incoming_value: str) -> bool:
        if key == "data_type":
            return self._score_data_type(incoming_value) > self._score_data_type(current_value)
        if key == "cardinality":
            return self._score_cardinality(incoming_value) > self._score_cardinality(current_value)
        return False

    def _score_data_type(self, value: str) -> int:
        normalized = value.strip()
        if not normalized:
            return 0
        if normalized.startswith("Abschnitt "):
            return 1
        if normalized in TYPE_MAP.values():
            return 4
        return 3

    def _score_cardinality(self, value: str) -> int:
        normalized = value.strip()
        if not normalized:
            return 0
        if re.fullmatch(r"\d+(?:\.\.(?:\*|\d+))?", normalized):
            return 3
        return 1

    def _finalize_record(self, record: dict[str, object]) -> dict[str, object]:
        finalized = dict(record)
        finalized["rules"] = list(finalized.get("rules", []))
        finalized["source_pages"] = sorted({int(page) for page in finalized.get("source_pages", [])})
        for key in [
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
            "min_char_length",
            "max_char_length",
            "min_decimal_precision",
            "max_decimal_precision",
            "extractor_name",
        ]:
            finalized[key] = str(finalized.get(key, "")).strip()
        return finalized

    def _split_path_block(self, value: str) -> tuple[list[str], list[str], list[str]]:
        raw_lines = [self._normalize_path_line(line) for line in value.splitlines() if line.strip()]
        normalized_paths: list[str] = []
        notes: list[str] = []
        current_path = ""

        for line in raw_lines:
            if line.startswith(self.config.note_prefixes):
                if current_path:
                    normalized_paths.append(current_path)
                    current_path = ""
                notes.append(line)
                continue
            if self._is_document_path_root(line):
                if current_path:
                    normalized_paths.append(current_path)
                current_path = line
                continue
            if current_path:
                current_path += line
            else:
                notes.append(line)

        if current_path:
            normalized_paths.append(current_path)

        invoice_paths = [line for line in normalized_paths if line.startswith("/Invoice/")]
        credit_paths = [line for line in normalized_paths if line.startswith("/CreditNote/")]
        return invoice_paths, credit_paths, notes
