from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import re
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from tax_parser_runtime.source_io import is_url
from tax_parser_runtime.web_html import HtmlCell, parse_html_tables


USER_AGENT = "tax-law-parser/1.0"


@dataclass
class WebDrilldownTreeConfig:
    profile_name: str
    header_aliases: dict[str, str] = field(
        default_factory=lambda: {
            "card": "Card",
            "name": "Name",
            "description": "Description",
        }
    )
    root_segment: str = "ubl-invoice"
    root_name: str = "ubl:Invoice"


class WebDrilldownTreeParser:
    def __init__(self, config: WebDrilldownTreeConfig) -> None:
        self.config = config

    def extract(self, source: str | Path) -> list[dict[str, object]]:
        html_text, base_url = self._load_html(source)
        tables = parse_html_tables(html_text, base_url=base_url)
        records: list[dict[str, object]] = []
        seen_ids: set[str] = set()
        for table in tables:
            header_map = self._map_headers(table.headers)
            if not self._is_candidate_table(header_map):
                continue
            for row in table.rows:
                record = self._build_record(row, header_map)
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
        normalized = {self._normalize_header(value): index for index, value in enumerate(headers)}
        mapped: dict[str, int] = {}
        for key, expected in self.config.header_aliases.items():
            index = normalized.get(self._normalize_header(expected))
            if index is not None:
                mapped[key] = index
        return mapped

    def _is_candidate_table(self, header_map: dict[str, int]) -> bool:
        return all(key in header_map for key in ("card", "name", "description"))

    def _build_record(self, row: list[HtmlCell], header_map: dict[str, int]) -> dict[str, object] | None:
        name_cell = self._cell(row, header_map["name"])
        card_cell = self._cell(row, header_map["card"])
        desc_cell = self._cell(row, header_map["description"])

        node_name = self._normalize_name(name_cell.text)
        detail_url = name_cell.links[0] if name_cell.links else ""
        invoice_path = self._path_from_detail_url(detail_url, node_name)
        if not node_name or not invoice_path:
            return None

        detail_text = desc_cell.text
        title, description, sample_value, rules = self._split_description(detail_text)
        if detail_url:
            rules.append(f"Detail page: {detail_url}")

        return {
            "field_id": invoice_path,
            "field_name": node_name.replace("@", ""),
            "field_description": description or title,
            "note_on_use": "",
            "data_type": "",
            "cardinality": self._normalize_cardinality(card_cell.text),
            "invoice_path": invoice_path,
            "credit_note_path": "",
            "report_path": invoice_path,
            "sample_value": sample_value,
            "value_set": "",
            "interpretation": title,
            "rules": rules,
            "source_pages": [],
            "min_char_length": "",
            "max_char_length": "",
            "min_decimal_precision": "",
            "max_decimal_precision": "",
            "extractor_name": self.config.profile_name,
        }

    def _cell(self, row: list[HtmlCell], index: int) -> HtmlCell:
        return row[index] if index < len(row) else HtmlCell(tag="td", text="", links=[])

    def _normalize_header(self, value: str) -> str:
        return re.sub(r"\s+", " ", value).strip().lower()

    def _normalize_name(self, value: str) -> str:
        normalized = re.sub(r"^[•\s]+", "", value or "").strip()
        return normalized

    def _normalize_cardinality(self, value: str) -> str:
        normalized = value.strip()
        if re.fullmatch(r"\d+\.\.(?:\d+|\*)", normalized):
            return normalized
        if normalized == "M":
            return "1..1"
        if normalized == "O":
            return "0..1"
        return normalized

    def _path_from_detail_url(self, detail_url: str, fallback_name: str) -> str:
        if not detail_url:
            if fallback_name == self.config.root_name:
                return f"/{self.config.root_name}"
            return ""
        parsed = urlparse(detail_url)
        parts = [part for part in parsed.path.split("/") if part]
        if self.config.root_segment not in parts:
            return ""
        index = parts.index(self.config.root_segment)
        tail = parts[index:]
        path_parts: list[str] = []
        for position, segment in enumerate(tail):
            if position == 0:
                path_parts.append(self.config.root_name)
                continue
            if segment == "tree":
                continue
            if segment.startswith(("cbc-", "cac-", "ext-", "ubl-")):
                prefix, name = segment.split("-", 1)
                path_parts.append(f"{prefix}:{name}")
                continue
            path_parts.append(f"@{segment}")
        return "/" + "/".join(path_parts)

    def _split_description(self, value: str) -> tuple[str, str, str, list[str]]:
        lines = [line.strip() for line in value.splitlines() if line.strip()]
        title = lines[0] if lines else ""
        description_parts: list[str] = []
        sample_value = ""
        rules: list[str] = []
        body_lines = lines[1:] if len(lines) > 1 else []
        if not body_lines and title:
            body_lines = [title]
            title = ""
        for line in body_lines:
            if line.startswith("Example value:"):
                sample_value = line.removeprefix("Example value:").strip(" `")
                continue
            if line.startswith("Default value:"):
                rules.append(line)
                continue
            description_parts.append(line)
        return title, " ".join(description_parts).strip(), sample_value, rules
