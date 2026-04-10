from __future__ import annotations

from pathlib import Path


PROFILE_NAME = "hr-einvoice-legacy"


def extract(pdf_path: Path) -> list[dict[str, object]]:
    from scripts.extract_tax_fields import extract_tax_field_records

    records = extract_tax_field_records(Path(pdf_path))
    return [_record_to_dict(record) for record in records]


def _record_to_dict(record) -> dict[str, object]:
    source_pages = sorted({int(page) for page in getattr(record, "source_pages", []) if str(page).isdigit()})
    return {
        "field_id": record.field_id,
        "field_name": record.field_name,
        "field_description": record.field_description,
        "note_on_use": record.note_on_use,
        "data_type": record.data_type,
        "cardinality": record.cardinality,
        "invoice_path": record.invoice_path,
        "credit_note_path": record.credit_note_path,
        "report_path": record.report_path,
        "sample_value": record.sample_value,
        "value_set": record.value_set,
        "interpretation": record.interpretation,
        "rules": list(record.rules),
        "source_pages": source_pages,
        "min_char_length": record.min_char_length,
        "max_char_length": record.max_char_length,
        "min_decimal_precision": record.min_decimal_precision,
        "max_decimal_precision": record.max_decimal_precision,
        "extractor_name": PROFILE_NAME,
    }
