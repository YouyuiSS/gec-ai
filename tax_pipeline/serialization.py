from __future__ import annotations

from dataclasses import asdict
from datetime import date

from .models import (
    CodeListDefinition,
    CodeListEntry,
    Evidence,
    ExtractionBundle,
    FieldChange,
    FieldConstraints,
    FieldDefinition,
    PathMap,
    RegulationDocument,
    ReviewItem,
    RuleDefinition,
    ValidationIssue,
    VersionDiff,
)


def _date_to_str(value: date | None) -> str | None:
    return value.isoformat() if value else None


def regulation_document_to_dict(document: RegulationDocument) -> dict[str, object]:
    return {
        "jurisdiction": document.jurisdiction,
        "tax_domain": document.tax_domain,
        "language_code": document.language_code,
        "version_label": document.version_label,
        "issued_on": _date_to_str(document.issued_on),
        "effective_from": _date_to_str(document.effective_from),
        "effective_to": _date_to_str(document.effective_to),
        "source_path": str(document.source_path) if document.source_path else None,
    }


def evidence_to_dict(evidence: Evidence) -> dict[str, object]:
    return asdict(evidence)


def field_to_dict(field: FieldDefinition) -> dict[str, object]:
    return {
        "field_code": field.field_code,
        "field_name": field.field_name,
        "field_kind": field.field_kind,
        "parent_group_code": field.parent_group_code,
        "field_description": field.field_description,
        "data_type": field.data_type,
        "occurrence_min": field.occurrence_min,
        "occurrence_max": field.occurrence_max,
        "sample_value": field.sample_value,
        "value_set_refs": field.value_set_refs,
        "semantic_notes": field.semantic_notes,
        "paths": asdict(field.paths),
        "constraints": asdict(field.constraints),
        "origin": field.origin,
        "confidence": field.confidence,
        "evidence": [evidence_to_dict(item) for item in field.evidence],
    }


def rule_to_dict(rule: RuleDefinition) -> dict[str, object]:
    return {
        "rule_code": rule.rule_code,
        "rule_type": rule.rule_type,
        "expression_text": rule.expression_text,
        "referenced_fields": rule.referenced_fields,
        "severity": rule.severity,
        "origin": rule.origin,
        "confidence": rule.confidence,
        "evidence": [evidence_to_dict(item) for item in rule.evidence],
    }


def code_list_to_dict(code_list: CodeListDefinition) -> dict[str, object]:
    return {
        "code_list_name": code_list.code_list_name,
        "entries": [asdict(entry) for entry in code_list.entries],
        "origin": code_list.origin,
        "confidence": code_list.confidence,
        "evidence": [evidence_to_dict(item) for item in code_list.evidence],
    }


def bundle_to_dict(bundle: ExtractionBundle) -> dict[str, object]:
    return {
        "document": regulation_document_to_dict(bundle.document),
        "fields": [field_to_dict(item) for item in bundle.fields],
        "rules": [rule_to_dict(item) for item in bundle.rules],
        "code_lists": [code_list_to_dict(item) for item in bundle.code_lists],
    }


def validation_issue_to_dict(issue: ValidationIssue) -> dict[str, object]:
    return asdict(issue)


def field_change_to_dict(change: FieldChange) -> dict[str, object]:
    return asdict(change)


def version_diff_to_dict(version_diff: VersionDiff | None) -> dict[str, object] | None:
    if version_diff is None:
        return None
    return {
        "base_version_label": version_diff.base_version_label,
        "candidate_version_label": version_diff.candidate_version_label,
        "field_changes": [field_change_to_dict(item) for item in version_diff.field_changes],
        "summary": version_diff.summary,
    }


def review_item_to_dict(item: ReviewItem) -> dict[str, object]:
    return {
        "item_id": item.item_id,
        "risk_level": item.risk_level,
        "message": item.message,
        "change": field_change_to_dict(item.change),
    }


def _str_to_date(value: str | None) -> date | None:
    return date.fromisoformat(value) if value else None


def bundle_from_dict(payload: dict[str, object]) -> ExtractionBundle:
    doc_payload = payload["document"]
    document = RegulationDocument(
        jurisdiction=doc_payload["jurisdiction"],
        tax_domain=doc_payload["tax_domain"],
        language_code=doc_payload["language_code"],
        version_label=doc_payload["version_label"],
        issued_on=_str_to_date(doc_payload.get("issued_on")),
        effective_from=_str_to_date(doc_payload.get("effective_from")),
        effective_to=_str_to_date(doc_payload.get("effective_to")),
    )

    fields = []
    for item in payload.get("fields", []):
        fields.append(
            FieldDefinition(
                field_code=item["field_code"],
                field_name=item["field_name"],
                field_kind=item["field_kind"],
                parent_group_code=item.get("parent_group_code"),
                field_description=item.get("field_description"),
                data_type=item.get("data_type"),
                occurrence_min=item.get("occurrence_min"),
                occurrence_max=item.get("occurrence_max"),
                sample_value=item.get("sample_value"),
                value_set_refs=item.get("value_set_refs", []),
                semantic_notes=item.get("semantic_notes"),
                paths=PathMap(**item.get("paths", {})),
                constraints=FieldConstraints(**item.get("constraints", {})),
                origin=item.get("origin", "explicit"),
                confidence=item.get("confidence", 1.0),
                evidence=[Evidence(**evidence) for evidence in item.get("evidence", [])],
            )
        )

    rules = []
    for item in payload.get("rules", []):
        rules.append(
            RuleDefinition(
                rule_code=item["rule_code"],
                rule_type=item["rule_type"],
                expression_text=item["expression_text"],
                referenced_fields=item.get("referenced_fields", []),
                severity=item.get("severity", "error"),
                origin=item.get("origin", "explicit"),
                confidence=item.get("confidence", 1.0),
                evidence=[Evidence(**evidence) for evidence in item.get("evidence", [])],
            )
        )

    code_lists = []
    for item in payload.get("code_lists", []):
        code_lists.append(
            CodeListDefinition(
                code_list_name=item["code_list_name"],
                entries=[CodeListEntry(**entry) for entry in item.get("entries", [])],
                origin=item.get("origin", "explicit"),
                confidence=item.get("confidence", 1.0),
                evidence=[Evidence(**evidence) for evidence in item.get("evidence", [])],
            )
        )

    return ExtractionBundle(document=document, fields=fields, rules=rules, code_lists=code_lists)
