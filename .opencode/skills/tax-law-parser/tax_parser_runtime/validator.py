from __future__ import annotations

import argparse
import json
from pathlib import Path


REQUIRED_STRING_FIELDS = [
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
    "min_char_length",
    "max_char_length",
    "min_decimal_precision",
    "max_decimal_precision",
    "extractor_name",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate tax-law-parser JSON output.")
    parser.add_argument("--json", required=True, help="Path to field_catalog.json.")
    return parser.parse_args()


def validate_record(record: dict[str, object], index: int, seen_ids: set[str]) -> list[str]:
    errors: list[str] = []

    for field_name in REQUIRED_STRING_FIELDS:
        value = record.get(field_name, "")
        if not isinstance(value, str):
            errors.append(f"record[{index}].{field_name} must be a string")

    field_id = record.get("field_id", "")
    if isinstance(field_id, str):
        if not field_id.strip():
            errors.append(f"record[{index}].field_id must not be empty")
        elif field_id in seen_ids:
            errors.append(f"duplicate field_id: {field_id}")
        else:
            seen_ids.add(field_id)

    rules = record.get("rules", [])
    if not isinstance(rules, list) or any(not isinstance(item, str) for item in rules):
        errors.append(f"record[{index}].rules must be a list of strings")

    source_pages = record.get("source_pages", [])
    if not isinstance(source_pages, list) or any(not isinstance(item, int) for item in source_pages):
        errors.append(f"record[{index}].source_pages must be a list of integers")

    return errors


def main() -> int:
    args = parse_args()
    json_path = Path(args.json).expanduser().resolve()
    payload = json.loads(json_path.read_text(encoding="utf-8"))

    if not isinstance(payload, list):
        raise SystemExit("field_catalog.json must be a JSON array.")

    errors: list[str] = []
    seen_ids: set[str] = set()
    for index, record in enumerate(payload):
        if not isinstance(record, dict):
            errors.append(f"record[{index}] must be an object")
            continue
        errors.extend(validate_record(record, index, seen_ids))

    if errors:
        for error in errors:
            print(error)
        raise SystemExit(1)

    print(f"validated records: {len(payload)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
