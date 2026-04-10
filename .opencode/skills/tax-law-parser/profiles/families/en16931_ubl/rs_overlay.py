from __future__ import annotations

from pathlib import Path

from .base import En16931UblConfig, En16931UblTableParser


PROFILE_NAME = "rs-srbdt-ext-2025"

PARSER = En16931UblTableParser(
    En16931UblConfig(
        profile_name=PROFILE_NAME,
        header_markers=(
            "иден.",
            "оригинални термин",
            "додатна напомена",
            "ubl путања",
            "српски термин ubl путања",
        ),
        note_prefixes=("Напомена:",),
    )
)


def extract(pdf_path: Path) -> list[dict[str, object]]:
    return PARSER.extract(Path(pdf_path))
