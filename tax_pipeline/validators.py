from __future__ import annotations

from .models import ExtractionBundle, ValidationIssue


class BasicBundleValidator:
    def validate(self, bundle: ExtractionBundle) -> list[ValidationIssue]:
        issues: list[ValidationIssue] = []

        seen_codes: set[str] = set()
        field_codes = {field.field_code for field in bundle.fields}

        for field in bundle.fields:
            if field.field_code in seen_codes:
                issues.append(
                    ValidationIssue(
                        severity="error",
                        code="duplicate_field_code",
                        message=f"Duplicate field code detected: {field.field_code}",
                        field_code=field.field_code,
                    )
                )
            seen_codes.add(field.field_code)

            if field.field_kind == "atomic" and not (field.paths.invoice or field.paths.credit_note):
                issues.append(
                    ValidationIssue(
                        severity="warning",
                        code="missing_field_path",
                        message=f"Atomic field {field.field_code} does not have an invoice or credit-note path.",
                        field_code=field.field_code,
                    )
                )

            if not field.evidence:
                issues.append(
                    ValidationIssue(
                        severity="warning",
                        code="missing_field_evidence",
                        message=f"Field {field.field_code} has no attached evidence.",
                        field_code=field.field_code,
                    )
                )

            if (
                isinstance(field.occurrence_max, int)
                and field.occurrence_min is not None
                and field.occurrence_min > field.occurrence_max
            ):
                issues.append(
                    ValidationIssue(
                        severity="error",
                        code="invalid_cardinality",
                        message=f"Field {field.field_code} has invalid cardinality bounds.",
                        field_code=field.field_code,
                    )
                )

        for rule in bundle.rules:
            missing = [
                ref
                for ref in rule.referenced_fields
                if ref not in field_codes and not ref.startswith(("BG-", "HR-BG-"))
            ]
            if missing:
                issues.append(
                    ValidationIssue(
                        severity="warning",
                        code="dangling_rule_reference",
                        message=f"Rule {rule.rule_code} references fields not present in bundle: {', '.join(missing)}",
                    )
                )

            if not rule.evidence:
                issues.append(
                    ValidationIssue(
                        severity="warning",
                        code="missing_rule_evidence",
                        message=f"Rule {rule.rule_code} has no attached evidence.",
                    )
                )

        return issues
