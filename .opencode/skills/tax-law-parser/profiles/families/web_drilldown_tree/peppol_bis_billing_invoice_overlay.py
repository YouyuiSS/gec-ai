from __future__ import annotations

from pathlib import Path

from .base import WebDrilldownTreeConfig, WebDrilldownTreeParser


PROFILE_NAME = "peppol-bis-billing-ubl-invoice-web"

PARSER = WebDrilldownTreeParser(
    WebDrilldownTreeConfig(
        profile_name=PROFILE_NAME,
        root_segment="ubl-invoice",
        root_name="ubl:Invoice",
    )
)


def extract(source: str | Path) -> list[dict[str, object]]:
    return PARSER.extract(source)
