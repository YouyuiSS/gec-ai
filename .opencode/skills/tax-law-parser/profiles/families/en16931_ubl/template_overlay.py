from __future__ import annotations

from pathlib import Path

from .base import En16931UblConfig, En16931UblTableParser


PROFILE_NAME = "template-overlay"

PARSER = En16931UblTableParser(
    En16931UblConfig(
        profile_name=PROFILE_NAME,
    )
)


def extract(pdf_path: Path) -> list[dict[str, object]]:
    raise NotImplementedError(
        "Copy this overlay, set PROFILE_NAME, tune the family configuration, "
        "and add any jurisdiction-specific hooks before using it."
    )
