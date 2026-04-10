from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve()
SKILL_ROOT = SCRIPT_PATH.parents[1]
if str(SKILL_ROOT) not in sys.path:
    sys.path.insert(0, str(SKILL_ROOT))

from skill_registry import LEGACY_REGISTRY_PATH, PROFILES_REGISTRY_PATH, find_registry_entry

EXTRACTORS_DIR = SKILL_ROOT / "extractors"
LEGACY_TEMPLATE_PATH = EXTRACTORS_DIR / "template_generic.py"
PROFILES_DIR = SKILL_ROOT / "profiles"
FAMILIES_DIR = PROFILES_DIR / "families"


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
    parser.add_argument(
        "--family",
        help="Optional parser family. When provided, scaffold a family overlay under profiles/families/<family>/.",
    )
    parser.add_argument("--jurisdiction", help="Optional jurisdiction code, for example HR or RS.")
    parser.add_argument("--tax-domain", help="Optional tax domain label, for example einvoice.")
    parser.add_argument("--language", help="Optional document language code, for example en or sr.")
    return parser.parse_args()


def slug_to_module(name: str) -> str:
    if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", name):
        raise SystemExit("Extractor name must use lowercase letters, digits, and single hyphens only.")
    return name.replace("-", "_")


def main() -> int:
    args = parse_args()
    module_name = slug_to_module(args.name)
    if find_registry_entry(args.name):
        raise SystemExit(f"Extractor '{args.name}' already exists in the skill registry.")

    if args.family:
        family_dir = FAMILIES_DIR / args.family
        template_path = family_dir / "template_overlay.py"
        if not template_path.exists():
            raise SystemExit(f"Family template not found: {template_path}")
        target_path = family_dir / f"{module_name}.py"
        registry_path = PROFILES_REGISTRY_PATH
        module_import = f"profiles.families.{args.family}.{module_name}"
    else:
        template_path = LEGACY_TEMPLATE_PATH
        target_path = EXTRACTORS_DIR / f"{module_name}.py"
        registry_path = LEGACY_REGISTRY_PATH
        module_import = module_name

    if target_path.exists():
        raise SystemExit(f"Extractor already exists: {target_path}")

    template = template_path.read_text(encoding="utf-8")
    template = template.replace('PROFILE_NAME = "template-generic"', f'PROFILE_NAME = "{args.name}"')
    template = template.replace('PROFILE_NAME = "template-overlay"', f'PROFILE_NAME = "{args.name}"')
    target_path.write_text(template, encoding="utf-8")

    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    entry = {
        "name": args.name,
        "module": module_import,
        "description": args.description,
        "filename_contains": args.filename_hint,
        "text_contains": args.text_hint,
    }
    if args.family:
        entry.update(
            {
                "family": args.family,
                "jurisdiction": args.jurisdiction or "",
                "tax_domain": args.tax_domain or "",
                "document_language": args.language or "",
            }
        )
    registry.append(entry)
    registry_path.write_text(json.dumps(registry, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"created extractor: {target_path}")
    print(f"updated registry: {registry_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
