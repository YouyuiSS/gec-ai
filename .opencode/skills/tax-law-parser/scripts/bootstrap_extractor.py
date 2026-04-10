from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve()
SKILL_ROOT = SCRIPT_PATH.parents[1]
EXTRACTORS_DIR = SKILL_ROOT / "extractors"
REGISTRY_PATH = EXTRACTORS_DIR / "registry.json"
TEMPLATE_PATH = EXTRACTORS_DIR / "template_generic.py"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Scaffold a new tax-law-parser extractor.")
    parser.add_argument("--name", required=True, help="Skill extractor name, for example hr-v2-layout.")
    parser.add_argument("--description", required=True, help="Short registry description.")
    parser.add_argument(
        "--filename-hint",
        action="append",
        default=[],
        help="Substring expected in matching PDF filenames. May be repeated.",
    )
    parser.add_argument(
        "--text-hint",
        action="append",
        default=[],
        help="Substring expected in the first few PDF pages. May be repeated.",
    )
    return parser.parse_args()


def slug_to_module(name: str) -> str:
    if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", name):
        raise SystemExit("Extractor name must use lowercase letters, digits, and single hyphens only.")
    return name.replace("-", "_")


def main() -> int:
    args = parse_args()
    module_name = slug_to_module(args.name)
    target_path = EXTRACTORS_DIR / f"{module_name}.py"
    if target_path.exists():
        raise SystemExit(f"Extractor already exists: {target_path}")

    template = TEMPLATE_PATH.read_text(encoding="utf-8")
    template = template.replace('PROFILE_NAME = "template-generic"', f'PROFILE_NAME = "{args.name}"')
    target_path.write_text(template, encoding="utf-8")

    registry = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    registry.append(
        {
            "name": args.name,
            "module": module_name,
            "description": args.description,
            "filename_contains": args.filename_hint,
            "text_contains": args.text_hint,
        }
    )
    REGISTRY_PATH.write_text(json.dumps(registry, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"created extractor: {target_path}")
    print(f"updated registry: {REGISTRY_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
