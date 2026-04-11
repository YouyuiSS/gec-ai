from __future__ import annotations

from pathlib import Path

from tax_parser_runtime.families.hr_einvoice_legacy.base import extract_hr_legacy_records


PROFILE_NAME = "hr-einvoice-legacy"


def extract(pdf_path: Path) -> list[dict[str, object]]:
    return extract_hr_legacy_records(Path(pdf_path), profile_name=PROFILE_NAME)
