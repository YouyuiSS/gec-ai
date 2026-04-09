from __future__ import annotations

import re
from pathlib import Path

from .models import ParsedDocument, ParsedPage, RegulationDocument


class PdfPlumberParser:
    def parse(self, document: RegulationDocument, source_path: Path) -> ParsedDocument:
        try:
            import pdfplumber
        except ModuleNotFoundError as exc:
            raise RuntimeError(
                "pdfplumber is required to parse PDF documents. Install it in the current environment."
            ) from exc

        pages: list[ParsedPage] = []
        with pdfplumber.open(source_path) as pdf:
            for page_number, page in enumerate(pdf.pages, start=1):
                text = page.extract_text() or ""
                tables = page.extract_tables() or []
                headings = [
                    line.strip()
                    for line in text.splitlines()
                    if re.match(r"^(?:HR-)?(?:BT|BG|BR|TB)-\d+\b", line.strip())
                ]
                examples = re.findall(r"<[^>]+>.*?</[^>]+>", text, re.S)
                pages.append(
                    ParsedPage(
                        page_number=page_number,
                        text=text,
                        tables=tables,
                        examples=examples[:20],
                        headings=headings[:50],
                    )
                )
        return ParsedDocument(document=document, pages=pages)
