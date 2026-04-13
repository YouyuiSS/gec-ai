from __future__ import annotations

from pathlib import Path

from .base import WebInlineTableConfig, WebInlineTableParser


PROFILE_NAME = "myinvois-invoice-v1-1-web"

PARSER = WebInlineTableParser(
    WebInlineTableConfig(
        profile_name=PROFILE_NAME,
    )
)


def extract(source: str | Path) -> list[dict[str, object]]:
    return PARSER.extract(source)
