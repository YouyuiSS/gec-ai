from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import re
from typing import Any
from urllib.request import Request, urlopen

from tax_parser_runtime.source_io import is_url
from tax_parser_runtime.web_html import HtmlCell, parse_html_tables


USER_AGENT = "tax-law-parser/1.0"


@dataclass
class WebInlineTableConfig:
    profile_name: str
    row_headers: dict[str, str] = field(
        default_factory=lambda: {
            "element": "ELEMENT",
            "type": "Field TYPE",
            "description": "DESCRIPTION",
            "example": "VALUE EXAMPLE",
            "mapping": "UBL Schema Mapping",
            "mandatory": "Mandatory",
            "chars": "Number of Chars",
            "context": "Context",
            "cardinality": "Cardinality",
        }
    )
    required_headers: tuple[str, ...] = ("ELEMENT", "DESCRIPTION", "UBL Schema Mapping")


class WebInlineTableParser:
    def __init__(self, config: WebInlineTableConfig) -> None:
        self.config = config

    def extract(self, source: str | Path) -> list[dict[str, object]]:
        html_text, base_url = self._load_html(source)
        tables = parse_html_tables(html_text, base_url=base_url)
        records: list[dict[str, object]] = []
        seen_ids: set[str] = set()
        for table in tables:
            header_map = self._map_headers(table.headers)
            if not header_map or not self._is_candidate_table(header_map):
                continue
            for row in table.rows:
                record = self._build_record(row, header_map, heading=table.heading_text)
                if record is None:
                    continue
                field_id = str(record["field_id"]).strip()
                if not field_id or field_id in seen_ids:
                    continue
                seen_ids.add(field_id)
                records.append(record)
        return records

    def _load_html(self, source: str | Path) -> tuple[str, str]:
        if isinstance(source, Path):
            return source.read_text(encoding="utf-8", errors="ignore"), ""
        source_str = str(source)
        if is_url(source_str):
            request = Request(source_str, headers={"User-Agent": USER_AGENT})
            with urlopen(request, timeout=30) as response:
                return response.read().decode("utf-8", errors="ignore"), str(response.geturl())
        path = Path(source_str).expanduser().resolve()
        return path.read_text(encoding="utf-8", errors="ignore"), ""

    def _map_headers(self, headers: list[str]) -> dict[str, int]:
        normalized_headers = {self._normalize_header(value): index for index, value in enumerate(headers)}
        mapped: dict[str, int] = {}
        for target, header_name in self.config.row_headers.items():
            index = normalized_headers.get(self._normalize_header(header_name))
            if index is not None:
                mapped[target] = index
        return mapped

    def _is_candidate_table(self, header_map: dict[str, int]) -> bool:
        return all(key in header_map for key in ("element", "description", "mapping"))

    def _build_record(
        self,
        row: list[HtmlCell],
        header_map: dict[str, int],
        *,
        heading: str,
    ) -> dict[str, object] | None:
        element = self._cell_text(row, header_map.get("element"))
        mapping = self._normalize_mapping(self._cell_text(row, header_map.get("mapping")))
        if not element or not mapping:
            return None

        data_type = self._cell_text(row, header_map.get("type"))
        description = self._cell_text(row, header_map.get("description"))
        example = self._cell_text(row, header_map.get("example"))
        mandatory = self._cell_text(row, header_map.get("mandatory"))
        cardinality = self._normalize_cardinality(self._cell_text(row, header_map.get("cardinality")), mandatory)
        char_spec = self._cell_text(row, header_map.get("chars"))
        context = self._cell_text(row, header_map.get("context"))

        min_length, max_length = self._split_length(char_spec)
        rules: list[str] = []
        detail_links = self._cell_links(row, header_map.get("element"))
        if context:
            rules.append(f"Context: {context}")
        for link in detail_links:
            rules.append(f"Detail link: {link}")

        return {
            "field_id": mapping,
            "field_name": element,
            "field_description": description,
            "note_on_use": mandatory,
            "data_type": data_type,
            "cardinality": cardinality,
            "invoice_path": mapping,
            "credit_note_path": "",
            "report_path": mapping,
            "sample_value": example,
            "value_set": "",
            "interpretation": heading,
            "rules": rules,
            "source_pages": [],
            "min_char_length": min_length,
            "max_char_length": max_length,
            "min_decimal_precision": "",
            "max_decimal_precision": "",
            "extractor_name": self.config.profile_name,
        }

    def _cell_text(self, row: list[HtmlCell], index: int | None) -> str:
        if index is None or index >= len(row):
            return ""
        return row[index].text.strip()

    def _cell_links(self, row: list[HtmlCell], index: int | None) -> list[str]:
        if index is None or index >= len(row):
            return []
        return row[index].links

    def _normalize_header(self, value: str) -> str:
        return re.sub(r"\s+", " ", value.replace("\xa0", " ")).strip().lower()

    def _normalize_mapping(self, value: str) -> str:
        if not value:
            return ""
        parts = [segment.strip() for segment in value.split("/") if segment.strip()]
        if not parts:
            return ""
        return "/" + "/".join(parts)

    def _normalize_cardinality(self, value: str, mandatory: str) -> str:
        normalized = value.strip().strip("[]")
        if normalized:
            normalized = normalized.replace("-", "..")
            return normalized
        lower_mandatory = mandatory.lower()
        if "mandatory" in lower_mandatory:
            return "1..1"
        if "optional" in lower_mandatory:
            return "0..1"
        return ""

    def _split_length(self, value: str) -> tuple[str, str]:
        cleaned = value.strip()
        if not cleaned:
            return "", ""
        if ".." in cleaned:
            parts = [part.strip() for part in cleaned.split("..", 1)]
            return parts[0], parts[1]
        if "-" in cleaned and re.fullmatch(r"\d+\s*-\s*\d+", cleaned):
            parts = [part.strip() for part in cleaned.split("-", 1)]
            return parts[0], parts[1]
        if re.fullmatch(r"\d+", cleaned):
            return cleaned, cleaned
        return "", cleaned
