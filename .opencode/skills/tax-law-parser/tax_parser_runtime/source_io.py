from __future__ import annotations

from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
import re
from typing import Any
from urllib.parse import urlparse
from urllib.request import Request, urlopen


USER_AGENT = "tax-law-parser/1.0"


class HtmlTextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._chunks: list[str] = []

    def handle_data(self, data: str) -> None:
        if data:
            self._chunks.append(data)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"br", "p", "div", "li", "tr", "td", "th", "h1", "h2", "h3", "h4"}:
            self._chunks.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in {"p", "div", "li", "tr", "td", "th", "h1", "h2", "h3", "h4"}:
            self._chunks.append("\n")

    def get_text(self) -> str:
        return normalize_whitespace("".join(self._chunks))


@dataclass
class SourceInput:
    raw: str
    kind: str
    identifier: str
    path: Path | None
    url: str | None

    @property
    def display_name(self) -> str:
        return self.identifier


def normalize_whitespace(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def is_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def parse_source_args(*, source: str | None, pdf: str | None) -> SourceInput:
    raw = (source or pdf or "").strip()
    if not raw:
        raise SystemExit("Either --source or --pdf is required.")

    if is_url(raw):
        parsed = urlparse(raw)
        suffix = Path(parsed.path).suffix.lower()
        kind = "pdf" if suffix == ".pdf" else "web"
        return SourceInput(
            raw=raw,
            kind=kind,
            identifier=raw,
            path=None,
            url=raw,
        )

    path = Path(raw).expanduser().resolve()
    if not path.exists():
        raise SystemExit(f"Source not found: {path}")

    suffix = path.suffix.lower()
    if suffix == ".pdf":
        kind = "pdf"
    elif suffix in {".html", ".htm"}:
        kind = "web"
    else:
        raise SystemExit(f"Unsupported source type: {path}")

    return SourceInput(
        raw=raw,
        kind=kind,
        identifier=str(path),
        path=path,
        url=None,
    )


def fetch_bytes(url: str, *, timeout: int = 30) -> bytes:
    request = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(request, timeout=timeout) as response:
        return response.read()


def read_text_sample(source: SourceInput, *, max_pages: int = 6, max_chars: int = 12000) -> str:
    if source.kind == "pdf":
        return read_pdf_text_sample(source, max_pages=max_pages)
    return read_html_text(source)[:max_chars]


def read_pdf_text_sample(source: SourceInput, *, max_pages: int = 6) -> str:
    try:
        import pdfplumber
    except ModuleNotFoundError as exc:
        raise RuntimeError("pdfplumber is required to inspect PDF files.") from exc

    if source.path is None:
        raise RuntimeError("Remote PDF inputs are not supported yet.")

    chunks: list[str] = []
    with pdfplumber.open(source.path) as pdf:
        for page in pdf.pages[:max_pages]:
            chunks.append(page.extract_text() or "")
    return "\n".join(chunks)


def read_html_text(source: SourceInput) -> str:
    if source.url:
        payload = fetch_bytes(source.url)
    elif source.path:
        payload = source.path.read_bytes()
    else:
        raise RuntimeError("HTML source must have a URL or path.")

    parser = HtmlTextExtractor()
    parser.feed(payload.decode("utf-8", errors="ignore"))
    return parser.get_text()


def source_metadata(source: SourceInput) -> dict[str, Any]:
    return {
        "source_input": source.raw,
        "source_kind": source.kind,
        "source_identifier": source.identifier,
        "source_url": source.url or "",
        "source_path": str(source.path) if source.path else "",
    }
