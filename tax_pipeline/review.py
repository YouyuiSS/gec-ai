from __future__ import annotations

from .models import FieldChange, ReviewItem


class RiskBasedReviewGate:
    def build_review_queue(self, bundle, issues, version_diff) -> list[ReviewItem]:
        items: list[ReviewItem] = []

        for issue in issues:
            items.append(
                ReviewItem(
                    item_id=f"validation:{issue.code}:{issue.field_code or 'global'}",
                    risk_level="high" if issue.severity == "error" else "medium",
                    message=issue.message,
                    change=FieldChange(
                        field_code=issue.field_code or "global",
                        change_type=f"validation_{issue.code}",
                        risk_level="high" if issue.severity == "error" else "medium",
                        explanation=issue.message,
                    ),
                )
            )

        if version_diff is None:
            return items

        for index, change in enumerate(version_diff.field_changes, start=1):
            if change.risk_level == "low":
                continue
            items.append(
                ReviewItem(
                    item_id=f"diff:{index}:{change.field_code}",
                    risk_level=change.risk_level,
                    message=change.explanation or f"{change.change_type} for {change.field_code}",
                    change=change,
                )
            )
        return items
