from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Literal


Origin = Literal["explicit", "inferred"]
RuleType = Literal[
    "presence",
    "dependency",
    "exclusive",
    "equality",
    "arithmetic",
    "code_list",
    "format",
    "other",
]
RiskLevel = Literal["low", "medium", "high"]
ReviewDecision = Literal["approve", "reject", "edit"]


@dataclass(slots=True)
class Evidence:
    page_number: int
    source_kind: str
    quote_text: str
    section_title: str | None = None


@dataclass(slots=True)
class PathMap:
    invoice: str | None = None
    credit_note: str | None = None
    remark: str | None = None


@dataclass(slots=True)
class FieldConstraints:
    min_char_length: int | None = None
    max_char_length: int | None = None
    min_decimal_scale: int | None = None
    max_decimal_scale: int | None = None
    format_hint: str | None = None


@dataclass(slots=True)
class FieldDefinition:
    field_code: str
    field_name: str
    field_kind: Literal["atomic", "group"]
    parent_group_code: str | None = None
    field_description: str | None = None
    data_type: str | None = None
    occurrence_min: int | None = None
    occurrence_max: int | str | None = None
    sample_value: str | None = None
    value_set_refs: list[str] = field(default_factory=list)
    semantic_notes: str | None = None
    paths: PathMap = field(default_factory=PathMap)
    constraints: FieldConstraints = field(default_factory=FieldConstraints)
    origin: Origin = "explicit"
    confidence: float = 1.0
    evidence: list[Evidence] = field(default_factory=list)


@dataclass(slots=True)
class RuleDefinition:
    rule_code: str
    rule_type: RuleType
    expression_text: str
    referenced_fields: list[str]
    severity: Literal["error", "warning", "info"] = "error"
    origin: Origin = "explicit"
    confidence: float = 1.0
    evidence: list[Evidence] = field(default_factory=list)


@dataclass(slots=True)
class CodeListEntry:
    code: str
    label: str
    description: str | None = None


@dataclass(slots=True)
class CodeListDefinition:
    code_list_name: str
    entries: list[CodeListEntry] = field(default_factory=list)
    origin: Origin = "explicit"
    confidence: float = 1.0
    evidence: list[Evidence] = field(default_factory=list)


@dataclass(slots=True)
class RegulationDocument:
    jurisdiction: str
    tax_domain: str
    language_code: str
    version_label: str
    issued_on: date | None = None
    effective_from: date | None = None
    effective_to: date | None = None
    source_path: Path | None = None


@dataclass(slots=True)
class ParsedPage:
    page_number: int
    text: str
    tables: list[list[list[str | None]]] = field(default_factory=list)
    examples: list[str] = field(default_factory=list)
    headings: list[str] = field(default_factory=list)


@dataclass(slots=True)
class ParsedDocument:
    document: RegulationDocument
    pages: list[ParsedPage]


@dataclass(slots=True)
class ExtractionBundle:
    document: RegulationDocument
    fields: list[FieldDefinition] = field(default_factory=list)
    rules: list[RuleDefinition] = field(default_factory=list)
    code_lists: list[CodeListDefinition] = field(default_factory=list)


@dataclass(slots=True)
class ValidationIssue:
    severity: Literal["error", "warning"]
    code: str
    message: str
    field_code: str | None = None


@dataclass(slots=True)
class FieldChange:
    field_code: str
    change_type: str
    risk_level: RiskLevel
    before_payload: dict | None = None
    after_payload: dict | None = None
    explanation: str | None = None


@dataclass(slots=True)
class VersionDiff:
    base_version_label: str | None
    candidate_version_label: str
    field_changes: list[FieldChange] = field(default_factory=list)
    summary: dict = field(default_factory=dict)


@dataclass(slots=True)
class ReviewItem:
    item_id: str
    risk_level: RiskLevel
    message: str
    change: FieldChange


@dataclass(slots=True)
class PipelineResult:
    bundle: ExtractionBundle
    validation_issues: list[ValidationIssue]
    version_diff: VersionDiff | None
    review_items: list[ReviewItem]
