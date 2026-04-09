# Tax Pipeline Scaffold

This folder is a starter kit for a tax regulation continuous-update pipeline.

The local demo now supports:

- PDF parsing with `pdfplumber`
- deterministic extraction from the existing Croatia eInvoice spec parser
- optional LangChain structured-output enrichment for low-confidence or incomplete fields
- local JSON bundle outputs
- Postgres persistence for source documents, document versions, fields, rules, code lists, diffs, review queue items, and artifacts

## Suggested Flow

1. ingest document
2. parse into page-indexed intermediate representation
3. run deterministic extraction
4. run LLM enrichment
5. normalize into canonical bundle
6. validate bundle
7. diff against currently published version
8. create review items
9. publish bundle

## Files

- `models.py`
  Shared dataclasses for fields, rules, evidence, bundles, and diffs.

- `orchestrator.py`
  Protocol-based orchestration skeleton for parser, extractors, diff engine, review gate, and publisher.

## Next Implementation Steps

1. Add provider-specific LangChain integration packages for the model vendors you want to use in production.
2. Add migration management for `sql/tax_regulation_schema.sql`.
3. Add a simple admin review UI or CLI.
4. Add publish workflows that promote reviewed candidate versions to `published`.

## Local Demo

Install dependencies:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Run with local JSON artifacts only:

```bash
python -m tax_pipeline \
  --pdf assets/ticket/Specification-of-the-usecase-of-eInvoice-with-HR-extensions.pdf \
  --jurisdiction HR \
  --tax-domain einvoice \
  --language-code en \
  --version-label 2025.1 \
  --outdir artifacts/demo-2025.1
```

Optional:

- `--published-bundle /path/to/published_bundle.json`
- `--issued-on 2025-04-25`
- `--effective-from 2025-05-01`
- `--auto-publish`

## Web Console

The repo now includes a lightweight browser UI backed by the same Python runtime used by the CLI.

Start it with:

```bash
python -m tax_ui
```

Open:

```text
http://127.0.0.1:8000
```

The web console supports:

- choosing a sample PDF from `assets/ticket`
- uploading a custom PDF
- toggling LLM enrichment
- toggling Postgres persistence
- listing persisted document versions from Postgres
- opening a persisted version and inspecting its stored bundle
- publishing a candidate version directly from the browser
- inspecting extracted fields, validation issues, review items, and generated artifacts

Web runs write their outputs under:

```text
artifacts/web_ui/runs/<run_id>
```

## LangChain Enrichment

The pipeline can optionally run a second-pass structured enrichment step for fields that are inferred, missing semantic notes, or missing obvious format hints.

The default install includes `langchain` and `langchain-openai`, so OpenAI-compatible chat-completions endpoints can be used directly.

Set the model via CLI or environment variable:

```bash
export TAX_PIPELINE_LLM_MODEL='openai:gpt-5-mini'
```

For an OpenAI-compatible local endpoint, these environment variables also work:

```bash
export OPENAI_API_KEY='local-codex-key'
export OPENAI_BASE_URL='http://127.0.0.1:8080/v1'
export OPENAI_MODEL='gpt-5.4'
```

Run with structured enrichment enabled:

```bash
python -m tax_pipeline \
  --pdf assets/ticket/Specification-of-the-usecase-of-eInvoice-with-HR-extensions.pdf \
  --jurisdiction HR \
  --tax-domain einvoice \
  --language-code en \
  --version-label 2025.1-llm \
  --issued-on 2025-04-25 \
  --effective-from 2025-05-01 \
  --outdir artifacts/demo-2025.1-llm \
  --use-llm-enricher \
  --llm-model openai:gpt-5-mini \
  --llm-max-fields-per-batch 6 \
  --llm-max-candidate-fields 18
```

Current behavior:

- deterministic extraction still owns the canonical field/rule skeleton
- LangChain only enriches selected field metadata
- if LangChain is disabled, the pipeline keeps using `NoopLLMEnricher`
- if `--llm-model` is omitted, the pipeline falls back to `TAX_PIPELINE_LLM_MODEL`, then `OPENAI_MODEL`
- for local OpenAI-compatible endpoints such as `127.0.0.1`, the enricher forces single-field batches because multi-field JSON extraction was less stable in testing

## Postgres Demo

The CLI reads Spring-style environment variables:

```bash
export SPRING_DATASOURCE_URL='jdbc:postgresql://127.0.0.1:5432'
export SPRING_DATASOURCE_USERNAME='xueyunsong'
export SPRING_DATASOURCE_PASSWORD=''
```

Create a dedicated database, persist the candidate version, and mark it as published when there are no review items:

```bash
python -m tax_pipeline \
  --pdf assets/ticket/Specification-of-the-usecase-of-eInvoice-with-HR-extensions.pdf \
  --jurisdiction HR \
  --tax-domain einvoice \
  --language-code en \
  --version-label 2025.1 \
  --issued-on 2025-04-25 \
  --effective-from 2025-05-01 \
  --outdir artifacts/demo-2025.1-db \
  --create-db \
  --persist-to-db \
  --db-name tax_regulation_demo \
  --auto-publish
```

Use the latest published version from Postgres as the diff baseline:

```bash
python -m tax_pipeline \
  --pdf assets/ticket/Specification-of-the-usecase-of-eInvoice-with-HR-extensions.pdf \
  --jurisdiction HR \
  --tax-domain einvoice \
  --language-code en \
  --version-label 2025.1-recheck \
  --issued-on 2025-04-25 \
  --effective-from 2025-05-01 \
  --outdir artifacts/demo-2025.1-recheck-db \
  --persist-to-db \
  --db-name tax_regulation_demo \
  --db-load-latest-published
```
