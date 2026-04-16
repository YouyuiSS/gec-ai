from __future__ import annotations

import argparse
import json
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve()
REPO_ROOT = SCRIPT_PATH.parents[2]
SKILL_ROOT = REPO_ROOT / ".opencode" / "skills" / "tax-law-parser"
BASELINES_ROOT = SKILL_ROOT / "baselines"
PROFILES_ROOT = SKILL_ROOT / "profiles"
DOCS_ROOT = REPO_ROOT / "docs"
AGENTS_FILE = REPO_ROOT / "AGENTS.md"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Check whether planned parser edits stay within the allowed tax skill scope."
    )
    parser.add_argument("--path", action="append", required=True, help="File path that the agent intends to edit.")
    parser.add_argument(
        "--allow-family-base-writes",
        action="store_true",
        help="Allow edits to profiles/families/*/base.py.",
    )
    parser.add_argument(
        "--allow-baseline-writes",
        action="store_true",
        help="Allow edits to baselines/.",
    )
    return parser.parse_args()


def is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def classify_path(path: Path, *, allow_family_base_writes: bool, allow_baseline_writes: bool) -> tuple[bool, str]:
    if not path.exists():
        resolved = path
    else:
        resolved = path.resolve()

    allowed_roots = [SKILL_ROOT, DOCS_ROOT]
    allowed_files = {AGENTS_FILE.resolve()}

    if resolved in allowed_files:
        return True, "allowed repo control file"

    if not any(is_relative_to(resolved, root.resolve()) for root in allowed_roots):
        return False, "outside allowed tax skill and docs scope"

    if is_relative_to(resolved, BASELINES_ROOT.resolve()) and not allow_baseline_writes:
        return False, "baseline writes require explicit approval"

    if resolved.name == "base.py" and is_relative_to(resolved, PROFILES_ROOT.resolve()) and not allow_family_base_writes:
        return False, "family base edits require explicit opt-in"

    return True, "allowed"


def main() -> int:
    args = parse_args()
    allowed: list[dict[str, str]] = []
    blocked: list[dict[str, str]] = []

    for raw_path in args.path:
        path = Path(raw_path).expanduser()
        if not path.is_absolute():
            path = (REPO_ROOT / path).resolve()
        ok, reason = classify_path(
            path,
            allow_family_base_writes=args.allow_family_base_writes,
            allow_baseline_writes=args.allow_baseline_writes,
        )
        item = {"path": str(path), "reason": reason}
        if ok:
            allowed.append(item)
        else:
            blocked.append(item)

    payload = {
        "repo_root": str(REPO_ROOT),
        "allowed": allowed,
        "blocked": blocked,
        "ok": not blocked,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if not blocked else 1


if __name__ == "__main__":
    raise SystemExit(main())
