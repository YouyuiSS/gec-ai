from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve()
SKILL_ROOT = SCRIPT_PATH.parents[1]
EXTRACTORS_DIR = SKILL_ROOT / "extractors"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compile, run, validate, and optionally compare a tax-law-parser extractor."
    )
    parser.add_argument("--pdf", required=True, help="Path to the target tax regulation PDF.")
    parser.add_argument("--extractor", required=True, help="Extractor name from registry.json.")
    parser.add_argument("--outdir", required=True, help="Directory for parser outputs.")
    parser.add_argument(
        "--baseline",
        help="Optional trusted baseline field_catalog.json for diff comparison.",
    )
    parser.add_argument(
        "--diff-outdir",
        help="Optional directory for diff outputs. Defaults to <outdir>/diff when --baseline is provided.",
    )
    return parser.parse_args()


def extractor_module_path(extractor_name: str) -> Path:
    module_name = extractor_name.replace("-", "_")
    return EXTRACTORS_DIR / f"{module_name}.py"


def run_command(command: list[str]) -> tuple[int, str]:
    result = subprocess.run(command, check=False, capture_output=True, text=True)
    output = "\n".join(part for part in [result.stdout, result.stderr] if part).strip()
    return result.returncode, output


def main() -> int:
    args = parse_args()
    pdf_path = Path(args.pdf).expanduser().resolve()
    outdir = Path(args.outdir).expanduser().resolve()
    baseline_path = Path(args.baseline).expanduser().resolve() if args.baseline else None
    diff_outdir = (
        Path(args.diff_outdir).expanduser().resolve()
        if args.diff_outdir
        else outdir / "diff"
    )

    module_path = extractor_module_path(args.extractor)
    if not module_path.exists():
        raise SystemExit(f"Extractor module not found: {module_path}")

    report: dict[str, object] = {
        "extractor": args.extractor,
        "module_path": str(module_path),
        "pdf_path": str(pdf_path),
        "outdir": str(outdir),
        "compile": None,
        "run": None,
        "validate": None,
        "compare": None,
    }

    compile_code, compile_output = run_command([sys.executable, "-m", "py_compile", str(module_path)])
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
            sys.executable,
            str(run_script),
            "--pdf",
            str(pdf_path),
            "--outdir",
            str(outdir),
            "--extractor",
            args.extractor,
        ]
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
            sys.executable,
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
                sys.executable,
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
