from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve()
SKILL_ROOT = SCRIPT_PATH.parents[1]
REPO_ROOT = SCRIPT_PATH.parents[4]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(SKILL_ROOT) not in sys.path:
    sys.path.insert(0, str(SKILL_ROOT))

from skill_registry import find_registry_entry, resolve_baseline_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Promote a verified field catalog to the skill's trusted baseline store."
    )
    parser.add_argument("--extractor", required=True, help="Extractor name from the skill registry.")
    parser.add_argument("--source", required=True, help="Path to a verified field_catalog.json.")
    parser.add_argument("--note", help="Optional note recorded in baseline_meta.json.")
    parser.add_argument("--force", action="store_true", help="Overwrite an existing baseline.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    registry_entry = find_registry_entry(args.extractor)
    if registry_entry is None:
        raise SystemExit(f"Extractor '{args.extractor}' was not found in the skill registry.")

    source_path = Path(args.source).expanduser().resolve()
    if not source_path.exists():
        raise SystemExit(f"Source catalog not found: {source_path}")

    baseline_path = resolve_baseline_path(registry_entry)
    if baseline_path is None:
        raise SystemExit(f"Extractor '{args.extractor}' does not have a resolvable baseline location.")
    baseline_path = baseline_path.resolve()
    baseline_dir = baseline_path.parent
    baseline_dir.mkdir(parents=True, exist_ok=True)

    if baseline_path.exists() and not args.force:
        raise SystemExit(f"Baseline already exists: {baseline_path}. Use --force to overwrite it.")

    shutil.copyfile(source_path, baseline_path)

    meta = {
        "extractor": args.extractor,
        "family": registry_entry.get("family", ""),
        "jurisdiction": registry_entry.get("jurisdiction", ""),
        "tax_domain": registry_entry.get("tax_domain", ""),
        "document_language": registry_entry.get("document_language", ""),
        "source_catalog": str(source_path),
        "promoted_at_utc": datetime.now(timezone.utc).isoformat(),
        "note": args.note or "",
    }
    meta_path = baseline_dir / "baseline_meta.json"
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"baseline: {baseline_path}")
    print(f"meta: {meta_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
