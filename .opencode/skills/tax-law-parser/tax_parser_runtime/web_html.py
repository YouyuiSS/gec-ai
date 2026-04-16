from __future__ import annotations

from dataclasses import dataclass, field
from html import unescape
from html.parser import HTMLParser
import re
from urllib.parse import urljoin


def normalize_whitespace(value: str) -> str:
    return re.sub(r"\s+", " ", unescape(value)).strip()


def normalize_multiline_text(value: str) -> str:
    lines = [normalize_whitespace(line) for line in re.split(r"\n+", unescape(value))]
    return "\n".join(line for line in lines if line)


@dataclass
class HtmlCell:
    tag: str
    text: str
    links: list[str] = field(default_factory=list)


@dataclass
class HtmlTable:
    heading_text: str
    heading_id: str
    headers: list[str]
    rows: list[list[HtmlCell]]


class HtmlTableExtractor(HTMLParser):
    def __init__(self, *, base_url: str = "") -> None:
        super().__init__()
        self.base_url = base_url
        self.tables: list[HtmlTable] = []
        self._current_heading_text = ""
        self._current_heading_id = ""
        self._heading_buffer: list[str] = []
        self._heading_tag = ""
        self._heading_attrs: dict[str, str] = {}
        self._current_table: dict[str, object] | None = None
        self._current_row: list[HtmlCell] | None = None
        self._current_cell: dict[str, object] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_map = {key: value or "" for key, value in attrs}
        if tag in {"h1", "h2", "h3", "h4"}:
            self._heading_tag = tag
            self._heading_attrs = attr_map
            self._heading_buffer = []
            return

        if tag == "table":
            self._current_table = {
                "heading_text": self._current_heading_text,
                "heading_id": self._current_heading_id,
                "rows": [],
            }
            return

        if tag == "tr" and self._current_table is not None:
            self._current_row = []
            return

        if tag in {"th", "td"} and self._current_table is not None:
            if self._current_row is None:
                self._current_row = []
            self._current_cell = {"tag": tag, "chunks": [], "links": []}
            return

        if tag == "a" and self._current_cell is not None:
            href = attr_map.get("href", "").strip()
            if href:
                self._current_cell["links"].append(urljoin(self.base_url, href))
            return

        if tag == "br" and self._current_cell is not None:
            self._current_cell["chunks"].append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in {"h1", "h2", "h3", "h4"} and tag == self._heading_tag:
            self._current_heading_text = normalize_whitespace("".join(self._heading_buffer))
            self._current_heading_id = self._heading_attrs.get("id", "").strip()
            self._heading_tag = ""
            self._heading_attrs = {}
            self._heading_buffer = []
            return

        if tag in {"th", "td"} and self._current_cell is not None:
            cell = HtmlCell(
                tag=str(self._current_cell["tag"]),
                text=normalize_multiline_text("".join(self._current_cell["chunks"])),
                links=list(self._current_cell["links"]),
            )
            if self._current_row is not None:
                self._current_row.append(cell)
            self._current_cell = None
            return

        if tag == "tr" and self._current_row is not None and self._current_table is not None:
            rows = self._current_table["rows"]
            assert isinstance(rows, list)
            rows.append(self._current_row)
            self._current_row = None
            return

        if tag in {"thead", "tbody"} and self._current_row is not None and self._current_table is not None:
            rows = self._current_table["rows"]
            assert isinstance(rows, list)
            rows.append(self._current_row)
            self._current_row = None
            return

        if tag == "table" and self._current_table is not None:
            rows = self._current_table["rows"]
            assert isinstance(rows, list)
            headers: list[str] = []
            body_rows: list[list[HtmlCell]] = []
            if rows:
                first_row = rows[0]
                if first_row and all(cell.tag == "th" for cell in first_row):
                    headers = [cell.text for cell in first_row]
                    body_rows = rows[1:]
                else:
                    headers = [cell.text for cell in first_row]
                    body_rows = rows[1:]
            self.tables.append(
                HtmlTable(
                    heading_text=str(self._current_table["heading_text"]),
                    heading_id=str(self._current_table["heading_id"]),
                    headers=headers,
                    rows=body_rows,
                )
            )
            self._current_table = None

    def handle_data(self, data: str) -> None:
        if self._current_cell is not None:
            self._current_cell["chunks"].append(data)
            return
        if self._heading_tag:
            self._heading_buffer.append(data)


def parse_html_tables(html_text: str, *, base_url: str = "") -> list[HtmlTable]:
    parser = HtmlTableExtractor(base_url=base_url)
    parser.feed(html_text)
    return parser.tables
