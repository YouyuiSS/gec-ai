from __future__ import annotations

import argparse
import json
import shlex
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCRIPT_PATH = Path(__file__).resolve()
SKILL_ROOT = SCRIPT_PATH.parents[1]
REPO_ROOT = SCRIPT_PATH.parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(SKILL_ROOT) not in sys.path:
    sys.path.insert(0, str(SKILL_ROOT))

from tax_parser_runtime.python_exec import resolve_project_python
from tax_parser_runtime.registry import find_registry_entry


PROJECT_PYTHON = resolve_project_python(REPO_ROOT, sys.executable)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Execute actionable source-monitor follow-ups against skill scripts or the tax pipeline."
    )
    parser.add_argument("--followups", required=True, help="Path to followups.json from source monitoring.")
    parser.add_argument("--outdir", required=True, help="Directory for execution logs and summary files.")
    parser.add_argument(
        "--pack-dir",
        help="Optional pack root directory. When provided, load registries and baselines from that pack.",
    )
    parser.add_argument(
        "--runner",
        choices=["test_extractor", "tax_pipeline", "suggested"],
        default="test_extractor",
        help="Execution backend to use for actionable follow-ups.",
    )
    parser.add_argument(
        "--source-id",
        action="append",
        default=[],
        help="Optional source_id filter. May be repeated.",
    )
    parser.add_argument(
        "--max-items",
        type=int,
        help="Optional maximum number of actionable follow-ups to process.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Write the execution plan without launching commands.",
    )
    parser.add_argument(
        "--fail-on-run-error",
        action="store_true",
        help="Exit non-zero if any launched command fails.",
    )
    parser.add_argument(
        "--version-label-prefix",
        default="source-monitor",
        help="Version label prefix when runner=tax_pipeline.",
    )
    return parser.parse_args()


def load_followups(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise SystemExit(f"{path} is not a JSON array.")
    return [item for item in payload if isinstance(item, dict)]


def slugify(value: str) -> str:
    chars = []
    for char in value:
        if char.isalnum() or char in {"-", "_", "."}:
            chars.append(char)
        else:
            chars.append("-")
    return "".join(chars).strip("-._") or "item"


def sanitize_version_component(value: str) -> str:
    slug = slugify(value).replace(".", "-")
    return slug[:48] or "snapshot"


def actionable(followup: dict[str, Any], runner: str) -> bool:
    if runner == "suggested":
        return bool(str(followup.get("suggested_command", "")).strip())

    if followup.get("source_kind") != "specification":
        return False

    attachment_path = str(followup.get("artifact_paths", {}).get("attachment_path", "")).strip()
    if not attachment_path:
        return False

    recommended_profile = followup.get("recommended_profile") or {}
    extractor_name = str(recommended_profile.get("name", "")).strip()
    if runner == "test_extractor":
        return bool(extractor_name)

    if runner == "tax_pipeline":
        jurisdiction = str(followup.get("jurisdiction", "")).strip()
        tax_domain = str(followup.get("tax_domain", "")).strip()
        return bool(jurisdiction and tax_domain)

    return False


def filter_followups(
    followups: list[dict[str, Any]],
    *,
    source_ids: set[str],
    runner: str,
    max_items: int | None,
) -> list[dict[str, Any]]:
    filtered: list[dict[str, Any]] = []
    for item in followups:
        source_id = str(item.get("source_id", "")).strip()
        if source_ids and source_id not in source_ids:
            continue
        if not actionable(item, runner):
            continue
        filtered.append(item)
        if max_items is not None and len(filtered) >= max_items:
            break
    return filtered


def build_test_extractor_command(followup: dict[str, Any], run_dir: Path, pack_dir: Path | None) -> list[str]:
    attachment_path = str(followup["artifact_paths"]["attachment_path"]).strip()
    extractor_name = str((followup.get("recommended_profile") or {}).get("name", "")).strip()
    if not attachment_path or not extractor_name:
        raise RuntimeError("test_extractor follow-up requires attachment_path and recommended_profile.name.")
    command = [
        PROJECT_PYTHON,
        str(SKILL_ROOT / "scripts" / "test_extractor.py"),
        "--pdf",
        attachment_path,
        "--extractor",
        extractor_name,
        "--outdir",
        str(run_dir / "parser_output"),
    ]
    if pack_dir:
        command.extend(["--pack-dir", str(pack_dir)])
    return command


def build_tax_pipeline_command(
    followup: dict[str, Any],
    run_dir: Path,
    version_label_prefix: str,
    pack_dir: Path | None,
) -> list[str]:
    attachment_path = str(followup["artifact_paths"]["attachment_path"]).strip()
    jurisdiction = str(followup.get("jurisdiction", "")).strip()
    tax_domain = str(followup.get("tax_domain", "")).strip()
    recommended_profile = followup.get("recommended_profile") or {}
    registry_entry = (
        find_registry_entry(str(recommended_profile.get("name", "")).strip(), pack_dir=pack_dir)
        if recommended_profile.get("name")
        else None
    )
    language_code = "en" if registry_entry is None else str(registry_entry.get("document_language", "en")).strip() or "en"
    version_label = (
        f"{sanitize_version_component(version_label_prefix)}-"
        f"{sanitize_version_component(str(followup.get('source_id', 'source')))}-"
        f"{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
    )
    return [
        PROJECT_PYTHON,
        "-m",
        "tax_pipeline",
        "--pdf",
        attachment_path,
        "--jurisdiction",
        jurisdiction,
        "--tax-domain",
        tax_domain,
        "--language-code",
        language_code,
        "--version-label",
        version_label,
        "--outdir",
        str(run_dir / "pipeline_output"),
    ]


def build_suggested_command(followup: dict[str, Any]) -> list[str]:
    command = str(followup.get("suggested_command", "")).strip()
    if not command:
        raise RuntimeError("suggested runner requires suggested_command.")
    return shlex.split(command)


def build_command(
    followup: dict[str, Any],
    *,
    runner: str,
    run_dir: Path,
    version_label_prefix: str,
    pack_dir: Path | None,
) -> list[str]:
    if runner == "test_extractor":
        return build_test_extractor_command(followup, run_dir, pack_dir)
    if runner == "tax_pipeline":
        return build_tax_pipeline_command(followup, run_dir, version_label_prefix, pack_dir)
    if runner == "suggested":
        return build_suggested_command(followup)
    raise RuntimeError(f"Unsupported runner: {runner}")


def execute_command(command: list[str], *, dry_run: bool) -> tuple[int | None, str, str]:
    if dry_run:
        return None, "", ""
    result = subprocess.run(command, check=False, capture_output=True, text=True)
    return result.returncode, result.stdout, result.stderr


def parse_json_output(text: str) -> dict[str, Any] | None:
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


def summarize_failure(parsed_output: dict[str, Any] | None, stdout: str, stderr: str) -> str:
    if parsed_output:
        for key in ("run", "validate", "compare", "compile"):
            section = parsed_output.get(key)
            if isinstance(section, dict) and section.get("ok") is False:
                output = str(section.get("output", "")).strip()
                if output:
                    return output.splitlines()[-1]
        if parsed_output.get("parse_error"):
            return "parse_error"
    combined = "\n".join(part for part in [stdout, stderr] if part).strip()
    return combined.splitlines()[-1] if combined else ""


def write_execution_artifacts(
    *,
    run_dir: Path,
    command: list[str],
    returncode: int | None,
    stdout: str,
    stderr: str,
    parsed_output: dict[str, Any] | None,
) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "stdout.txt").write_text(stdout, encoding="utf-8")
    (run_dir / "stderr.txt").write_text(stderr, encoding="utf-8")
    (run_dir / "command.json").write_text(
        json.dumps(
            {
                "command": command,
                "returncode": returncode,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    if parsed_output is not None:
        (run_dir / "parsed_output.json").write_text(
            json.dumps(parsed_output, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


def build_markdown_summary(summary_payload: dict[str, Any]) -> str:
    lines = [
        "# Source Follow-up Execution",
        "",
        "## Summary",
        "",
        f"- Runner: {summary_payload['runner']}",
        f"- Dry run: {summary_payload['dry_run']}",
        f"- Selected items: {summary_payload['selected_count']}",
        f"- Executed items: {summary_payload['executed_count']}",
        f"- Failed items: {summary_payload['failed_count']}",
        "",
    ]

    for item in summary_payload["items"]:
        lines.extend(
            [
                f"## {item['source_id']}",
                "",
                f"- Status: {item['status']}",
                f"- Suggested action: {item['suggested_action']}",
                f"- Run dir: {item['run_dir']}",
                f"- Return code: {item['returncode'] if item['returncode'] is not None else 'dry-run'}",
                f"- Command: `{item['command_text']}`",
            ]
        )
        if item.get("failure_summary"):
            lines.append(f"- Failure summary: {item['failure_summary']}")
        if item.get("artifact_attachment_path"):
            lines.append(f"- Attachment: {item['artifact_attachment_path']}")
        if item.get("artifact_landing_path"):
            lines.append(f"- Landing page: {item['artifact_landing_path']}")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def main() -> int:
    args = parse_args()
    pack_dir = Path(args.pack_dir).expanduser().resolve() if args.pack_dir else None
    followups_path = Path(args.followups).expanduser().resolve()
    outdir = Path(args.outdir).expanduser().resolve()
    outdir.mkdir(parents=True, exist_ok=True)

    selected = filter_followups(
        load_followups(followups_path),
        source_ids=set(args.source_id),
        runner=args.runner,
        max_items=args.max_items,
    )
    if not selected:
        raise SystemExit("No actionable follow-ups matched the requested filters and runner.")

    items: list[dict[str, Any]] = []
    failed_count = 0
    executed_count = 0

    for followup in selected:
        source_id = str(followup.get("source_id", "")).strip()
        run_dir = outdir / "runs" / slugify(source_id) / args.runner
        command = build_command(
            followup,
            runner=args.runner,
            run_dir=run_dir,
            version_label_prefix=args.version_label_prefix,
            pack_dir=pack_dir,
        )
        returncode, stdout, stderr = execute_command(command, dry_run=args.dry_run)
        parsed_output = parse_json_output(stdout)
        write_execution_artifacts(
            run_dir=run_dir,
            command=command,
            returncode=returncode,
            stdout=stdout,
            stderr=stderr,
            parsed_output=parsed_output,
        )

        if returncode is not None:
            executed_count += 1
        status = "dry_run" if returncode is None else ("ok" if returncode == 0 else "failed")
        if status == "failed":
            failed_count += 1
        failure_summary = summarize_failure(parsed_output, stdout, stderr) if status == "failed" else ""

        items.append(
            {
                "source_id": source_id,
                "status": status,
                "suggested_action": str(followup.get("suggested_action", "")).strip(),
                "run_dir": str(run_dir),
                "command": command,
                "command_text": " ".join(shlex.quote(part) for part in command),
                "returncode": returncode,
                "failure_summary": failure_summary,
                "artifact_attachment_path": str(followup.get("artifact_paths", {}).get("attachment_path", "")).strip(),
                "artifact_landing_path": str(followup.get("artifact_paths", {}).get("landing_path", "")).strip(),
            }
        )

    summary_payload = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "followups_path": str(followups_path),
        "runner": args.runner,
        "dry_run": args.dry_run,
        "selected_count": len(selected),
        "executed_count": executed_count,
        "failed_count": failed_count,
        "items": items,
    }

    summary_json_path = outdir / "execution_summary.json"
    summary_md_path = outdir / "execution_summary.md"
    summary_json_path.write_text(json.dumps(summary_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    summary_md_path.write_text(build_markdown_summary(summary_payload), encoding="utf-8")

    print(f"runner: {args.runner}")
    print(f"selected: {len(selected)}")
    print(f"executed: {executed_count}")
    print(f"failed: {failed_count}")
    print(f"summary_json: {summary_json_path}")
    print(f"summary_markdown: {summary_md_path}")

    if args.fail_on_run_error and failed_count:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
