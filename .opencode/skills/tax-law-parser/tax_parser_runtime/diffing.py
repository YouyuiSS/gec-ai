from __future__ import annotations

import argparse
import json
from pathlib import Path


COMPARE_KEYS = [
    "field_name",
    "field_description",
    "note_on_use",
    "data_type",
    "cardinality",
    "invoice_path",
    "credit_note_path",
    "report_path",
    "sample_value",
    "value_set",
    "interpretation",
    "rules",
    "source_pages",
    "min_char_length",
    "max_char_length",
    "min_decimal_precision",
    "max_decimal_precision",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compare two tax-law-parser field catalogs.")
    parser.add_argument("--baseline", required=True, help="Path to the trusted baseline field_catalog.json.")
    parser.add_argument("--candidate", required=True, help="Path to the generated candidate field_catalog.json.")
    parser.add_argument("--outdir", required=True, help="Directory for diff outputs.")
    parser.add_argument(
        "--max-samples",
        type=int,
        default=20,
        help="Maximum sample IDs to include per category in the markdown summary.",
    )
    return parser.parse_args()


def load_catalog(path: Path) -> list[dict[str, object]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise SystemExit(f"{path} is not a JSON array.")
    return payload


def index_by_field_id(payload: list[dict[str, object]]) -> dict[str, dict[str, object]]:
    mapping: dict[str, dict[str, object]] = {}
    for item in payload:
        if not isinstance(item, dict):
            continue
        field_id = str(item.get("field_id", "")).strip()
        if field_id:
            mapping[field_id] = item
    return mapping


def diff_catalogs(
    baseline_map: dict[str, dict[str, object]],
    candidate_map: dict[str, dict[str, object]],
) -> dict[str, object]:
    baseline_ids = set(baseline_map)
    candidate_ids = set(candidate_map)

    missing = sorted(baseline_ids - candidate_ids)
    extra = sorted(candidate_ids - baseline_ids)

    changed: list[dict[str, object]] = []
    for field_id in sorted(baseline_ids & candidate_ids):
        before = baseline_map[field_id]
        after = candidate_map[field_id]
        field_changes: list[dict[str, object]] = []
        for key in COMPARE_KEYS:
            before_value = before.get(key)
            after_value = after.get(key)
            if before_value != after_value:
                field_changes.append(
                    {
                        "key": key,
                        "before": before_value,
                        "after": after_value,
                    }
                )
        if field_changes:
            changed.append(
                {
                    "field_id": field_id,
                    "changes": field_changes,
                }
            )

    summary = {
        "baseline_count": len(baseline_map),
        "candidate_count": len(candidate_map),
        "missing_count": len(missing),
        "extra_count": len(extra),
        "changed_count": len(changed),
    }

    return {
        "summary": summary,
        "missing_field_ids": missing,
        "extra_field_ids": extra,
        "changed_fields": changed,
    }


def write_outputs(outdir: Path, diff_payload: dict[str, object], max_samples: int) -> dict[str, Path]:
    outdir.mkdir(parents=True, exist_ok=True)
    json_path = outdir / "catalog_diff.json"
    md_path = outdir / "catalog_diff.md"

    json_path.write_text(json.dumps(diff_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(build_markdown(diff_payload, max_samples=max_samples), encoding="utf-8")
    return {"json": json_path, "markdown": md_path}


def build_markdown(diff_payload: dict[str, object], max_samples: int) -> str:
    summary = diff_payload["summary"]
    missing = diff_payload["missing_field_ids"]
    extra = diff_payload["extra_field_ids"]
    changed = diff_payload["changed_fields"]

    lines = [
        "# Catalog Diff",
        "",
        "## Summary",
        "",
        f"- Baseline: {summary['baseline_count']}",
        f"- Candidate: {summary['candidate_count']}",
        f"- Missing: {summary['missing_count']}",
        f"- Extra: {summary['extra_count']}",
        f"- Changed: {summary['changed_count']}",
        "",
    ]

    lines.extend(_render_id_section("Missing Field IDs", missing, max_samples))
    lines.extend(_render_id_section("Extra Field IDs", extra, max_samples))
    lines.extend(_render_changed_section(changed, max_samples))
    return "\n".join(lines).rstrip() + "\n"


def _render_id_section(title: str, ids: list[str], max_samples: int) -> list[str]:
    lines = [f"## {title}", ""]
    if not ids:
        lines.append("- None")
        lines.append("")
        return lines

    for field_id in ids[:max_samples]:
        lines.append(f"- {field_id}")
    if len(ids) > max_samples:
        lines.append(f"- ... and {len(ids) - max_samples} more")
    lines.append("")
    return lines


def _render_changed_section(changed: list[dict[str, object]], max_samples: int) -> list[str]:
    lines = ["## Changed Fields", ""]
    if not changed:
        lines.append("- None")
        lines.append("")
        return lines

    for item in changed[:max_samples]:
        lines.append(f"- {item['field_id']}")
        for change in item["changes"][:5]:
            lines.append(f"  {change['key']}: {change['before']!r} -> {change['after']!r}")
    if len(changed) > max_samples:
        lines.append(f"- ... and {len(changed) - max_samples} more")
    lines.append("")
    return lines


def main() -> int:
    args = parse_args()
    baseline_path = Path(args.baseline).expanduser().resolve()
    candidate_path = Path(args.candidate).expanduser().resolve()
    outdir = Path(args.outdir).expanduser().resolve()

    baseline_map = index_by_field_id(load_catalog(baseline_path))
    candidate_map = index_by_field_id(load_catalog(candidate_path))
    diff_payload = diff_catalogs(baseline_map, candidate_map)
    outputs = write_outputs(outdir, diff_payload, max_samples=args.max_samples)

    summary = diff_payload["summary"]
    print(f"baseline: {summary['baseline_count']}")
    print(f"candidate: {summary['candidate_count']}")
    print(f"missing: {summary['missing_count']}")
    print(f"extra: {summary['extra_count']}")
    print(f"changed: {summary['changed_count']}")
    print(f"json: {outputs['json']}")
    print(f"markdown: {outputs['markdown']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
