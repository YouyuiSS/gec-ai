from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve()
SKILL_ROOT = SCRIPT_PATH.parents[1]
REPO_ROOT = SCRIPT_PATH.parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(SKILL_ROOT) not in sys.path:
    sys.path.insert(0, str(SKILL_ROOT))

from tax_parser_runtime.python_exec import resolve_project_python
from tax_parser_runtime.registry import describe_registry_module, find_registry_entry, resolve_baseline_path, resolve_module_path


PROJECT_PYTHON = resolve_project_python(REPO_ROOT, sys.executable)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compile, run, validate, and optionally compare a tax-law-parser extractor."
    )
    parser.add_argument("--pdf", required=True, help="Path to the target tax regulation PDF.")
    parser.add_argument("--extractor", required=True, help="Extractor name from the skill registry.")
    parser.add_argument("--outdir", required=True, help="Directory for parser outputs.")
    parser.add_argument(
        "--pack-dir",
        help="Optional pack root directory. When provided, load registries and baselines from that pack.",
    )
    parser.add_argument(
        "--baseline",
        help="Optional trusted baseline field_catalog.json for diff comparison.",
    )
    parser.add_argument(
        "--diff-outdir",
        help="Optional directory for diff outputs. Defaults to <outdir>/diff when --baseline is provided.",
    )
    return parser.parse_args()


def run_command(command: list[str]) -> tuple[int, str]:
    result = subprocess.run(command, check=False, capture_output=True, text=True)
    output = "\n".join(part for part in [result.stdout, result.stderr] if part).strip()
    return result.returncode, output


def main() -> int:
    args = parse_args()
    pdf_path = Path(args.pdf).expanduser().resolve()
    outdir = Path(args.outdir).expanduser().resolve()
    pack_dir = Path(args.pack_dir).expanduser().resolve() if args.pack_dir else None
    baseline_path = Path(args.baseline).expanduser().resolve() if args.baseline else None
    diff_outdir = (
        Path(args.diff_outdir).expanduser().resolve()
        if args.diff_outdir
        else outdir / "diff"
    )

    registry_entry = find_registry_entry(args.extractor, pack_dir=pack_dir)
    if registry_entry is None:
        raise SystemExit(f"Extractor '{args.extractor}' was not found in the skill registry.")

    module_import_name = describe_registry_module(registry_entry)
    module_path = resolve_module_path(registry_entry)
    baseline_source = "explicit" if baseline_path else "auto"
    if baseline_path is None:
        candidate_baseline = resolve_baseline_path(registry_entry)
        if candidate_baseline and candidate_baseline.exists():
            baseline_path = candidate_baseline.resolve()
        else:
            baseline_path = None
            baseline_source = "missing"
    elif not baseline_path.exists():
        raise SystemExit(f"Baseline file not found: {baseline_path}")

    report: dict[str, object] = {
        "extractor": args.extractor,
        "family": registry_entry.get("family", ""),
        "jurisdiction": registry_entry.get("jurisdiction", ""),
        "pack_dir": str(pack_dir) if pack_dir else "",
        "python_executable": PROJECT_PYTHON,
        "module_import": module_import_name,
        "module_path": str(module_path),
        "pdf_path": str(pdf_path),
        "outdir": str(outdir),
        "baseline_path": str(baseline_path) if baseline_path else "",
        "baseline_source": baseline_source,
        "compile": None,
        "run": None,
        "validate": None,
        "compare": None,
    }

    compile_code, compile_output = run_command([PROJECT_PYTHON, "-m", "py_compile", str(module_path)])
    report["compile"] = {
        "ok": compile_code == 0,
        "output": compile_output,
    }
    if compile_code != 0:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 1

    run_script = SKILL_ROOT / "scripts" / "run_tax_parser.py"
    run_code, run_output = run_command(
        [
            PROJECT_PYTHON,
            str(run_script),
            "--pdf",
            str(pdf_path),
            "--outdir",
            str(outdir),
            "--extractor",
            args.extractor,
        ]
        + (["--pack-dir", str(pack_dir)] if pack_dir else [])
    )
    report["run"] = {
        "ok": run_code == 0,
        "output": run_output,
    }
    if run_code != 0:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 1

    validate_script = SKILL_ROOT / "scripts" / "validate_tax_output.py"
    validate_code, validate_output = run_command(
        [
            PROJECT_PYTHON,
            str(validate_script),
            "--json",
            str(outdir / "field_catalog.json"),
        ]
    )
    report["validate"] = {
        "ok": validate_code == 0,
        "output": validate_output,
    }
    if validate_code != 0:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 1

    if baseline_path:
        compare_script = SKILL_ROOT / "scripts" / "compare_field_catalogs.py"
        compare_code, compare_output = run_command(
            [
                PROJECT_PYTHON,
                str(compare_script),
                "--baseline",
                str(baseline_path),
                "--candidate",
                str(outdir / "field_catalog.json"),
                "--outdir",
                str(diff_outdir),
            ]
        )
        report["compare"] = {
            "ok": compare_code == 0,
            "output": compare_output,
            "diff_outdir": str(diff_outdir),
        }
        if compare_code != 0:
            print(json.dumps(report, ensure_ascii=False, indent=2))
            return 1

    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
