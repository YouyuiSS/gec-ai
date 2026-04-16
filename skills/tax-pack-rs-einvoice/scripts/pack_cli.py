from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve()
PACK_DIR = SCRIPT_PATH.parents[1]
SKILLS_ROOT = PACK_DIR.parent
CORE_DIR = SKILLS_ROOT / "tax-parser-core"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the Serbia eInvoice pack via tax-parser-core.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run")
    run_parser.add_argument("--pdf", required=True)
    run_parser.add_argument("--outdir", required=True)
    run_parser.add_argument("--extractor")

    test_parser = subparsers.add_parser("test")
    test_parser.add_argument("--pdf", required=True)
    test_parser.add_argument("--extractor", default="rs-srbdt-ext-2025")
    test_parser.add_argument("--outdir", required=True)

    monitor = subparsers.add_parser("monitor")
    monitor.add_argument("--outdir", required=True)

    followups = subparsers.add_parser("followups")
    followups.add_argument("--followups", required=True)
    followups.add_argument("--outdir", required=True)
    followups.add_argument("--runner", default="test_extractor")
    followups.add_argument("--max-items")

    gate = subparsers.add_parser("quality-gate")
    gate.add_argument("--pdf", required=True)
    gate.add_argument("--extractor", default="rs-srbdt-ext-2025")
    gate.add_argument("--outdir", required=True)

    return parser.parse_args()


def core_script(name: str) -> Path:
    path = CORE_DIR / "scripts" / name
    if not path.exists():
        raise SystemExit(f"Required core script not found: {path}")
    return path


def build_command(args: argparse.Namespace) -> list[str]:
    if args.command == "run":
        command = [
            sys.executable,
            str(core_script("run_tax_parser.py")),
            "--pack-dir",
            str(PACK_DIR),
            "--pdf",
            str(Path(args.pdf).expanduser().resolve()),
            "--outdir",
            str(Path(args.outdir).expanduser().resolve()),
        ]
        if args.extractor:
            command.extend(["--extractor", args.extractor])
        return command

    if args.command == "test":
        return [
            sys.executable,
            str(core_script("test_extractor.py")),
            "--pack-dir",
            str(PACK_DIR),
            "--pdf",
            str(Path(args.pdf).expanduser().resolve()),
            "--extractor",
            args.extractor,
            "--outdir",
            str(Path(args.outdir).expanduser().resolve()),
        ]

    if args.command == "monitor":
        return [
            sys.executable,
            str(core_script("monitor_official_sources.py")),
            "--pack-dir",
            str(PACK_DIR),
            "--outdir",
            str(Path(args.outdir).expanduser().resolve()),
        ]

    if args.command == "followups":
        command = [
            sys.executable,
            str(core_script("run_source_followups.py")),
            "--pack-dir",
            str(PACK_DIR),
            "--followups",
            str(Path(args.followups).expanduser().resolve()),
            "--runner",
            args.runner,
            "--outdir",
            str(Path(args.outdir).expanduser().resolve()),
        ]
        if args.max_items:
            command.extend(["--max-items", str(args.max_items)])
        return command

    if args.command == "quality-gate":
        return [
            sys.executable,
            str(core_script("quality_gate.py")),
            "--pack-dir",
            str(PACK_DIR),
            "--pdf",
            str(Path(args.pdf).expanduser().resolve()),
            "--extractor",
            args.extractor,
            "--outdir",
            str(Path(args.outdir).expanduser().resolve()),
        ]

    raise SystemExit(f"Unsupported command: {args.command}")


def main() -> int:
    args = parse_args()
    command = build_command(args)
    result = subprocess.run(command, check=False)
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
