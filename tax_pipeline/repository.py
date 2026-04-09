from __future__ import annotations

import hashlib
import importlib
import json
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .database import PostgresConnectionConfig
from .models import (
    CodeListDefinition,
    CodeListEntry,
    Evidence,
    ExtractionBundle,
    FieldConstraints,
    FieldDefinition,
    PathMap,
    PipelineResult,
    RegulationDocument,
    RuleDefinition,
)
from .serialization import bundle_to_dict, field_change_to_dict


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _coerce_occurrence_max(value: str | None) -> int | str | None:
    if value is None:
        return None
    return int(value) if value.isdigit() else value


def _normalize_json_value(value, fallback):
    if value is None:
        return fallback
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return fallback
    return value


def _load_psycopg():
    try:
        psycopg = importlib.import_module("psycopg")
        rows = importlib.import_module("psycopg.rows")
        sql = importlib.import_module("psycopg.sql")
        return psycopg, rows, sql
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "psycopg is required for Postgres persistence. Install dependencies from requirements.txt."
        ) from exc


@dataclass(slots=True)
class PersistenceSummary:
    database_name: str
    source_document_id: int
    document_version_id: int
    extraction_run_id: int
    version_diff_id: int | None
    review_item_count: int
    artifact_count: int
    document_status: str


@dataclass(slots=True)
class DocumentVersionSummary:
    document_version_id: int
    source_document_id: int
    jurisdiction: str
    tax_domain: str
    language_code: str | None
    version_label: str
    original_filename: str
    status: str
    issued_on: str | None
    effective_from: str | None
    effective_to: str | None
    created_at: str
    published_at: str | None
    parser_fingerprint: str | None
    llm_fingerprint: str | None
    llm_model: str | None
    metrics: dict[str, object]
    diff_summary: dict[str, object] | None
    artifact_bundle_types: list[str]


@dataclass(slots=True)
class DocumentVersionRecord:
    summary: DocumentVersionSummary
    bundle_payload: dict[str, object]
    validation_payload: list[dict[str, object]]
    review_payload: list[dict[str, object]]
    diff_payload: dict[str, object] | None
    run_summary_payload: dict[str, object] | None
    artifact_paths: dict[str, str]


class PostgresTaxRegulationRepository:
    def __init__(
        self,
        config: PostgresConnectionConfig,
        schema_path: Path | None = None,
    ) -> None:
        self.config = config
        self.schema_path = schema_path or Path(__file__).resolve().parent.parent / "sql" / "tax_regulation_schema.sql"

    def ensure_database(self, create_if_missing: bool = False) -> bool:
        psycopg, _, sql = _load_psycopg()
        admin_config = self.config.with_database("postgres")
        with psycopg.connect(**admin_config.connect_kwargs(), autocommit=True) as conn:
            with conn.cursor() as cur:
                cur.execute("select 1 from pg_database where datname = %s", (self.config.database,))
                exists = cur.fetchone() is not None
                if exists:
                    return False
                if not create_if_missing:
                    raise RuntimeError(
                        f"Database {self.config.database} does not exist. Re-run with creation enabled."
                    )
                cur.execute(sql.SQL("create database {}").format(sql.Identifier(self.config.database)))
                return True

    def apply_schema(self) -> None:
        schema_path = self.schema_path.resolve()
        psql_path = shutil.which("psql")
        if psql_path:
            env = dict(os.environ, PGPASSWORD=self.config.password)
            subprocess.run(
                [
                    psql_path,
                    "-h",
                    self.config.host,
                    "-p",
                    str(self.config.port),
                    "-U",
                    self.config.username,
                    "-d",
                    self.config.database,
                    "-v",
                    "ON_ERROR_STOP=1",
                    "-f",
                    str(schema_path),
                ],
                check=True,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            return

        psycopg, _, _ = _load_psycopg()
        sql_text = schema_path.read_text(encoding="utf-8")
        with psycopg.connect(**self.config.connect_kwargs(), autocommit=True) as conn:
            with conn.cursor() as cur:
                cur.execute(sql_text)

    def bootstrap(self, create_database: bool = False) -> bool:
        created = self.ensure_database(create_if_missing=create_database)
        self.apply_schema()
        return created

    def load_latest_published_bundle(
        self,
        jurisdiction: str,
        tax_domain: str,
    ) -> ExtractionBundle | None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    select dv.id
                    from document_version dv
                    join source_document sd on sd.id = dv.source_document_id
                    where sd.jurisdiction = %s
                      and sd.tax_domain = %s
                      and dv.status = 'published'
                    order by coalesce(dv.effective_from, dv.issued_on) desc nulls last, dv.created_at desc
                    limit 1
                    """,
                    (jurisdiction, tax_domain),
                )
                row = cur.fetchone()
        if not row:
            return None
        return self._load_bundle_by_version_id(row["id"])

    def load_bundle_by_version_label(
        self,
        jurisdiction: str,
        tax_domain: str,
        version_label: str,
    ) -> ExtractionBundle | None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    select dv.id
                    from document_version dv
                    join source_document sd on sd.id = dv.source_document_id
                    where sd.jurisdiction = %s
                      and sd.tax_domain = %s
                      and dv.version_label = %s
                    order by dv.created_at desc
                    limit 1
                    """,
                    (jurisdiction, tax_domain, version_label),
                )
                row = cur.fetchone()
        if not row:
            return None
        return self._load_bundle_by_version_id(row["id"])

    def list_document_versions(
        self,
        jurisdiction: str,
        tax_domain: str,
        limit: int = 20,
    ) -> list[DocumentVersionSummary]:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    select
                        dv.id as document_version_id,
                        sd.id as source_document_id,
                        sd.jurisdiction,
                        sd.tax_domain,
                        sd.language_code,
                        sd.original_filename,
                        dv.version_label,
                        dv.status,
                        dv.issued_on,
                        dv.effective_from,
                        dv.effective_to,
                        dv.created_at,
                        dv.published_at,
                        dv.parser_fingerprint,
                        dv.llm_fingerprint,
                        latest_run.llm_model,
                        latest_run.metrics,
                        latest_diff.summary as diff_summary,
                        coalesce(artifact_types.bundle_types, '{}'::text[]) as artifact_bundle_types
                    from document_version dv
                    join source_document sd on sd.id = dv.source_document_id
                    left join lateral (
                        select er.llm_model, er.metrics
                        from extraction_run er
                        where er.document_version_id = dv.id
                        order by er.started_at desc, er.id desc
                        limit 1
                    ) latest_run on true
                    left join lateral (
                        select vd.summary
                        from version_diff vd
                        where vd.candidate_version_id = dv.id
                        order by vd.created_at desc, vd.id desc
                        limit 1
                    ) latest_diff on true
                    left join lateral (
                        select array_agg(pb.bundle_type order by pb.bundle_type) as bundle_types
                        from publication_bundle pb
                        where pb.document_version_id = dv.id
                    ) artifact_types on true
                    where sd.jurisdiction = %s
                      and sd.tax_domain = %s
                    order by coalesce(dv.published_at, dv.created_at) desc, dv.id desc
                    limit %s
                    """,
                    (jurisdiction, tax_domain, limit),
                )
                rows = cur.fetchall()

        summaries: list[DocumentVersionSummary] = []
        for row in rows:
            metrics = _normalize_json_value(row["metrics"], {})
            diff_summary = _normalize_json_value(row["diff_summary"], None)
            artifact_bundle_types = list(row["artifact_bundle_types"] or [])
            summaries.append(
                DocumentVersionSummary(
                    document_version_id=row["document_version_id"],
                    source_document_id=row["source_document_id"],
                    jurisdiction=row["jurisdiction"],
                    tax_domain=row["tax_domain"],
                    language_code=row["language_code"],
                    version_label=row["version_label"],
                    original_filename=row["original_filename"],
                    status=row["status"],
                    issued_on=row["issued_on"].isoformat() if row["issued_on"] else None,
                    effective_from=row["effective_from"].isoformat() if row["effective_from"] else None,
                    effective_to=row["effective_to"].isoformat() if row["effective_to"] else None,
                    created_at=row["created_at"].isoformat(),
                    published_at=row["published_at"].isoformat() if row["published_at"] else None,
                    parser_fingerprint=row["parser_fingerprint"],
                    llm_fingerprint=row["llm_fingerprint"],
                    llm_model=row["llm_model"],
                    metrics=metrics if isinstance(metrics, dict) else {},
                    diff_summary=diff_summary if isinstance(diff_summary, dict) else None,
                    artifact_bundle_types=artifact_bundle_types,
                )
            )
        return summaries

    def get_document_version_record(self, document_version_id: int) -> DocumentVersionRecord:
        summary = self.get_document_version_summary(document_version_id)
        artifact_paths = self.get_artifact_paths(document_version_id)
        bundle_payload = bundle_to_dict(self._load_bundle_by_version_id(document_version_id))
        validation_payload = self._read_json_artifact(artifact_paths.get("validation_issues"), [])
        review_payload = self._read_json_artifact(artifact_paths.get("review_items"), [])
        diff_payload = self._read_json_artifact(artifact_paths.get("version_diff"), None)
        run_summary_payload = self._read_json_artifact(artifact_paths.get("run_summary"), None)

        if review_payload == []:
            review_payload = self._load_review_items_payload(document_version_id)
        if diff_payload is None:
            diff_payload = self._load_version_diff_payload(document_version_id)

        return DocumentVersionRecord(
            summary=summary,
            bundle_payload=bundle_payload,
            validation_payload=validation_payload if isinstance(validation_payload, list) else [],
            review_payload=review_payload if isinstance(review_payload, list) else [],
            diff_payload=diff_payload if isinstance(diff_payload, dict) else None,
            run_summary_payload=run_summary_payload if isinstance(run_summary_payload, dict) else None,
            artifact_paths=artifact_paths,
        )

    def get_document_version_summary(self, document_version_id: int) -> DocumentVersionSummary:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    select
                        dv.id as document_version_id,
                        sd.id as source_document_id,
                        sd.jurisdiction,
                        sd.tax_domain,
                        sd.language_code,
                        sd.original_filename,
                        dv.version_label,
                        dv.status,
                        dv.issued_on,
                        dv.effective_from,
                        dv.effective_to,
                        dv.created_at,
                        dv.published_at,
                        dv.parser_fingerprint,
                        dv.llm_fingerprint,
                        latest_run.llm_model,
                        latest_run.metrics,
                        latest_diff.summary as diff_summary,
                        coalesce(artifact_types.bundle_types, '{}'::text[]) as artifact_bundle_types
                    from document_version dv
                    join source_document sd on sd.id = dv.source_document_id
                    left join lateral (
                        select er.llm_model, er.metrics
                        from extraction_run er
                        where er.document_version_id = dv.id
                        order by er.started_at desc, er.id desc
                        limit 1
                    ) latest_run on true
                    left join lateral (
                        select vd.summary
                        from version_diff vd
                        where vd.candidate_version_id = dv.id
                        order by vd.created_at desc, vd.id desc
                        limit 1
                    ) latest_diff on true
                    left join lateral (
                        select array_agg(pb.bundle_type order by pb.bundle_type) as bundle_types
                        from publication_bundle pb
                        where pb.document_version_id = dv.id
                    ) artifact_types on true
                    where dv.id = %s
                    """,
                    (document_version_id,),
                )
                row = cur.fetchone()
        if row is None:
            raise RuntimeError(f"Document version {document_version_id} was not found.")
        metrics = _normalize_json_value(row["metrics"], {})
        diff_summary = _normalize_json_value(row["diff_summary"], None)
        artifact_bundle_types = list(row["artifact_bundle_types"] or [])
        return DocumentVersionSummary(
            document_version_id=row["document_version_id"],
            source_document_id=row["source_document_id"],
            jurisdiction=row["jurisdiction"],
            tax_domain=row["tax_domain"],
            language_code=row["language_code"],
            version_label=row["version_label"],
            original_filename=row["original_filename"],
            status=row["status"],
            issued_on=row["issued_on"].isoformat() if row["issued_on"] else None,
            effective_from=row["effective_from"].isoformat() if row["effective_from"] else None,
            effective_to=row["effective_to"].isoformat() if row["effective_to"] else None,
            created_at=row["created_at"].isoformat(),
            published_at=row["published_at"].isoformat() if row["published_at"] else None,
            parser_fingerprint=row["parser_fingerprint"],
            llm_fingerprint=row["llm_fingerprint"],
            llm_model=row["llm_model"],
            metrics=metrics if isinstance(metrics, dict) else {},
            diff_summary=diff_summary if isinstance(diff_summary, dict) else None,
            artifact_bundle_types=artifact_bundle_types,
        )

    def get_artifact_paths(self, document_version_id: int) -> dict[str, str]:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    select bundle_type, artifact_uri
                    from publication_bundle
                    where document_version_id = %s
                    order by created_at asc, id asc
                    """,
                    (document_version_id,),
                )
                return {
                    row["bundle_type"]: row["artifact_uri"]
                    for row in cur.fetchall()
                    if row["artifact_uri"]
                }

    def publish_document_version(
        self,
        document_version_id: int,
        reviewer: str = "web-ui",
        comment: str | None = None,
    ) -> DocumentVersionRecord:
        summary = self.get_document_version_summary(document_version_id)
        artifact_paths = self.get_artifact_paths(document_version_id)
        published_path = self._materialize_published_bundle(document_version_id, artifact_paths)

        with self._connect() as conn:
            with conn.transaction():
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        update document_version
                        set status = 'published',
                            published_at = now()
                        where id = %s
                        """,
                        (document_version_id,),
                    )
                    cur.execute(
                        """
                        update version_diff
                        set status = 'published'
                        where candidate_version_id = %s
                        """,
                        (document_version_id,),
                    )
                    cur.execute(
                        """
                        update review_queue_item
                        set status = 'resolved'
                        where version_diff_id in (
                            select id from version_diff where candidate_version_id = %s
                        )
                        """,
                        (document_version_id,),
                    )
                    cur.execute(
                        """
                        insert into review_decision (
                            version_diff_id,
                            reviewer,
                            decision,
                            comment
                        )
                        select id, %s, %s, %s
                        from version_diff
                        where candidate_version_id = %s
                        on conflict do nothing
                        """,
                        (reviewer, "approve", comment, document_version_id),
                    )
                    cur.execute(
                        """
                        insert into publication_bundle (
                            document_version_id,
                            bundle_type,
                            bundle_status,
                            artifact_uri,
                            checksum_sha256
                        )
                        values (%s, %s, %s, %s, %s)
                        on conflict (document_version_id, bundle_type, bundle_status) do update
                        set artifact_uri = excluded.artifact_uri,
                            checksum_sha256 = excluded.checksum_sha256,
                            created_at = now()
                        """,
                        (
                            document_version_id,
                            "published_bundle",
                            "published",
                            str(published_path),
                            _sha256(published_path),
                        ),
                    )

        return self.get_document_version_record(document_version_id)

    def persist_pipeline_result(
        self,
        result: PipelineResult,
        source_path: Path,
        artifact_paths: dict[str, Path],
        parser_fingerprint: str = "pdfplumber",
        llm_fingerprint: str = "noop",
        llm_model: str | None = None,
        prompt_version: str | None = None,
        published: bool = False,
    ) -> PersistenceSummary:
        document = result.bundle.document
        source_checksum = _sha256(source_path)
        document_status = "published" if published else "candidate"

        with self._connect() as conn:
            with conn.transaction():
                with conn.cursor() as cur:
                    source_document_id = self._upsert_source_document(
                        cur=cur,
                        document=document,
                        source_path=source_path,
                        checksum_sha256=source_checksum,
                    )
                    document_version_id = self._upsert_document_version(
                        cur=cur,
                        source_document_id=source_document_id,
                        document=document,
                        status=document_status,
                        parser_fingerprint=parser_fingerprint,
                        llm_fingerprint=llm_fingerprint,
                        published=published,
                    )

                    self._clear_version_snapshot(cur, document_version_id)

                    citation_ids = self._insert_bundle_snapshot(
                        cur=cur,
                        document_version_id=document_version_id,
                        bundle=result.bundle,
                    )
                    version_diff_id = self._insert_version_diff_snapshot(
                        cur=cur,
                        document=document,
                        document_version_id=document_version_id,
                        result=result,
                    )
                    artifact_count = self._insert_artifact_snapshot(
                        cur=cur,
                        document_version_id=document_version_id,
                        artifact_paths=artifact_paths,
                    )
                    extraction_run_id = self._insert_extraction_run(
                        cur=cur,
                        document_version_id=document_version_id,
                        result=result,
                        parser_fingerprint=parser_fingerprint,
                        llm_model=llm_model,
                        prompt_version=prompt_version,
                        citation_count=len(citation_ids),
                        artifact_count=artifact_count,
                        published=published,
                    )

        return PersistenceSummary(
            database_name=self.config.database,
            source_document_id=source_document_id,
            document_version_id=document_version_id,
            extraction_run_id=extraction_run_id,
            version_diff_id=version_diff_id,
            review_item_count=len(result.review_items),
            artifact_count=artifact_count,
            document_status=document_status,
        )

    def _connect(self):
        psycopg, rows, _ = _load_psycopg()
        return psycopg.connect(**self.config.connect_kwargs(), row_factory=rows.dict_row)

    def _load_bundle_by_version_id(self, document_version_id: int) -> ExtractionBundle:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    select
                        dv.id as document_version_id,
                        dv.version_label,
                        dv.issued_on,
                        dv.effective_from,
                        dv.effective_to,
                        sd.jurisdiction,
                        sd.tax_domain,
                        sd.language_code,
                        sd.source_uri
                    from document_version dv
                    join source_document sd on sd.id = dv.source_document_id
                    where dv.id = %s
                    """,
                    (document_version_id,),
                )
                version_row = cur.fetchone()
                if version_row is None:
                    raise RuntimeError(f"Document version {document_version_id} was not found.")

                document = RegulationDocument(
                    jurisdiction=version_row["jurisdiction"],
                    tax_domain=version_row["tax_domain"],
                    language_code=version_row["language_code"],
                    version_label=version_row["version_label"],
                    issued_on=version_row["issued_on"],
                    effective_from=version_row["effective_from"],
                    effective_to=version_row["effective_to"],
                    source_path=Path(version_row["source_uri"]) if version_row["source_uri"] else None,
                )

                cur.execute(
                    """
                    select
                        id,
                        field_code,
                        field_kind,
                        parent_group_code,
                        field_name,
                        field_description,
                        data_type,
                        occurrence_min,
                        occurrence_max,
                        sample_value,
                        value_set_refs,
                        semantic_notes,
                        min_char_length,
                        max_char_length,
                        min_decimal_scale,
                        max_decimal_scale,
                        origin,
                        confidence
                    from field_definition
                    where document_version_id = %s
                    order by field_code
                    """,
                    (document_version_id,),
                )
                field_rows = cur.fetchall()

                cur.execute(
                    """
                    select
                        fd.field_code,
                        fp.doc_kind,
                        fp.path_expr,
                        fp.remark
                    from field_definition fd
                    join field_path fp on fp.field_definition_id = fd.id
                    where fd.document_version_id = %s
                    """,
                    (document_version_id,),
                )
                path_rows = cur.fetchall()

                cur.execute(
                    """
                    select
                        fd.field_code,
                        c.page_number,
                        c.section_title,
                        c.source_kind,
                        c.quote_text
                    from field_definition fd
                    join field_citation fc on fc.field_definition_id = fd.id
                    join citation c on c.id = fc.citation_id
                    where fd.document_version_id = %s
                    order by fd.field_code, c.page_number, c.id
                    """,
                    (document_version_id,),
                )
                field_citation_rows = cur.fetchall()

                cur.execute(
                    """
                    select
                        id,
                        rule_code,
                        rule_type,
                        severity,
                        expression_text,
                        origin,
                        confidence
                    from rule_definition
                    where document_version_id = %s
                    order by rule_code
                    """,
                    (document_version_id,),
                )
                rule_rows = cur.fetchall()

                cur.execute(
                    """
                    select
                        rd.rule_code,
                        fd.field_code
                    from rule_definition rd
                    join rule_field_link rfl on rfl.rule_definition_id = rd.id
                    join field_definition fd on fd.id = rfl.field_definition_id
                    where rd.document_version_id = %s
                    order by rd.rule_code, fd.field_code
                    """,
                    (document_version_id,),
                )
                rule_link_rows = cur.fetchall()

                cur.execute(
                    """
                    select
                        rd.rule_code,
                        c.page_number,
                        c.section_title,
                        c.source_kind,
                        c.quote_text
                    from rule_definition rd
                    join rule_citation rc on rc.rule_definition_id = rd.id
                    join citation c on c.id = rc.citation_id
                    where rd.document_version_id = %s
                    order by rd.rule_code, c.page_number, c.id
                    """,
                    (document_version_id,),
                )
                rule_citation_rows = cur.fetchall()

                cur.execute(
                    """
                    select
                        id,
                        code_list_name,
                        origin,
                        confidence
                    from code_list_definition
                    where document_version_id = %s
                    order by code_list_name
                    """,
                    (document_version_id,),
                )
                code_list_rows = cur.fetchall()

                cur.execute(
                    """
                    select
                        cld.code_list_name,
                        cle.code,
                        cle.label,
                        cle.description
                    from code_list_definition cld
                    join code_list_entry cle on cle.code_list_definition_id = cld.id
                    where cld.document_version_id = %s
                    order by cld.code_list_name, cle.code
                    """,
                    (document_version_id,),
                )
                code_entry_rows = cur.fetchall()

                cur.execute(
                    """
                    select
                        cld.code_list_name,
                        c.page_number,
                        c.section_title,
                        c.source_kind,
                        c.quote_text
                    from code_list_definition cld
                    join code_list_citation clc on clc.code_list_definition_id = cld.id
                    join citation c on c.id = clc.citation_id
                    where cld.document_version_id = %s
                    order by cld.code_list_name, c.page_number, c.id
                    """,
                    (document_version_id,),
                )
                code_citation_rows = cur.fetchall()

        path_map_by_field: dict[str, PathMap] = {}
        for row in path_rows:
            path_map = path_map_by_field.setdefault(row["field_code"], PathMap())
            if row["doc_kind"] == "invoice":
                path_map.invoice = row["path_expr"]
            elif row["doc_kind"] == "credit_note":
                path_map.credit_note = row["path_expr"]
            if row["remark"] and not path_map.remark:
                path_map.remark = row["remark"]

        evidence_by_field: dict[str, list[Evidence]] = {}
        for row in field_citation_rows:
            evidence_by_field.setdefault(row["field_code"], []).append(
                Evidence(
                    page_number=row["page_number"],
                    section_title=row["section_title"],
                    source_kind=row["source_kind"],
                    quote_text=row["quote_text"],
                )
            )

        fields = [
            FieldDefinition(
                field_code=row["field_code"],
                field_name=row["field_name"],
                field_kind=row["field_kind"],
                parent_group_code=row["parent_group_code"],
                field_description=row["field_description"],
                data_type=row["data_type"],
                occurrence_min=row["occurrence_min"],
                occurrence_max=_coerce_occurrence_max(row["occurrence_max"]),
                sample_value=row["sample_value"],
                value_set_refs=list(_normalize_json_value(row["value_set_refs"], [])),
                semantic_notes=row["semantic_notes"],
                paths=path_map_by_field.get(row["field_code"], PathMap()),
                constraints=FieldConstraints(
                    min_char_length=row["min_char_length"],
                    max_char_length=row["max_char_length"],
                    min_decimal_scale=row["min_decimal_scale"],
                    max_decimal_scale=row["max_decimal_scale"],
                ),
                origin=row["origin"],
                confidence=float(row["confidence"]),
                evidence=evidence_by_field.get(row["field_code"], []),
            )
            for row in field_rows
        ]

        rule_refs_by_code: dict[str, list[str]] = {}
        for row in rule_link_rows:
            rule_refs_by_code.setdefault(row["rule_code"], []).append(row["field_code"])

        evidence_by_rule: dict[str, list[Evidence]] = {}
        for row in rule_citation_rows:
            evidence_by_rule.setdefault(row["rule_code"], []).append(
                Evidence(
                    page_number=row["page_number"],
                    section_title=row["section_title"],
                    source_kind=row["source_kind"],
                    quote_text=row["quote_text"],
                )
            )

        rules = [
            RuleDefinition(
                rule_code=row["rule_code"],
                rule_type=row["rule_type"],
                expression_text=row["expression_text"],
                referenced_fields=rule_refs_by_code.get(row["rule_code"], []),
                severity=row["severity"],
                origin=row["origin"],
                confidence=float(row["confidence"]),
                evidence=evidence_by_rule.get(row["rule_code"], []),
            )
            for row in rule_rows
        ]

        code_entries_by_name: dict[str, list[CodeListEntry]] = {}
        for row in code_entry_rows:
            code_entries_by_name.setdefault(row["code_list_name"], []).append(
                CodeListEntry(
                    code=row["code"],
                    label=row["label"],
                    description=row["description"],
                )
            )

        evidence_by_code_list: dict[str, list[Evidence]] = {}
        for row in code_citation_rows:
            evidence_by_code_list.setdefault(row["code_list_name"], []).append(
                Evidence(
                    page_number=row["page_number"],
                    section_title=row["section_title"],
                    source_kind=row["source_kind"],
                    quote_text=row["quote_text"],
                )
            )

        code_lists = [
            CodeListDefinition(
                code_list_name=row["code_list_name"],
                entries=code_entries_by_name.get(row["code_list_name"], []),
                origin=row["origin"],
                confidence=float(row["confidence"]),
                evidence=evidence_by_code_list.get(row["code_list_name"], []),
            )
            for row in code_list_rows
        ]

        return ExtractionBundle(document=document, fields=fields, rules=rules, code_lists=code_lists)

    def _upsert_source_document(self, cur, document: RegulationDocument, source_path: Path, checksum_sha256: str) -> int:
        cur.execute(
            """
            insert into source_document (
                jurisdiction,
                tax_domain,
                language_code,
                source_uri,
                original_filename,
                checksum_sha256
            )
            values (%s, %s, %s, %s, %s, %s)
            on conflict (checksum_sha256) do update
            set jurisdiction = excluded.jurisdiction,
                tax_domain = excluded.tax_domain,
                language_code = excluded.language_code,
                source_uri = excluded.source_uri,
                original_filename = excluded.original_filename
            returning id
            """,
            (
                document.jurisdiction,
                document.tax_domain,
                document.language_code,
                str(source_path),
                source_path.name,
                checksum_sha256,
            ),
        )
        row = cur.fetchone()
        return row["id"]

    def _upsert_document_version(
        self,
        cur,
        source_document_id: int,
        document: RegulationDocument,
        status: str,
        parser_fingerprint: str,
        llm_fingerprint: str,
        published: bool,
    ) -> int:
        cur.execute(
            """
            insert into document_version (
                source_document_id,
                version_label,
                issued_on,
                effective_from,
                effective_to,
                status,
                parser_fingerprint,
                llm_fingerprint,
                published_at
            )
            values (%s, %s, %s, %s, %s, %s, %s, %s, case when %s then now() else null end)
            on conflict (source_document_id, version_label) do update
            set issued_on = excluded.issued_on,
                effective_from = excluded.effective_from,
                effective_to = excluded.effective_to,
                status = excluded.status,
                parser_fingerprint = excluded.parser_fingerprint,
                llm_fingerprint = excluded.llm_fingerprint,
                published_at = excluded.published_at
            returning id
            """,
            (
                source_document_id,
                document.version_label,
                document.issued_on,
                document.effective_from,
                document.effective_to,
                status,
                parser_fingerprint,
                llm_fingerprint,
                published,
            ),
        )
        row = cur.fetchone()
        return row["id"]

    def _clear_version_snapshot(self, cur, document_version_id: int) -> None:
        cur.execute("delete from publication_bundle where document_version_id = %s", (document_version_id,))
        cur.execute(
            """
            delete from review_queue_item
            where version_diff_id in (
                select id from version_diff where candidate_version_id = %s
            )
            """,
            (document_version_id,),
        )
        cur.execute(
            """
            delete from field_change
            where version_diff_id in (
                select id from version_diff where candidate_version_id = %s
            )
            """,
            (document_version_id,),
        )
        cur.execute("delete from version_diff where candidate_version_id = %s", (document_version_id,))
        cur.execute("delete from code_list_definition where document_version_id = %s", (document_version_id,))
        cur.execute("delete from rule_definition where document_version_id = %s", (document_version_id,))
        cur.execute("delete from field_definition where document_version_id = %s", (document_version_id,))
        cur.execute("delete from citation where document_version_id = %s", (document_version_id,))

    def _insert_bundle_snapshot(self, cur, document_version_id: int, bundle: ExtractionBundle) -> dict[tuple, int]:
        citation_ids: dict[tuple, int] = {}
        field_ids: dict[str, int] = {}

        for field in bundle.fields:
            cur.execute(
                """
                insert into field_definition (
                    document_version_id,
                    field_code,
                    field_kind,
                    parent_group_code,
                    field_name,
                    field_description,
                    data_type,
                    occurrence_min,
                    occurrence_max,
                    sample_value,
                    value_set_refs,
                    semantic_notes,
                    min_char_length,
                    max_char_length,
                    min_decimal_scale,
                    max_decimal_scale,
                    origin,
                    confidence
                )
                values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s, %s, %s, %s, %s)
                returning id
                """,
                (
                    document_version_id,
                    field.field_code,
                    field.field_kind,
                    field.parent_group_code,
                    field.field_name,
                    field.field_description,
                    field.data_type,
                    field.occurrence_min,
                    str(field.occurrence_max) if field.occurrence_max is not None else None,
                    field.sample_value,
                    json.dumps(field.value_set_refs, ensure_ascii=False),
                    field.semantic_notes,
                    field.constraints.min_char_length,
                    field.constraints.max_char_length,
                    field.constraints.min_decimal_scale,
                    field.constraints.max_decimal_scale,
                    field.origin,
                    field.confidence,
                ),
            )
            field_id = cur.fetchone()["id"]
            field_ids[field.field_code] = field_id

            for doc_kind, path_expr in (("invoice", field.paths.invoice), ("credit_note", field.paths.credit_note)):
                if not path_expr:
                    continue
                cur.execute(
                    """
                    insert into field_path (field_definition_id, doc_kind, path_expr, remark)
                    values (%s, %s, %s, %s)
                    """,
                    (field_id, doc_kind, path_expr, field.paths.remark),
                )

            for evidence in field.evidence:
                citation_id = self._upsert_citation(
                    cur=cur,
                    citation_ids=citation_ids,
                    document_version_id=document_version_id,
                    evidence=evidence,
                    anchor_text=field.field_code,
                )
                cur.execute(
                    """
                    insert into field_citation (field_definition_id, citation_id)
                    values (%s, %s)
                    on conflict do nothing
                    """,
                    (field_id, citation_id),
                )

        for rule in bundle.rules:
            cur.execute(
                """
                insert into rule_definition (
                    document_version_id,
                    rule_code,
                    rule_type,
                    severity,
                    expression_text,
                    normalized_expression,
                    origin,
                    confidence
                )
                values (%s, %s, %s, %s, %s, %s::jsonb, %s, %s)
                returning id
                """,
                (
                    document_version_id,
                    rule.rule_code,
                    rule.rule_type,
                    rule.severity,
                    rule.expression_text,
                    json.dumps({"referenced_fields": rule.referenced_fields}, ensure_ascii=False),
                    rule.origin,
                    rule.confidence,
                ),
            )
            rule_id = cur.fetchone()["id"]

            for field_code in rule.referenced_fields:
                field_id = field_ids.get(field_code)
                if field_id is None:
                    continue
                cur.execute(
                    """
                    insert into rule_field_link (rule_definition_id, field_definition_id, role)
                    values (%s, %s, %s)
                    on conflict do nothing
                    """,
                    (rule_id, field_id, "reference"),
                )

            for evidence in rule.evidence:
                citation_id = self._upsert_citation(
                    cur=cur,
                    citation_ids=citation_ids,
                    document_version_id=document_version_id,
                    evidence=evidence,
                    anchor_text=rule.rule_code,
                )
                cur.execute(
                    """
                    insert into rule_citation (rule_definition_id, citation_id)
                    values (%s, %s)
                    on conflict do nothing
                    """,
                    (rule_id, citation_id),
                )

        for code_list in bundle.code_lists:
            cur.execute(
                """
                insert into code_list_definition (
                    document_version_id,
                    code_list_name,
                    origin,
                    confidence
                )
                values (%s, %s, %s, %s)
                returning id
                """,
                (
                    document_version_id,
                    code_list.code_list_name,
                    code_list.origin,
                    code_list.confidence,
                ),
            )
            code_list_id = cur.fetchone()["id"]

            for entry in code_list.entries:
                cur.execute(
                    """
                    insert into code_list_entry (
                        code_list_definition_id,
                        code,
                        label,
                        description
                    )
                    values (%s, %s, %s, %s)
                    on conflict (code_list_definition_id, code) do update
                    set label = excluded.label,
                        description = excluded.description
                    """,
                    (code_list_id, entry.code, entry.label, entry.description),
                )

            for evidence in code_list.evidence:
                citation_id = self._upsert_citation(
                    cur=cur,
                    citation_ids=citation_ids,
                    document_version_id=document_version_id,
                    evidence=evidence,
                    anchor_text=code_list.code_list_name,
                )
                cur.execute(
                    """
                    insert into code_list_citation (code_list_definition_id, citation_id)
                    values (%s, %s)
                    on conflict do nothing
                    """,
                    (code_list_id, citation_id),
                )

        return citation_ids

    def _upsert_citation(
        self,
        cur,
        citation_ids: dict[tuple, int],
        document_version_id: int,
        evidence: Evidence,
        anchor_text: str | None,
    ) -> int:
        key = (
            evidence.page_number,
            evidence.section_title,
            evidence.source_kind,
            evidence.quote_text,
            anchor_text,
        )
        if key in citation_ids:
            return citation_ids[key]

        cur.execute(
            """
            insert into citation (
                document_version_id,
                page_number,
                section_title,
                source_kind,
                quote_text,
                anchor_text
            )
            values (%s, %s, %s, %s, %s, %s)
            returning id
            """,
            (
                document_version_id,
                evidence.page_number,
                evidence.section_title,
                evidence.source_kind,
                evidence.quote_text,
                anchor_text,
            ),
        )
        citation_id = cur.fetchone()["id"]
        citation_ids[key] = citation_id
        return citation_id

    def _insert_version_diff_snapshot(
        self,
        cur,
        document: RegulationDocument,
        document_version_id: int,
        result: PipelineResult,
    ) -> int | None:
        if result.version_diff is None:
            return None

        base_version_id = None
        if result.version_diff.base_version_label:
            cur.execute(
                """
                select dv.id
                from document_version dv
                join source_document sd on sd.id = dv.source_document_id
                where sd.jurisdiction = %s
                  and sd.tax_domain = %s
                  and dv.version_label = %s
                order by dv.created_at desc
                limit 1
                """,
                (
                    document.jurisdiction,
                    document.tax_domain,
                    result.version_diff.base_version_label,
                ),
            )
            row = cur.fetchone()
            base_version_id = row["id"] if row else None

        cur.execute(
            """
            insert into version_diff (
                base_version_id,
                candidate_version_id,
                status,
                summary
            )
            values (%s, %s, %s, %s::jsonb)
            returning id
            """,
            (
                base_version_id,
                document_version_id,
                "pending_review" if result.review_items else "auto_approved",
                json.dumps(result.version_diff.summary, ensure_ascii=False),
            ),
        )
        version_diff_id = cur.fetchone()["id"]

        for change in result.version_diff.field_changes:
            cur.execute(
                """
                insert into field_change (
                    version_diff_id,
                    field_code,
                    change_type,
                    risk_level,
                    before_payload,
                    after_payload,
                    auto_approved
                )
                values (%s, %s, %s, %s, %s::jsonb, %s::jsonb, %s)
                """,
                (
                    version_diff_id,
                    change.field_code,
                    change.change_type,
                    change.risk_level,
                    json.dumps(change.before_payload, ensure_ascii=False) if change.before_payload is not None else None,
                    json.dumps(change.after_payload, ensure_ascii=False) if change.after_payload is not None else None,
                    change.risk_level == "low",
                ),
            )

        for item in result.review_items:
            cur.execute(
                """
                insert into review_queue_item (
                    version_diff_id,
                    item_id,
                    risk_level,
                    message,
                    field_code,
                    change_type,
                    payload
                )
                values (%s, %s, %s, %s, %s, %s, %s::jsonb)
                """,
                (
                    version_diff_id,
                    item.item_id,
                    item.risk_level,
                    item.message,
                    item.change.field_code,
                    item.change.change_type,
                    json.dumps(field_change_to_dict(item.change), ensure_ascii=False),
                ),
            )

        return version_diff_id

    def _insert_artifact_snapshot(self, cur, document_version_id: int, artifact_paths: dict[str, Path]) -> int:
        count = 0
        for bundle_type, path in artifact_paths.items():
            if not path.exists():
                continue
            cur.execute(
                """
                insert into publication_bundle (
                    document_version_id,
                    bundle_type,
                    bundle_status,
                    artifact_uri,
                    checksum_sha256
                )
                values (%s, %s, %s, %s, %s)
                """,
                (
                    document_version_id,
                    bundle_type,
                    "published" if bundle_type == "published_bundle" else "draft",
                    str(path),
                    _sha256(path),
                ),
            )
            count += 1
        return count

    def _insert_extraction_run(
        self,
        cur,
        document_version_id: int,
        result: PipelineResult,
        parser_fingerprint: str,
        llm_model: str | None,
        prompt_version: str | None,
        citation_count: int,
        artifact_count: int,
        published: bool,
    ) -> int:
        metrics = {
            "field_count": len(result.bundle.fields),
            "rule_count": len(result.bundle.rules),
            "code_list_count": len(result.bundle.code_lists),
            "validation_issue_count": len(result.validation_issues),
            "review_item_count": len(result.review_items),
            "citation_count": citation_count,
            "artifact_count": artifact_count,
            "published": published,
            "diff_summary": result.version_diff.summary if result.version_diff else None,
        }
        cur.execute(
            """
            insert into extraction_run (
                document_version_id,
                stage,
                status,
                finished_at,
                tool_version,
                llm_model,
                prompt_version,
                metrics
            )
            values (%s, %s, %s, now(), %s, %s, %s, %s::jsonb)
            returning id
            """,
            (
                document_version_id,
                "pipeline",
                "completed",
                parser_fingerprint,
                llm_model,
                prompt_version,
                json.dumps(metrics, ensure_ascii=False),
            ),
        )
        return cur.fetchone()["id"]

    def _materialize_published_bundle(self, document_version_id: int, artifact_paths: dict[str, str]) -> Path:
        existing_published = artifact_paths.get("published_bundle")
        if existing_published:
            published_path = Path(existing_published)
            if published_path.exists():
                return published_path

        candidate_path_str = artifact_paths.get("candidate_bundle")
        if candidate_path_str:
            candidate_path = Path(candidate_path_str)
            if candidate_path.exists():
                published_path = candidate_path.parent / "published_bundle.json"
                if candidate_path.resolve() != published_path.resolve():
                    shutil.copyfile(candidate_path, published_path)
                return published_path

        fallback_dir = Path(__file__).resolve().parent.parent / "artifacts" / "published_versions" / str(document_version_id)
        fallback_dir.mkdir(parents=True, exist_ok=True)
        published_path = fallback_dir / "published_bundle.json"
        bundle_payload = bundle_to_dict(self._load_bundle_by_version_id(document_version_id))
        published_path.write_text(json.dumps(bundle_payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return published_path

    def _read_json_artifact(self, artifact_path: str | None, fallback):
        if not artifact_path:
            return fallback
        path = Path(artifact_path)
        if not path.exists():
            return fallback
        return _normalize_json_value(path.read_text(encoding="utf-8"), fallback)

    def _load_review_items_payload(self, document_version_id: int) -> list[dict[str, object]]:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    select
                        rqi.item_id,
                        rqi.risk_level,
                        rqi.message,
                        rqi.field_code,
                        rqi.change_type,
                        rqi.payload
                    from review_queue_item rqi
                    join version_diff vd on vd.id = rqi.version_diff_id
                    where vd.candidate_version_id = %s
                    order by rqi.created_at asc, rqi.id asc
                    """,
                    (document_version_id,),
                )
                rows = cur.fetchall()
        payload: list[dict[str, object]] = []
        for row in rows:
            change_payload = _normalize_json_value(row["payload"], {})
            payload.append(
                {
                    "item_id": row["item_id"],
                    "risk_level": row["risk_level"],
                    "message": row["message"],
                    "change": change_payload if isinstance(change_payload, dict) else {},
                }
            )
        return payload

    def _load_version_diff_payload(self, document_version_id: int) -> dict[str, object] | None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    select
                        vd.id,
                        vd.summary,
                        base_dv.version_label as base_version_label,
                        candidate_dv.version_label as candidate_version_label
                    from version_diff vd
                    left join document_version base_dv on base_dv.id = vd.base_version_id
                    join document_version candidate_dv on candidate_dv.id = vd.candidate_version_id
                    where vd.candidate_version_id = %s
                    order by vd.created_at desc, vd.id desc
                    limit 1
                    """,
                    (document_version_id,),
                )
                diff_row = cur.fetchone()
                if diff_row is None:
                    return None

                cur.execute(
                    """
                    select
                        field_code,
                        change_type,
                        risk_level,
                        before_payload,
                        after_payload
                    from field_change
                    where version_diff_id = %s
                    order by id asc
                    """,
                    (diff_row["id"],),
                )
                change_rows = cur.fetchall()

        return {
            "base_version_label": diff_row["base_version_label"],
            "candidate_version_label": diff_row["candidate_version_label"],
            "summary": _normalize_json_value(diff_row["summary"], {}) or {},
            "field_changes": [
                {
                    "field_code": row["field_code"],
                    "change_type": row["change_type"],
                    "risk_level": row["risk_level"],
                    "before_payload": _normalize_json_value(row["before_payload"], None),
                    "after_payload": _normalize_json_value(row["after_payload"], None),
                }
                for row in change_rows
            ],
        }
