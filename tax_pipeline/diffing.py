from __future__ import annotations

from dataclasses import asdict

from .models import ExtractionBundle, FieldChange, VersionDiff


def _field_key(field) -> tuple:
    return (
        field.field_name,
        field.data_type,
        field.occurrence_min,
        field.occurrence_max,
        field.paths.invoice,
        field.paths.credit_note,
        field.constraints.min_char_length,
        field.constraints.max_char_length,
        field.constraints.min_decimal_scale,
        field.constraints.max_decimal_scale,
    )


class FieldLevelDiffEngine:
    def diff(
        self,
        published: ExtractionBundle | None,
        candidate: ExtractionBundle,
    ) -> VersionDiff | None:
        if published is None:
            return VersionDiff(
                base_version_label=None,
                candidate_version_label=candidate.document.version_label,
                field_changes=[],
                summary={
                    "baseline": "none",
                    "candidate_field_count": len(candidate.fields),
                    "candidate_rule_count": len(candidate.rules),
                },
            )

        published_fields = {field.field_code: field for field in published.fields}
        candidate_fields = {field.field_code: field for field in candidate.fields}

        changes: list[FieldChange] = []
        added = removed = changed = 0

        for field_code in sorted(candidate_fields.keys() - published_fields.keys()):
            field = candidate_fields[field_code]
            added += 1
            changes.append(
                FieldChange(
                    field_code=field_code,
                    change_type="added",
                    risk_level="medium" if (field.occurrence_min or 0) > 0 else "low",
                    before_payload=None,
                    after_payload=asdict(field),
                    explanation="Field not present in published bundle.",
                )
            )

        for field_code in sorted(published_fields.keys() - candidate_fields.keys()):
            field = published_fields[field_code]
            removed += 1
            changes.append(
                FieldChange(
                    field_code=field_code,
                    change_type="removed",
                    risk_level="high" if (field.occurrence_min or 0) > 0 else "medium",
                    before_payload=asdict(field),
                    after_payload=None,
                    explanation="Field present in published bundle but missing from candidate.",
                )
            )

        for field_code in sorted(candidate_fields.keys() & published_fields.keys()):
            before = published_fields[field_code]
            after = candidate_fields[field_code]
            if _field_key(before) == _field_key(after):
                continue

            if (before.occurrence_min, before.occurrence_max) != (after.occurrence_min, after.occurrence_max):
                change_type = "cardinality_changed"
                risk = "high"
            elif before.data_type != after.data_type:
                change_type = "data_type_changed"
                risk = "high"
            elif (before.paths.invoice, before.paths.credit_note) != (after.paths.invoice, after.paths.credit_note):
                change_type = "path_changed"
                risk = "medium"
            elif (
                before.constraints.min_char_length,
                before.constraints.max_char_length,
                before.constraints.min_decimal_scale,
                before.constraints.max_decimal_scale,
            ) != (
                after.constraints.min_char_length,
                after.constraints.max_char_length,
                after.constraints.min_decimal_scale,
                after.constraints.max_decimal_scale,
            ):
                change_type = "constraint_changed"
                risk = "high"
            else:
                change_type = "metadata_changed"
                risk = "low"

            changed += 1
            changes.append(
                FieldChange(
                    field_code=field_code,
                    change_type=change_type,
                    risk_level=risk,
                    before_payload=asdict(before),
                    after_payload=asdict(after),
                    explanation=f"{change_type} for field {field_code}.",
                )
            )

        return VersionDiff(
            base_version_label=published.document.version_label,
            candidate_version_label=candidate.document.version_label,
            field_changes=changes,
            summary={
                "added": added,
                "removed": removed,
                "changed": changed,
            },
        )
