from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any


SCRIPT_PATH = Path(__file__).resolve()
SKILL_ROOT = SCRIPT_PATH.parents[1]
if str(SKILL_ROOT) not in sys.path:
    sys.path.insert(0, str(SKILL_ROOT))

from skill_registry import find_registry_entry
from runtime_python import resolve_project_python


TEST_SCRIPT = SKILL_ROOT / "scripts" / "test_extractor.py"
PROJECT_PYTHON = resolve_project_python(SKILL_ROOT.parent.parent, sys.executable)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the tax parser quality gate with stable vs experimental policies."
    )
    parser.add_argument("--pdf", required=True, help="Path to the target PDF.")
    parser.add_argument("--extractor", required=True, help="Extractor name from the skill registry.")
    parser.add_argument("--outdir", required=True, help="Directory for test outputs.")
    parser.add_argument(
        "--pack-dir",
        help="Optional pack root directory. When provided, load registries and baselines from that pack.",
    )
    parser.add_argument("--baseline", help="Optional override baseline.")
    parser.add_argument(
        "--allow-changed",
        type=int,
        default=0,
        help="Allowed changed field count for stable profiles. Default is 0.",
    )
    parser.add_argument(
        "--allow-missing",
        type=int,
        default=0,
        help="Allowed missing field count for stable profiles. Default is 0.",
    )
    parser.add_argument(
        "--allow-extra",
        type=int,
        default=0,
        help="Allowed extra field count for stable profiles. Default is 0.",
    )
    return parser.parse_args()


def extract_json(text: str) -> dict[str, Any] | None:
    stripped = text.strip()
    if not stripped:
        return None
    try:
        payload = json.loads(stripped)
    except json.JSONDecodeError:
        start = stripped.find("{")
        end = stripped.rfind("}")
        if start == -1 or end == -1 or end <= start:
            return None
        try:
            payload = json.loads(stripped[start : end + 1])
        except json.JSONDecodeError:
            return None
    return payload if isinstance(payload, dict) else None


def read_diff_summary(report: dict[str, Any]) -> dict[str, int] | None:
    compare = report.get("compare")
    if not isinstance(compare, dict):
        return None
    diff_outdir = compare.get("diff_outdir")
    if not diff_outdir:
        return None
    diff_path = Path(str(diff_outdir)) / "catalog_diff.json"
    if not diff_path.exists():
        return None
    payload = json.loads(diff_path.read_text(encoding="utf-8"))
    summary = payload.get("summary")
    return summary if isinstance(summary, dict) else None


def main() -> int:
    args = parse_args()
    pack_dir = Path(args.pack_dir).expanduser().resolve() if args.pack_dir else None
    entry = find_registry_entry(args.extractor, pack_dir=pack_dir)
    if entry is None:
        raise SystemExit(f"Extractor '{args.extractor}' was not found in the skill registry.")

    stability = str(entry.get("stability", "")).strip() or "experimental"
    command = [
        PROJECT_PYTHON,
        str(TEST_SCRIPT),
        "--pdf",
        str(Path(args.pdf).expanduser().resolve()),
        "--extractor",
        args.extractor,
        "--outdir",
        str(Path(args.outdir).expanduser().resolve()),
    ]
    if pack_dir:
        command.extend(["--pack-dir", str(pack_dir)])
    if args.baseline:
        command.extend(["--baseline", str(Path(args.baseline).expanduser().resolve())])

    result = subprocess.run(command, check=False, capture_output=True, text=True)
    report = extract_json(result.stdout) or {
        "parse_error": True,
        "stdout": result.stdout,
        "stderr": result.stderr,
    }
    diff_summary = read_diff_summary(report)

    reasons: list[str] = []
    for section in ["compile", "run", "validate"]:
        payload = report.get(section)
        if not isinstance(payload, dict) or not payload.get("ok"):
            reasons.append(f"{section} failed")

    if stability == "stable":
        if diff_summary is None:
            reasons.append("stable profile requires baseline comparison")
        else:
            if int(diff_summary.get("missing_count", 0)) > args.allow_missing:
                reasons.append("missing field count exceeds gate")
            if int(diff_summary.get("extra_count", 0)) > args.allow_extra:
                reasons.append("extra field count exceeds gate")
            if int(diff_summary.get("changed_count", 0)) > args.allow_changed:
                reasons.append("changed field count exceeds gate")

    status = "pass" if not reasons and result.returncode == 0 else "fail"
    payload = {
        "status": status,
        "extractor": args.extractor,
        "pack_dir": str(pack_dir) if pack_dir else "",
        "stability": stability,
        "gate_command": command,
        "test_report": report,
        "diff_summary": diff_summary,
        "reasons": reasons,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if status == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
