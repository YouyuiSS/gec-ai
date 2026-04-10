from __future__ import annotations

from pathlib import Path


def extract(pdf_path: Path) -> list[dict[str, object]]:
    from profiles.families.en16931_ubl.rs_overlay import extract as overlay_extract

    return overlay_extract(Path(pdf_path))
