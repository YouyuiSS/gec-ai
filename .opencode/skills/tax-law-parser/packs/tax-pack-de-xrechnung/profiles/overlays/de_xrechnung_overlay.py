from __future__ import annotations

from pathlib import Path

from tax_parser_runtime.families.en16931_ubl.base import En16931UblConfig, En16931UblTableParser


PROFILE_NAME = "de-xrechnung-3-0-x"

PARSER = En16931UblTableParser(
    En16931UblConfig(
        profile_name=PROFILE_NAME,
        header_markers=(
            "semantischer datentyp",
            "anz.",
            "seite",
        ),
        note_prefixes=("Anmerkung:", "Note:"),
    )
)


def extract(pdf_path: Path) -> list[dict[str, object]]:
    return PARSER.extract(Path(pdf_path))
