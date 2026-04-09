from __future__ import annotations

import argparse
from pathlib import Path

from .runtime import PipelineRunRequest, execute_pipeline_request, maybe_date


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the local tax regulation update pipeline.")
    parser.add_argument("--pdf", required=True, help="Path to the source regulation PDF.")
    parser.add_argument("--jurisdiction", required=True, help="Jurisdiction code, for example HR.")
    parser.add_argument("--tax-domain", required=True, help="Tax domain, for example einvoice.")
    parser.add_argument("--language-code", default="en", help="Language code.")
    parser.add_argument("--version-label", required=True, help="Candidate version label.")
    parser.add_argument("--issued-on", help="Issued date in YYYY-MM-DD.")
    parser.add_argument("--effective-from", help="Effective-from date in YYYY-MM-DD.")
    parser.add_argument("--effective-to", help="Effective-to date in YYYY-MM-DD.")
    parser.add_argument("--published-bundle", help="Path to a previously published bundle JSON.")
    parser.add_argument(
        "--outdir",
        required=True,
        help="Directory for generated bundle, diff, validation, and review outputs.",
    )
    parser.add_argument(
        "--auto-publish",
        action="store_true",
        help="Write published_bundle.json when there are no validation issues or review items.",
    )
    parser.add_argument(
        "--persist-to-db",
        action="store_true",
        help="Persist the candidate version, diff, and artifacts into Postgres.",
    )
    parser.add_argument(
        "--db-name",
        default="tax_regulation_demo",
        help="Database name to use with SPRING_DATASOURCE_* connection settings.",
    )
    parser.add_argument(
        "--create-db",
        action="store_true",
        help="Create the target database if it does not already exist.",
    )
    parser.add_argument(
        "--db-baseline-version-label",
        help="Load the baseline bundle from Postgres by version label instead of a local JSON file.",
    )
    parser.add_argument(
        "--db-load-latest-published",
        action="store_true",
        help="Load the latest published bundle from Postgres as the baseline.",
    )
    parser.add_argument(
        "--use-llm-enricher",
        action="store_true",
        help="Use LangChain structured output to enrich low-confidence or incomplete fields.",
    )
    parser.add_argument(
        "--llm-model",
        help="LangChain model identifier, for example openai:gpt-5-mini.",
    )
    parser.add_argument(
        "--llm-max-fields-per-batch",
        type=int,
        default=8,
        help="Maximum fields to send in one LangChain structured-output batch.",
    )
    parser.add_argument(
        "--llm-max-candidate-fields",
        type=int,
        default=24,
        help="Maximum number of candidate fields to enrich in one run.",
    )
    return parser.parse_args()
def run() -> int:
    args = parse_args()
    request = PipelineRunRequest(
        source_path=Path(args.pdf),
        outdir=Path(args.outdir),
        jurisdiction=args.jurisdiction,
        tax_domain=args.tax_domain,
        version_label=args.version_label,
        language_code=args.language_code,
        issued_on=maybe_date(args.issued_on),
        effective_from=maybe_date(args.effective_from),
        effective_to=maybe_date(args.effective_to),
        published_bundle_path=Path(args.published_bundle) if args.published_bundle else None,
        auto_publish=args.auto_publish,
        persist_to_db=args.persist_to_db,
        db_name=args.db_name,
        create_db=args.create_db,
        db_baseline_version_label=args.db_baseline_version_label,
        db_load_latest_published=args.db_load_latest_published,
        use_llm_enricher=args.use_llm_enricher,
        llm_model=args.llm_model,
        llm_max_fields_per_batch=args.llm_max_fields_per_batch,
        llm_max_candidate_fields=args.llm_max_candidate_fields,
    )
    execution = execute_pipeline_request(request)

    print(f"candidate bundle: {execution.artifact_paths['candidate_bundle']}")
    print(f"validation issues: {execution.artifact_paths['validation_issues']}")
    print(f"version diff: {execution.artifact_paths['version_diff']}")
    print(f"review items: {execution.artifact_paths['review_items']}")
    print(f"run summary: {request.outdir.resolve() / 'run_summary.json'}")
    if execution.persistence_summary is not None:
        print(
            "database persistence: "
            f"{execution.persistence_summary.database_name} "
            f"(document_version_id={execution.persistence_summary.document_version_id}, "
            f"extraction_run_id={execution.persistence_summary.extraction_run_id})"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
