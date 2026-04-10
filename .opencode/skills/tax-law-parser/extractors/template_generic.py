from __future__ import annotations

from pathlib import Path


PROFILE_NAME = "template-generic"


def extract(pdf_path: Path) -> list[dict[str, object]]:
    raise NotImplementedError(
        "Copy this module to a document-specific extractor, implement deterministic parsing, "
        "and register it in extractors/registry.json before using it."
    )
