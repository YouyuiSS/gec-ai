from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any


SCRIPT_PATH = Path(__file__).resolve()
SKILL_ROOT = SCRIPT_PATH.parents[1]
TEST_SCRIPT = SKILL_ROOT / "scripts" / "test_extractor.py"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate a deterministic repair brief for a tax-law-parser extractor."
    )
    parser.add_argument("--pdf", required=True, help="Path to the target tax regulation PDF.")
    parser.add_argument("--extractor", required=True, help="Extractor name from registry.json.")
    parser.add_argument("--outdir", required=True, help="Directory for run outputs and repair brief files.")
    parser.add_argument("--baseline", help="Optional trusted baseline field_catalog.json.")
    parser.add_argument(
        "--diff-outdir",
        help="Optional directory for diff outputs. Defaults to <outdir>/run/diff when --baseline is provided.",
    )
    parser.add_argument(
        "--max-samples",
        type=int,
        default=8,
        help="Maximum sample items to include per issue category.",
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


def run_test(
    *,
    pdf_path: Path,
    extractor: str,
    run_outdir: Path,
    baseline: Path | None,
    diff_outdir: Path | None,
) -> tuple[int, dict[str, Any], str, str]:
    command = [
        sys.executable,
        str(TEST_SCRIPT),
        "--pdf",
        str(pdf_path),
        "--extractor",
        extractor,
        "--outdir",
        str(run_outdir),
    ]
    if baseline:
        command.extend(["--baseline", str(baseline)])
    if diff_outdir:
        command.extend(["--diff-outdir", str(diff_outdir)])
    result = subprocess.run(command, check=False, capture_output=True, text=True)
    report = extract_json(result.stdout) or {
        "parse_error": True,
        "stdout": result.stdout,
        "stderr": result.stderr,
    }
    return result.returncode, report, result.stdout, result.stderr


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def load_candidate_catalog(run_outdir: Path) -> list[dict[str, Any]]:
    path = run_outdir / "field_catalog.json"
    if not path.exists():
        return []
    payload = load_json(path)
    return payload if isinstance(payload, list) else []


def load_diff_payload(report: dict[str, Any]) -> dict[str, Any] | None:
    compare = report.get("compare")
    if not isinstance(compare, dict):
        return None
    diff_outdir = compare.get("diff_outdir")
    if not isinstance(diff_outdir, str) or not diff_outdir:
        return None
    path = Path(diff_outdir) / "catalog_diff.json"
    if not path.exists():
        return None
    payload = load_json(path)
    return payload if isinstance(payload, dict) else None


def analyze_candidate_catalog(
    payload: list[dict[str, Any]],
    *,
    max_samples: int,
) -> dict[str, Any]:
    metrics = {
        "record_count": len(payload),
        "empty_name_ratio": 0.0,
        "empty_description_ratio": 0.0,
        "group_id_ratio": 0.0,
        "leader_dots_name_ratio": 0.0,
        "report_path_rule_ratio": 0.0,
        "path_coverage_ratio": 0.0,
    }
    issues: list[dict[str, Any]] = []
    if not payload:
        issues.append(
            {
                "code": "missing_output",
                "message": "field_catalog.json was not produced.",
                "samples": [],
                "recommendation": "Fix compile, run, or validator failures before semantic repair.",
            }
        )
        return {"metrics": metrics, "issues": issues}

    empty_name_ids: list[str] = []
    empty_description_ids: list[str] = []
    group_id_ids: list[str] = []
    leader_dot_ids: list[str] = []
    report_path_rule_ids: list[str] = []
    missing_path_ids: list[str] = []

    for item in payload:
        if not isinstance(item, dict):
            continue
        field_id = str(item.get("field_id", "")).strip()
        field_name = str(item.get("field_name", "")).strip()
        field_description = str(item.get("field_description", "")).strip()
        report_path = str(item.get("report_path", "")).strip()
        invoice_path = str(item.get("invoice_path", "")).strip()
        credit_note_path = str(item.get("credit_note_path", "")).strip()

        if not field_name:
            empty_name_ids.append(field_id)
        if not field_description:
            empty_description_ids.append(field_id)
        if field_id.startswith("BG-") or field_id.startswith("HR-BG-"):
            group_id_ids.append(field_id)
        if "...." in field_name or ". ." in field_name:
            leader_dot_ids.append(field_id)
        if report_path.startswith("BR-") or report_path.startswith("HR-BR-"):
            report_path_rule_ids.append(field_id)
        if not any([invoice_path, credit_note_path, report_path]):
            missing_path_ids.append(field_id)

    record_count = len(payload)
    metrics.update(
        {
            "empty_name_ratio": len(empty_name_ids) / record_count,
            "empty_description_ratio": len(empty_description_ids) / record_count,
            "group_id_ratio": len(group_id_ids) / record_count,
            "leader_dots_name_ratio": len(leader_dot_ids) / record_count,
            "report_path_rule_ratio": len(report_path_rule_ids) / record_count,
            "path_coverage_ratio": (record_count - len(missing_path_ids)) / record_count,
        }
    )

    if leader_dot_ids:
        issues.append(
            {
                "code": "field_name_toc_noise",
                "message": "Field names still contain table-of-contents dots or page-number artifacts.",
                "samples": leader_dot_ids[:max_samples],
                "recommendation": "Filter out TOC rows and strip trailing leader dots and page numbers before assigning field_name.",
            }
        )
    if group_id_ids:
        issues.append(
            {
                "code": "group_ids_emitted_as_fields",
                "message": "BG group identifiers were emitted as atomic fields.",
                "samples": group_id_ids[:max_samples],
                "recommendation": "Emit only atomic BT or HR-BT fields unless the document explicitly defines a BG node as a reportable field.",
            }
        )
    if report_path_rule_ids:
        issues.append(
            {
                "code": "rule_ids_used_as_report_path",
                "message": "Business rule identifiers were placed into report_path.",
                "samples": report_path_rule_ids[:max_samples],
                "recommendation": "Keep BR and HR-BR identifiers in rules only. report_path should contain invoice or credit-note reporting paths, or stay empty.",
            }
        )
    if missing_path_ids and metrics["path_coverage_ratio"] < 0.2:
        issues.append(
            {
                "code": "missing_paths",
                "message": "Too many records are missing invoice_path, credit_note_path, and report_path.",
                "samples": missing_path_ids[:max_samples],
                "recommendation": "Recover path rows from the table layout and keep path extraction separate from description text assembly.",
            }
        )
    if empty_name_ids and metrics["empty_name_ratio"] > 0.15:
        issues.append(
            {
                "code": "missing_names",
                "message": "Too many fields are missing field_name.",
                "samples": empty_name_ids[:max_samples],
                "recommendation": "Tighten heading and table column mapping so the first label cell becomes field_name instead of collapsing into description.",
            }
        )
    if empty_description_ids and metrics["empty_description_ratio"] > 0.15:
        issues.append(
            {
                "code": "missing_descriptions",
                "message": "Too many fields are missing field_description.",
                "samples": empty_description_ids[:max_samples],
                "recommendation": "Split name, description, and note-on-use more carefully instead of concatenating whole rows.",
            }
        )

    return {"metrics": metrics, "issues": issues}


def summarize_diff(diff_payload: dict[str, Any] | None, *, max_samples: int) -> dict[str, Any] | None:
    if not diff_payload:
        return None
    summary = diff_payload.get("summary", {})
    changed_fields = diff_payload.get("changed_fields", [])
    changed_samples: list[dict[str, Any]] = []
    for item in changed_fields[:max_samples]:
        if not isinstance(item, dict):
            continue
        changes = item.get("changes", [])
        compact_changes = []
        for change in changes[:3]:
            if not isinstance(change, dict):
                continue
            compact_changes.append(
                {
                    "key": change.get("key"),
                    "before": change.get("before"),
                    "after": change.get("after"),
                }
            )
        changed_samples.append({"field_id": item.get("field_id"), "changes": compact_changes})
    return {
        "summary": summary,
        "missing_samples": diff_payload.get("missing_field_ids", [])[:max_samples],
        "extra_samples": diff_payload.get("extra_field_ids", [])[:max_samples],
        "changed_samples": changed_samples,
    }


def build_recommendations(
    *,
    report: dict[str, Any],
    quality: dict[str, Any],
    diff_summary: dict[str, Any] | None,
) -> list[str]:
    recommendations: list[str] = []

    compile_payload = report.get("compile")
    run_payload = report.get("run")
    validate_payload = report.get("validate")
    if isinstance(compile_payload, dict) and not compile_payload.get("ok"):
        recommendations.append("Fix the Python syntax or import error first. Do not attempt semantic repair before py_compile passes.")
    if isinstance(run_payload, dict) and not run_payload.get("ok"):
        recommendations.append("Fix the runtime failure in the extractor before reviewing catalog quality.")
    if isinstance(validate_payload, dict) and not validate_payload.get("ok"):
        recommendations.append("Make the output pass validate_tax_output.py before comparing semantics.")

    if diff_summary:
        summary = diff_summary["summary"]
        if summary.get("extra_count", 0):
            recommendations.append("Inspect the extra field IDs first. They usually reveal over-matching rows, TOC lines, or group nodes being emitted as fields.")
        if summary.get("changed_count", 0):
            recommendations.append("Next, fix changed fields with missing paths or collapsed names. Widespread changed fields usually mean row parsing is too greedy.")

    for issue in quality.get("issues", []):
        recommendation = issue.get("recommendation")
        if isinstance(recommendation, str) and recommendation not in recommendations:
            recommendations.append(recommendation)

    if not recommendations:
        recommendations.append("No obvious repair actions were identified. Inspect changed field samples manually.")
    return recommendations


def determine_status(
    *,
    report: dict[str, Any],
    quality: dict[str, Any],
    diff_summary: dict[str, Any] | None,
) -> str:
    for key in ("compile", "run", "validate"):
        payload = report.get(key)
        if not isinstance(payload, dict) or not payload.get("ok"):
            return "test_failed"
    if diff_summary:
        summary = diff_summary["summary"]
        if any(summary.get(key, 0) for key in ("missing_count", "extra_count", "changed_count")):
            return "needs_repair"
    if quality.get("issues"):
        return "needs_repair"
    return "pass"


def build_markdown(report_payload: dict[str, Any]) -> str:
    lines = [
        "# Repair Brief",
        "",
        "## Status",
        "",
        f"- Status: {report_payload['status']}",
        f"- Extractor: {report_payload['extractor']}",
        f"- PDF: {report_payload['pdf_path']}",
        f"- Run output: {report_payload['run_outdir']}",
        "",
        "## Test Results",
        "",
    ]
    for key in ("compile", "run", "validate"):
        payload = report_payload["test_report"].get(key)
        ok = bool(isinstance(payload, dict) and payload.get("ok"))
        lines.append(f"- {key}: {'ok' if ok else 'failed'}")
    compare = report_payload["test_report"].get("compare")
    if isinstance(compare, dict):
        lines.append(f"- compare: {'ok' if compare.get('ok') else 'failed'}")
    lines.append("")

    diff_summary = report_payload.get("diff_summary")
    if diff_summary:
        summary = diff_summary["summary"]
        lines.extend(
            [
                "## Diff Summary",
                "",
                f"- Baseline: {summary['baseline_count']}",
                f"- Candidate: {summary['candidate_count']}",
                f"- Missing: {summary['missing_count']}",
                f"- Extra: {summary['extra_count']}",
                f"- Changed: {summary['changed_count']}",
                "",
            ]
        )
        if diff_summary["extra_samples"]:
            lines.append("Extra field samples:")
            for field_id in diff_summary["extra_samples"]:
                lines.append(f"- {field_id}")
            lines.append("")
        if diff_summary["changed_samples"]:
            lines.append("Changed field samples:")
            for item in diff_summary["changed_samples"]:
                lines.append(f"- {item['field_id']}")
                for change in item["changes"]:
                    lines.append(f"  {change['key']}: {change['before']!r} -> {change['after']!r}")
            lines.append("")

    quality = report_payload["quality"]
    lines.extend(
        [
            "## Quality Checks",
            "",
            f"- Record count: {quality['metrics']['record_count']}",
            f"- Path coverage ratio: {quality['metrics']['path_coverage_ratio']:.3f}",
            f"- Group ID ratio: {quality['metrics']['group_id_ratio']:.3f}",
            f"- Leader dots name ratio: {quality['metrics']['leader_dots_name_ratio']:.3f}",
            f"- Report path rule ratio: {quality['metrics']['report_path_rule_ratio']:.3f}",
            "",
        ]
    )

    lines.extend(["## Action Items", ""])
    for item in report_payload["recommendations"]:
        lines.append(f"- {item}")
    lines.append("")

    if quality["issues"]:
        lines.extend(["## Detected Issues", ""])
        for issue in quality["issues"]:
            lines.append(f"- {issue['code']}: {issue['message']}")
            if issue["samples"]:
                lines.append(f"  Samples: {', '.join(issue['samples'])}")
            lines.append(f"  Recommendation: {issue['recommendation']}")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def write_outputs(
    *,
    outdir: Path,
    payload: dict[str, Any],
    stdout: str,
    stderr: str,
) -> tuple[Path, Path]:
    outdir.mkdir(parents=True, exist_ok=True)
    json_path = outdir / "repair_brief.json"
    md_path = outdir / "repair_brief.md"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(build_markdown(payload), encoding="utf-8")
    (outdir / "test_stdout.txt").write_text(stdout, encoding="utf-8")
    (outdir / "test_stderr.txt").write_text(stderr, encoding="utf-8")
    return json_path, md_path


def main() -> int:
    args = parse_args()
    pdf_path = Path(args.pdf).expanduser().resolve()
    baseline_path = Path(args.baseline).expanduser().resolve() if args.baseline else None
    outdir = Path(args.outdir).expanduser().resolve()
    run_outdir = outdir / "run"
    diff_outdir = Path(args.diff_outdir).expanduser().resolve() if args.diff_outdir else (run_outdir / "diff" if baseline_path else None)

    returncode, report, stdout, stderr = run_test(
        pdf_path=pdf_path,
        extractor=args.extractor,
        run_outdir=run_outdir,
        baseline=baseline_path,
        diff_outdir=diff_outdir,
    )
    candidate_catalog = load_candidate_catalog(run_outdir)
    quality = analyze_candidate_catalog(candidate_catalog, max_samples=args.max_samples)
    diff_summary = summarize_diff(load_diff_payload(report), max_samples=args.max_samples)
    recommendations = build_recommendations(report=report, quality=quality, diff_summary=diff_summary)
    status = determine_status(report=report, quality=quality, diff_summary=diff_summary)

    payload = {
        "status": status,
        "extractor": args.extractor,
        "pdf_path": str(pdf_path),
        "baseline_path": str(baseline_path) if baseline_path else None,
        "run_outdir": str(run_outdir),
        "test_returncode": returncode,
        "test_report": report,
        "quality": quality,
        "diff_summary": diff_summary,
        "recommendations": recommendations,
    }
    json_path, md_path = write_outputs(outdir=outdir, payload=payload, stdout=stdout, stderr=stderr)
    print(f"repair brief json: {json_path}")
    print(f"repair brief markdown: {md_path}")
    print(f"status: {status}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
