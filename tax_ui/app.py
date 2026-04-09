from __future__ import annotations

import os
import shutil
import traceback
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from threading import Lock
from uuid import uuid4

from fastapi import FastAPI, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from tax_pipeline.database import PostgresConnectionConfig
from tax_pipeline.repository import PostgresTaxRegulationRepository
from tax_pipeline.runtime import PipelineRunRequest, execute_pipeline_request, maybe_date


ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS_ROOT = ROOT / "artifacts" / "web_ui"
RUNS_ROOT = ARTIFACTS_ROOT / "runs"
STATIC_DIR = Path(__file__).resolve().parent / "static"
TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
SAMPLE_DIR = ROOT / "assets" / "ticket"
ARTIFACTS_BY_NAME = {
    "candidate_bundle",
    "validation_issues",
    "version_diff",
    "review_items",
    "published_bundle",
    "run_summary",
}


@dataclass(slots=True)
class WebRunRecord:
    run_id: str
    status: str
    source_name: str
    created_at: str
    updated_at: str
    config: dict[str, object]
    summary: dict[str, object] | None = None
    bundle: dict[str, object] | None = None
    validation_issues: list[dict[str, object]] = field(default_factory=list)
    review_items: list[dict[str, object]] = field(default_factory=list)
    version_diff: dict[str, object] | None = None
    artifact_paths: dict[str, str] = field(default_factory=dict)
    error: str | None = None


app = FastAPI(title="Tax Regulation Console")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="tax-ui")
_runs: dict[str, WebRunRecord] = {}
_runs_lock = Lock()


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _sample_pdfs() -> list[dict[str, str]]:
    return [{"name": path.name, "path": str(path)} for path in sorted(SAMPLE_DIR.glob("*.pdf"))]


def _truthy(value: str | None) -> bool:
    return str(value).strip().lower() in {"1", "true", "on", "yes"}


def _set_run(run_id: str, **updates) -> None:
    with _runs_lock:
        record = _runs[run_id]
        for key, value in updates.items():
            setattr(record, key, value)
        record.updated_at = _now_iso()


def _serialize_run(record: WebRunRecord) -> dict[str, object]:
    payload = asdict(record)
    payload["kind"] = "run"
    payload["artifact_urls"] = {
        key: f"/api/runs/{record.run_id}/artifacts/{key}"
        for key in record.artifact_paths
    }
    return payload


def _open_repository(db_name: str) -> PostgresTaxRegulationRepository:
    try:
        config = PostgresConnectionConfig.from_spring_environment(database=db_name)
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return PostgresTaxRegulationRepository(config=config)


def _serialize_version_summary(summary) -> dict[str, object]:
    payload = asdict(summary)
    payload["kind"] = "version"
    payload["can_publish"] = summary.status != "published"
    payload["field_count"] = int(summary.metrics.get("field_count", 0) or 0)
    payload["rule_count"] = int(summary.metrics.get("rule_count", 0) or 0)
    payload["code_list_count"] = int(summary.metrics.get("code_list_count", 0) or 0)
    payload["validation_issue_count"] = int(summary.metrics.get("validation_issue_count", 0) or 0)
    payload["review_item_count"] = int(summary.metrics.get("review_item_count", 0) or 0)
    return payload


def _serialize_version_record(record, db_name: str) -> dict[str, object]:
    summary = record.summary
    run_summary = record.run_summary_payload or {}
    diff_payload = record.diff_payload
    summary_payload = {
        "bundle_path": record.artifact_paths.get("candidate_bundle"),
        "validation_issue_count": len(record.validation_payload),
        "review_item_count": len(record.review_payload),
        "diff_summary": (diff_payload or {}).get("summary") or summary.diff_summary,
        "published_bundle_written": "published_bundle" in record.artifact_paths,
        "llm": {
            "enabled": (summary.llm_fingerprint or "noop") != "noop",
            "fingerprint": summary.llm_fingerprint,
            "model": summary.llm_model,
            "max_fields_per_batch": run_summary.get("llm", {}).get("max_fields_per_batch"),
            "max_candidate_fields": run_summary.get("llm", {}).get("max_candidate_fields"),
        },
        "database": {
            "database_name": db_name,
            "document_version_id": summary.document_version_id,
            "document_status": summary.status,
        },
    }
    return {
        "kind": "version",
        "version_id": summary.document_version_id,
        "status": summary.status,
        "source_name": summary.original_filename,
        "created_at": summary.created_at,
        "updated_at": summary.published_at or summary.created_at,
        "config": {
            "jurisdiction": summary.jurisdiction,
            "tax_domain": summary.tax_domain,
            "language_code": summary.language_code,
            "db_name": db_name,
            "version_label": summary.version_label,
        },
        "summary": summary_payload,
        "bundle": record.bundle_payload,
        "validation_issues": record.validation_payload,
        "review_items": record.review_payload,
        "version_diff": diff_payload,
        "artifact_urls": {
            key: f"/api/document-versions/{summary.document_version_id}/artifacts/{key}?db_name={db_name}"
            for key in record.artifact_paths
        },
        "metadata": _serialize_version_summary(summary),
        "can_publish": summary.status != "published",
    }


def _run_pipeline_job(run_id: str, pipeline_request: PipelineRunRequest) -> None:
    _set_run(run_id, status="running")
    try:
        execution = execute_pipeline_request(pipeline_request)
    except Exception:  # noqa: BLE001
        _set_run(
            run_id,
            status="failed",
            error=traceback.format_exc(limit=20),
        )
        return

    _set_run(
        run_id,
        status="succeeded",
        summary=execution.summary_payload,
        bundle=execution.bundle_payload,
        validation_issues=execution.validation_payload,
        review_items=execution.review_payload,
        version_diff=execution.diff_payload,
        artifact_paths={key: str(value) for key, value in execution.artifact_paths.items()},
    )


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    context = {
        "request": request,
        "sample_pdfs": _sample_pdfs(),
        "default_openai_model": os.getenv("OPENAI_MODEL", ""),
        "has_openai_env": bool(os.getenv("OPENAI_BASE_URL") and os.getenv("OPENAI_API_KEY")),
        "has_db_env": bool(os.getenv("SPRING_DATASOURCE_URL") and os.getenv("SPRING_DATASOURCE_USERNAME")),
        "default_db_name": "tax_regulation_demo",
    }
    return templates.TemplateResponse(request, "index.html", context)


@app.get("/api/runs")
def list_runs():
    with _runs_lock:
        runs = sorted(_runs.values(), key=lambda item: item.created_at, reverse=True)
        return {"runs": [_serialize_run(record) for record in runs]}


@app.get("/api/runs/{run_id}")
def get_run(run_id: str):
    with _runs_lock:
        record = _runs.get(run_id)
        if record is None:
            raise HTTPException(status_code=404, detail="Run not found.")
        return _serialize_run(record)


@app.get("/api/runs/{run_id}/artifacts/{artifact_name}")
def download_run_artifact(run_id: str, artifact_name: str):
    if artifact_name not in ARTIFACTS_BY_NAME:
        raise HTTPException(status_code=404, detail="Artifact not found.")

    with _runs_lock:
        record = _runs.get(run_id)
        if record is None:
            raise HTTPException(status_code=404, detail="Run not found.")
        artifact_path = record.artifact_paths.get(artifact_name)

    if not artifact_path or not Path(artifact_path).exists():
        raise HTTPException(status_code=404, detail="Artifact not available.")

    return FileResponse(path=artifact_path, filename=Path(artifact_path).name)


@app.get("/api/document-versions")
def list_document_versions(
    jurisdiction: str = Query(...),
    tax_domain: str = Query(...),
    db_name: str = Query("tax_regulation_demo"),
    limit: int = Query(20, ge=1, le=100),
):
    repository = _open_repository(db_name)
    versions = repository.list_document_versions(jurisdiction=jurisdiction, tax_domain=tax_domain, limit=limit)
    return {
        "db_name": db_name,
        "jurisdiction": jurisdiction,
        "tax_domain": tax_domain,
        "versions": [_serialize_version_summary(item) for item in versions],
    }


@app.get("/api/document-versions/{document_version_id}")
def get_document_version(
    document_version_id: int,
    db_name: str = Query("tax_regulation_demo"),
):
    repository = _open_repository(db_name)
    record = repository.get_document_version_record(document_version_id)
    return _serialize_version_record(record, db_name)


@app.get("/api/document-versions/{document_version_id}/artifacts/{artifact_name}")
def download_version_artifact(
    document_version_id: int,
    artifact_name: str,
    db_name: str = Query("tax_regulation_demo"),
):
    if artifact_name not in ARTIFACTS_BY_NAME:
        raise HTTPException(status_code=404, detail="Artifact not found.")

    repository = _open_repository(db_name)
    artifact_path = repository.get_artifact_paths(document_version_id).get(artifact_name)
    if not artifact_path or not Path(artifact_path).exists():
        raise HTTPException(status_code=404, detail="Artifact not available.")

    return FileResponse(path=artifact_path, filename=Path(artifact_path).name)


@app.post("/api/document-versions/{document_version_id}/publish")
def publish_document_version(
    document_version_id: int,
    db_name: str = Form("tax_regulation_demo"),
    reviewer: str = Form("web-ui"),
    comment: str = Form("Published from web console."),
):
    repository = _open_repository(db_name)
    record = repository.publish_document_version(
        document_version_id=document_version_id,
        reviewer=reviewer,
        comment=comment or None,
    )
    return _serialize_version_record(record, db_name)


@app.post("/api/runs")
async def create_run(
    existing_pdf_path: str = Form(""),
    uploaded_pdf: UploadFile | None = File(default=None),
    jurisdiction: str = Form("HR"),
    tax_domain: str = Form("einvoice"),
    language_code: str = Form("en"),
    version_label: str = Form(...),
    issued_on: str = Form(""),
    effective_from: str = Form(""),
    effective_to: str = Form(""),
    auto_publish: str = Form(""),
    persist_to_db: str = Form(""),
    db_name: str = Form("tax_regulation_demo"),
    create_db: str = Form(""),
    db_baseline_version_label: str = Form(""),
    db_load_latest_published: str = Form(""),
    use_llm_enricher: str = Form(""),
    llm_model: str = Form(""),
    llm_max_fields_per_batch: int = Form(8),
    llm_max_candidate_fields: int = Form(1),
):
    run_id = datetime.now().strftime("%Y%m%d%H%M%S") + "-" + uuid4().hex[:8]
    run_dir = RUNS_ROOT / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    source_path: Path
    source_name: str
    if uploaded_pdf is not None and uploaded_pdf.filename:
        source_name = uploaded_pdf.filename
        source_path = run_dir / "input" / source_name
        source_path.parent.mkdir(parents=True, exist_ok=True)
        with source_path.open("wb") as handle:
            shutil.copyfileobj(uploaded_pdf.file, handle)
    elif existing_pdf_path.strip():
        source_path = Path(existing_pdf_path.strip()).expanduser().resolve()
        source_name = source_path.name
    else:
        raise HTTPException(status_code=400, detail="Provide a sample PDF path or upload a PDF.")

    if not source_path.exists():
        raise HTTPException(status_code=400, detail=f"PDF not found: {source_path}")
    if source_path.suffix.lower() != ".pdf":
        raise HTTPException(status_code=400, detail="Only PDF files are supported.")

    config = {
        "jurisdiction": jurisdiction,
        "tax_domain": tax_domain,
        "language_code": language_code,
        "version_label": version_label,
        "issued_on": issued_on or None,
        "effective_from": effective_from or None,
        "effective_to": effective_to or None,
        "source_path": str(source_path),
        "persist_to_db": _truthy(persist_to_db),
        "db_name": db_name,
        "use_llm_enricher": _truthy(use_llm_enricher),
        "llm_model": llm_model or None,
        "llm_max_candidate_fields": llm_max_candidate_fields,
    }

    request = PipelineRunRequest(
        source_path=source_path,
        outdir=run_dir,
        jurisdiction=jurisdiction,
        tax_domain=tax_domain,
        language_code=language_code,
        version_label=version_label,
        issued_on=maybe_date(issued_on or None),
        effective_from=maybe_date(effective_from or None),
        effective_to=maybe_date(effective_to or None),
        auto_publish=_truthy(auto_publish),
        persist_to_db=_truthy(persist_to_db),
        db_name=db_name,
        create_db=_truthy(create_db),
        db_baseline_version_label=db_baseline_version_label or None,
        db_load_latest_published=_truthy(db_load_latest_published),
        use_llm_enricher=_truthy(use_llm_enricher),
        llm_model=llm_model or None,
        llm_max_fields_per_batch=llm_max_fields_per_batch,
        llm_max_candidate_fields=llm_max_candidate_fields,
    )

    record = WebRunRecord(
        run_id=run_id,
        status="queued",
        source_name=source_name,
        created_at=_now_iso(),
        updated_at=_now_iso(),
        config=config,
    )
    with _runs_lock:
        _runs[run_id] = record

    _executor.submit(_run_pipeline_job, run_id, request)
    return JSONResponse({"run_id": run_id, "status": "queued", "status_url": f"/api/runs/{run_id}"})
