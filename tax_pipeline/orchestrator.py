from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from .models import (
    ExtractionBundle,
    ParsedDocument,
    PipelineResult,
    RegulationDocument,
    ReviewItem,
    ValidationIssue,
    VersionDiff,
)


class DocumentParser(Protocol):
    def parse(self, document: RegulationDocument, source_path: Path) -> ParsedDocument:
        ...


class DeterministicExtractor(Protocol):
    def extract(self, parsed: ParsedDocument) -> ExtractionBundle:
        ...


class LLMEnricher(Protocol):
    def enrich(self, parsed: ParsedDocument, partial: ExtractionBundle) -> ExtractionBundle:
        ...


class BundleValidator(Protocol):
    def validate(self, bundle: ExtractionBundle) -> list[ValidationIssue]:
        ...


class DiffEngine(Protocol):
    def diff(
        self,
        published: ExtractionBundle | None,
        candidate: ExtractionBundle,
    ) -> VersionDiff | None:
        ...


class ReviewGate(Protocol):
    def build_review_queue(
        self,
        bundle: ExtractionBundle,
        issues: list[ValidationIssue],
        version_diff: VersionDiff | None,
    ) -> list[ReviewItem]:
        ...


class Publisher(Protocol):
    def publish(self, bundle: ExtractionBundle) -> None:
        ...


@dataclass(slots=True)
class PipelineConfig:
    auto_publish_when_no_review_items: bool = False


@dataclass(slots=True)
class TaxRegulationUpdatePipeline:
    parser: DocumentParser
    deterministic_extractor: DeterministicExtractor
    llm_enricher: LLMEnricher
    validator: BundleValidator
    diff_engine: DiffEngine
    review_gate: ReviewGate
    publisher: Publisher
    config: PipelineConfig = field(default_factory=PipelineConfig)

    def run(
        self,
        document: RegulationDocument,
        source_path: Path,
        published_bundle: ExtractionBundle | None = None,
    ) -> PipelineResult:
        parsed = self.parser.parse(document=document, source_path=source_path)

        deterministic_bundle = self.deterministic_extractor.extract(parsed)
        enriched_bundle = self.llm_enricher.enrich(parsed, deterministic_bundle)

        issues = self.validator.validate(enriched_bundle)
        version_diff = self.diff_engine.diff(published_bundle, enriched_bundle)
        review_items = self.review_gate.build_review_queue(
            bundle=enriched_bundle,
            issues=issues,
            version_diff=version_diff,
        )

        if self.config.auto_publish_when_no_review_items and not review_items and not issues:
            self.publisher.publish(enriched_bundle)

        return PipelineResult(
            bundle=enriched_bundle,
            validation_issues=issues,
            version_diff=version_diff,
            review_items=review_items,
        )
