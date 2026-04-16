from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve()
SKILL_ROOT = SCRIPT_PATH.parents[1]
REPO_ROOT = SCRIPT_PATH.parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(SKILL_ROOT) not in sys.path:
    sys.path.insert(0, str(SKILL_ROOT))

from tax_parser_runtime.registry import describe_registry_module, import_extractor_module, load_registry


DEFAULT_COLUMNS = [
    "field_id",
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
    "extractor_name",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the tax-law-parser skill on a PDF.")
    parser.add_argument("--pdf", required=True, help="Path to the tax regulation PDF.")
    parser.add_argument("--outdir", required=True, help="Directory for generated outputs.")
    parser.add_argument("--extractor", help="Explicit extractor name from the skill registry.")
    parser.add_argument(
        "--pack-dir",
        help="Optional pack root directory. When provided, load registries and baselines from that pack.",
    )
    parser.add_argument(
        "--pages-for-match",
        type=int,
        default=6,
        help="Number of pages to sample when auto-selecting an extractor.",
    )
    return parser.parse_args()


def read_text_sample(pdf_path: Path, max_pages: int) -> str:
    try:
        import pdfplumber
    except ModuleNotFoundError as exc:
        raise RuntimeError("pdfplumber is required to inspect PDF files.") from exc

    chunks: list[str] = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages[:max_pages]:
            chunks.append(page.extract_text() or "")
    return "\n".join(chunks)


def choose_extractor(registry: list[dict[str, object]], pdf_path: Path, pages_for_match: int, explicit: str | None):
    if explicit:
        for item in registry:
            if item["name"] == explicit:
                return item, {"strategy": "explicit", "score": None}
        raise RuntimeError(f"Extractor '{explicit}' was not found in the skill registry.")

    filename = pdf_path.name
    text_sample = read_text_sample(pdf_path, max_pages=pages_for_match)

    best_item = None
    best_score = -1
    for item in registry:
        score = 0
        for needle in item.get("filename_contains", []):
            if needle and needle in filename:
                score += 3
        for needle in item.get("text_contains", []):
            if needle and needle in text_sample:
                score += 1
        if score > best_score:
            best_item = item
            best_score = score

    if best_item is None or best_score <= 0:
        raise RuntimeError(
            "No extractor matched this PDF. Create a new extractor with "
            "scripts/bootstrap_extractor.py, then implement or adjust the parser directly in Python."
        )

    return best_item, {"strategy": "auto", "score": best_score}


def load_extractor(entry: dict[str, object]):
    module = import_extractor_module(entry)
    if not hasattr(module, "extract"):
        raise RuntimeError(
            f"Extractor module '{describe_registry_module(entry)}' does not define extract(pdf_path)."
        )
    return module


def normalize_records(records: list[dict[str, object]]) -> list[dict[str, object]]:
    normalized: list[dict[str, object]] = []
    seen_ids: set[str] = set()

    for record in records:
        row = {key: record.get(key, "" if key not in {"rules", "source_pages"} else []) for key in DEFAULT_COLUMNS}
        row["rules"] = list(row["rules"] or [])
        row["source_pages"] = [int(page) for page in row["source_pages"] or []]
        field_id = str(row["field_id"]).strip()
        if not field_id:
            raise RuntimeError("Encountered a record with an empty field_id.")
        if field_id in seen_ids:
            raise RuntimeError(f"Duplicate field_id detected: {field_id}")
        seen_ids.add(field_id)
        normalized.append(row)

    return normalized


def write_outputs(outdir: Path, records: list[dict[str, object]], metadata: dict[str, object]) -> dict[str, Path]:
    outdir.mkdir(parents=True, exist_ok=True)
    json_path = outdir / "field_catalog.json"
    csv_path = outdir / "field_catalog.csv"
    report_path = outdir / "run_report.json"

    json_path.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")

    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=DEFAULT_COLUMNS)
        writer.writeheader()
        for row in records:
            writer.writerow(
                {
                    **row,
                    "rules": " | ".join(row["rules"]),
                    "source_pages": ",".join(str(page) for page in row["source_pages"]),
                }
            )

    report_path.write_text(
        json.dumps(
            {
                **metadata,
                "record_count": len(records),
                "json_path": str(json_path),
                "csv_path": str(csv_path),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    return {
        "json": json_path,
        "csv": csv_path,
        "report": report_path,
    }


def main() -> int:
    args = parse_args()
    pdf_path = Path(args.pdf).expanduser().resolve()
    outdir = Path(args.outdir).expanduser().resolve()
    pack_dir = Path(args.pack_dir).expanduser().resolve() if args.pack_dir else None

    if not pdf_path.exists():
        raise SystemExit(f"PDF not found: {pdf_path}")
    if pdf_path.suffix.lower() != ".pdf":
        raise SystemExit("Only PDF inputs are supported.")

    registry = load_registry(pack_dir=pack_dir)
    extractor_entry, selection_meta = choose_extractor(
        registry=registry,
        pdf_path=pdf_path,
        pages_for_match=args.pages_for_match,
        explicit=args.extractor,
    )
    module = load_extractor(extractor_entry)
    records = normalize_records(module.extract(pdf_path))
    outputs = write_outputs(
        outdir=outdir,
        records=records,
        metadata={
            "pdf_path": str(pdf_path),
            "pack_dir": str(pack_dir) if pack_dir else "",
            "extractor_name": extractor_entry["name"],
            "extractor_module": describe_registry_module(extractor_entry),
            "extractor_family": extractor_entry.get("family", ""),
            "jurisdiction": extractor_entry.get("jurisdiction", ""),
            "tax_domain": extractor_entry.get("tax_domain", ""),
            "document_language": extractor_entry.get("document_language", ""),
            "registry_source": extractor_entry.get("registry_source", ""),
            "selection": selection_meta,
        },
    )

    print(f"extractor: {extractor_entry['name']}")
    print(f"json: {outputs['json']}")
    print(f"csv: {outputs['csv']}")
    print(f"report: {outputs['report']}")
    print(f"records: {len(records)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
