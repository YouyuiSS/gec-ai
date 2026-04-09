from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from .database import PostgresConnectionConfig
from .diffing import FieldLevelDiffEngine
from .enrichers import LangChainStructuredEnricher, NoopLLMEnricher
from .extractors import PdfTaxFieldDeterministicExtractor
from .models import RegulationDocument
from .orchestrator import PipelineConfig, TaxRegulationUpdatePipeline
from .parsers import PdfPlumberParser
from .publishing import LocalBundlePublisher
from .repository import PersistenceSummary, PostgresTaxRegulationRepository
from .review import RiskBasedReviewGate
from .serialization import (
    bundle_from_dict,
    bundle_to_dict,
    review_item_to_dict,
    validation_issue_to_dict,
    version_diff_to_dict,
)
from .validators import BasicBundleValidator


@dataclass(slots=True)
class PipelineRunRequest:
    source_path: Path
    outdir: Path
    jurisdiction: str
    tax_domain: str
    version_label: str
    language_code: str = "en"
    issued_on: date | None = None
    effective_from: date | None = None
    effective_to: date | None = None
    published_bundle_path: Path | None = None
    auto_publish: bool = False
    persist_to_db: bool = False
    db_name: str = "tax_regulation_demo"
    create_db: bool = False
    db_baseline_version_label: str | None = None
    db_load_latest_published: bool = False
    use_llm_enricher: bool = False
    llm_model: str | None = None
    llm_max_fields_per_batch: int = 8
    llm_max_candidate_fields: int = 24


@dataclass(slots=True)
class PipelineExecutionResult:
    summary_payload: dict[str, object]
    artifact_paths: dict[str, Path]
    bundle_payload: dict[str, object]
    validation_payload: list[dict[str, object]]
    diff_payload: dict[str, object] | None
    review_payload: list[dict[str, object]]
    persistence_summary: PersistenceSummary | None


def maybe_date(value: str | None) -> date | None:
    return date.fromisoformat(value) if value else None


def load_published_bundle(path: Path | None):
    if not path:
        return None
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    return bundle_from_dict(payload)


def build_repository(request: PipelineRunRequest) -> PostgresTaxRegulationRepository | None:
    needs_database = request.persist_to_db or request.db_baseline_version_label or request.db_load_latest_published
    if not needs_database:
        return None

    config = PostgresConnectionConfig.from_spring_environment(database=request.db_name)
    repository = PostgresTaxRegulationRepository(config=config)
    repository.bootstrap(create_database=request.create_db)
    return repository


def build_enricher(request: PipelineRunRequest):
    if not request.use_llm_enricher:
        return NoopLLMEnricher(), "noop", None, None

    model = request.llm_model or os.getenv("TAX_PIPELINE_LLM_MODEL") or os.getenv("OPENAI_MODEL")
    enricher = LangChainStructuredEnricher(
        model=model,
        max_fields_per_batch=request.llm_max_fields_per_batch,
        max_candidate_fields=request.llm_max_candidate_fields,
    )
    provider = getattr(enricher, "model_provider", None) or "unknown"
    return enricher, f"langchain_structured_{provider}", model, "v1-langchain-structured"


def execute_pipeline_request(request: PipelineRunRequest) -> PipelineExecutionResult:
    if request.published_bundle_path and (request.db_baseline_version_label or request.db_load_latest_published):
        raise RuntimeError("Use either a local published bundle path or a Postgres baseline flag, not both.")

    source_path = Path(request.source_path).resolve()
    outdir = Path(request.outdir).resolve()
    outdir.mkdir(parents=True, exist_ok=True)

    document = RegulationDocument(
        jurisdiction=request.jurisdiction,
        tax_domain=request.tax_domain,
        language_code=request.language_code,
        version_label=request.version_label,
        issued_on=request.issued_on,
        effective_from=request.effective_from,
        effective_to=request.effective_to,
        source_path=source_path,
    )

    repository = build_repository(request)
    llm_enricher, llm_fingerprint, llm_model, prompt_version = build_enricher(request)
    pipeline = TaxRegulationUpdatePipeline(
        parser=PdfPlumberParser(),
        deterministic_extractor=PdfTaxFieldDeterministicExtractor(source_path=source_path),
        llm_enricher=llm_enricher,
        validator=BasicBundleValidator(),
        diff_engine=FieldLevelDiffEngine(),
        review_gate=RiskBasedReviewGate(),
        publisher=LocalBundlePublisher(outdir=outdir),
        config=PipelineConfig(auto_publish_when_no_review_items=request.auto_publish),
    )

    published_bundle = load_published_bundle(request.published_bundle_path)
    if published_bundle is None and repository is not None:
        if request.db_baseline_version_label:
            published_bundle = repository.load_bundle_by_version_label(
                jurisdiction=request.jurisdiction,
                tax_domain=request.tax_domain,
                version_label=request.db_baseline_version_label,
            )
        elif request.db_load_latest_published:
            published_bundle = repository.load_latest_published_bundle(
                jurisdiction=request.jurisdiction,
                tax_domain=request.tax_domain,
            )

    result = pipeline.run(
        document=document,
        source_path=source_path,
        published_bundle=published_bundle,
    )

    bundle_payload = bundle_to_dict(result.bundle)
    validation_payload = [validation_issue_to_dict(item) for item in result.validation_issues]
    diff_payload = version_diff_to_dict(result.version_diff)
    review_payload = [review_item_to_dict(item) for item in result.review_items]

    bundle_path = outdir / "candidate_bundle.json"
    validation_path = outdir / "validation_issues.json"
    diff_path = outdir / "version_diff.json"
    review_path = outdir / "review_items.json"
    summary_path = outdir / "run_summary.json"

    bundle_path.write_text(json.dumps(bundle_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    validation_path.write_text(json.dumps(validation_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    diff_path.write_text(json.dumps(diff_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    review_path.write_text(json.dumps(review_payload, ensure_ascii=False, indent=2), encoding="utf-8")

    published_bundle_written = request.auto_publish and not result.validation_issues and not result.review_items
    artifact_paths = {
        "candidate_bundle": bundle_path,
        "validation_issues": validation_path,
        "version_diff": diff_path,
        "review_items": review_path,
        "run_summary": summary_path,
    }
    published_bundle_path = outdir / "published_bundle.json"
    if published_bundle_path.exists():
        artifact_paths["published_bundle"] = published_bundle_path

    persistence_summary = None
    if repository is not None and request.persist_to_db:
        persistence_summary = repository.persist_pipeline_result(
            result=result,
            source_path=source_path,
            artifact_paths=artifact_paths,
            parser_fingerprint="pdfplumber",
            llm_fingerprint=llm_fingerprint,
            llm_model=llm_model,
            prompt_version=prompt_version,
            published=published_bundle_written,
        )

    summary_payload = {
        "bundle_path": str(bundle_path),
        "validation_issue_count": len(result.validation_issues),
        "review_item_count": len(result.review_items),
        "diff_summary": result.version_diff.summary if result.version_diff else None,
        "published_bundle_written": published_bundle_written,
        "llm": {
            "enabled": request.use_llm_enricher,
            "fingerprint": llm_fingerprint,
            "model": llm_model,
            "max_fields_per_batch": getattr(llm_enricher, "max_fields_per_batch", None) if request.use_llm_enricher else None,
            "max_candidate_fields": getattr(llm_enricher, "max_candidate_fields", None) if request.use_llm_enricher else None,
        },
        "database": None
        if persistence_summary is None
        else {
            "database_name": persistence_summary.database_name,
            "source_document_id": persistence_summary.source_document_id,
            "document_version_id": persistence_summary.document_version_id,
            "extraction_run_id": persistence_summary.extraction_run_id,
            "version_diff_id": persistence_summary.version_diff_id,
            "review_item_count": persistence_summary.review_item_count,
            "artifact_count": persistence_summary.artifact_count,
            "document_status": persistence_summary.document_status,
        },
    }
    summary_path.write_text(json.dumps(summary_payload, ensure_ascii=False, indent=2), encoding="utf-8")

    return PipelineExecutionResult(
        summary_payload=summary_payload,
        artifact_paths=artifact_paths,
        bundle_payload=bundle_payload,
        validation_payload=validation_payload,
        diff_payload=diff_payload,
        review_payload=review_payload,
        persistence_summary=persistence_summary,
    )
