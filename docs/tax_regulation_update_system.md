# Tax Regulation Continuous Update System

## Goal

Build a versioned, evidence-backed system that can ingest new tax law and e-invoicing specification documents, extract structured field and rule definitions, compare them against the currently published version, and publish validated bundles to downstream systems.

This is not a chatbot feature. It is a document-to-regulation pipeline with AI used only where deterministic parsing is weak.

## Design Principles

1. Version everything
   Never overwrite the active regulation model. Every upload becomes a new candidate version.

2. Evidence first
   Every extracted field, code list, rule, and change must carry page-level evidence.

3. Rules first, AI second
   Use deterministic parsing for explicit structure. Use AI for semantic normalization, ambiguous sections, and change explanation.

4. Explicit is different from inferred
   Store whether a value is explicitly stated in the source or inferred by the system.

5. Publish bundles, not loose rows
   Downstream systems should consume a coherent regulation bundle selected by jurisdiction, tax domain, and effective date.

## Core Entities

- `source_document`
  Raw uploaded file plus checksum and provenance.

- `document_version`
  A candidate regulation version derived from one or more documents.

- `field_definition`
  Atomic field such as `BT-1`, `HR-BT-15`, or a local jurisdiction extension field.

- `rule_definition`
  Cross-field rule, arithmetic rule, presence rule, exclusivity rule, code-list rule, or format rule.

- `citation`
  Evidence span with page number and short quoted text.

- `version_diff`
  Structured comparison between a candidate and a published version.

- `publication_bundle`
  Frozen machine-readable output for downstream consumers.

## End-to-End Pipeline

### 1. Ingestion

Input:

- PDF, DOCX, HTML, scan image, zip of specs
- metadata such as jurisdiction, tax domain, language, source URI, issue date, effective date if known

Actions:

- compute checksum
- store original artifact
- create `source_document`
- create candidate `document_version`

### 2. Document Parsing

Goal:

- recover text blocks
- recover tables
- recover code examples such as XML, JSON, XSD, UBL paths
- preserve page boundaries

Recommended strategy:

- text-native PDF: `pdfplumber`, `pypdf`
- scanned PDF: OCR pass before extraction
- tables: table extractor plus page fallback text blocks
- code blocks: heuristic extraction based on XML tags and syntax markers

Output:

- page-indexed intermediate representation:
  - `pages[].text`
  - `pages[].tables`
  - `pages[].examples`
  - `pages[].headings`

### 3. Deterministic Extraction

This layer should extract anything explicit and stable:

- field ids such as `BT-*`, `BG-*`, `HR-BT-*`, `HR-BG-*`
- business term / field name
- description
- note on use
- data type
- cardinality
- invoice path / credit note path
- local remarks
- code-list references like `UNTDID 5305`, `ISO 4217`, `ISO 3166-1`
- explicit examples
- explicit format constraints like `yyyy-MM-dd`, `hh:mm:ss`, `2 decimal places`

Why this matters:

- deterministic extraction is cheaper
- easier to test
- easier to diff
- much safer than free-form LLM extraction

### 4. LLM Enrichment

The LLM should receive:

- only relevant chunks
- extracted table row candidate
- surrounding text block
- examples
- strict JSON schema

The LLM should do only these jobs:

- normalize business meaning
- classify rule type
- map code-list references into canonical names
- resolve ambiguous formatting language
- summarize change impact between versions
- mark low-confidence cases for review

The LLM should not invent:

- missing field ids
- missing paths
- missing code-list values
- lengths or decimal scales not stated by source

### 5. Canonical Normalization

Map extracted outputs into one canonical model:

- `jurisdiction`
- `tax_domain`
- `field_code`
- `field_name`
- `field_kind = atomic | group`
- `data_type`
- `occurrence_min`
- `occurrence_max`
- `constraints`
- `value_set_refs`
- `invoice_path`
- `credit_note_path`
- `semantic_notes`
- `evidence[]`
- `origin = explicit | inferred`
- `confidence`

### 6. Validation

Run machine validation before human review:

- required columns present
- page evidence present
- field ids unique within version
- path syntax sanity checks
- code-list reference normalization checks
- numeric constraints internally consistent
- rule references point to existing fields

### 7. Version Diff

Compare candidate version to current published version.

Diff types:

- field added
- field removed
- field renamed
- path changed
- cardinality changed
- data type changed
- format changed
- code-list changed
- rule added
- rule removed
- rule logic changed

Assign risk per change:

- low: example text changed, note wording changed
- medium: code list reference changed, new optional field, path changed
- high: required field removed, cardinality tightened, numeric format changed, arithmetic rule changed

### 8. Human Review Gate

Auto-approve only low-risk changes with strong evidence.

Everything else goes to a review queue with:

- before / after payload
- evidence pages
- affected fields
- downstream impact summary
- suggested reviewer action

### 9. Publication

Publish a regulation bundle, not raw extraction rows.

Recommended artifacts:

- `fields.csv`
- `fields.json`
- `rules.json`
- `code_lists.json`
- `version_diff.json`
- generated validation DSL or SQL checks

Bundle selection rule:

- `jurisdiction`
- `tax_domain`
- `effective_date`
- `bundle_status = published`

## Where AI Adds Value

- section classification in heterogeneous documents
- change explanation for reviewers
- normalization of rule wording into typed rule categories
- multilingual alignment across English and local-language specs
- extracting hidden semantics from prose paragraphs when no table is present

## Where AI Should Not Be the Source of Truth

- published code list values
- exact effective dates
- field existence when source is unclear
- final runtime validation behavior
- published bundle selection

## Review Queue Design

Each review item should show:

- candidate version
- change type
- risk level
- evidence snippets
- extracted structured payload
- previous published payload
- AI explanation
- approve / reject / edit action

Suggested reviewer buckets:

- parser failure
- ambiguous code list
- rule conflict
- suspected OCR corruption
- possible field rename
- possible field split / merge

## Suggested Release Policy

Auto-publish only when all conditions hold:

- parser validation passed
- no high-risk diffs
- confidence above threshold
- required evidence attached for every changed item

Otherwise:

- hold candidate bundle
- require reviewer decision

## Suggested Tech Stack

- storage: PostgreSQL
- artifact storage: S3 or local object store
- parser workers: Python
- orchestration: Celery, Temporal, or lightweight job queue
- review UI: internal web app
- search: Postgres full text first, vector index optional

## Minimal Viable Implementation

Phase 1:

- single jurisdiction
- PDF only
- deterministic extraction of fields and rules
- CSV and JSON outputs
- manual review in admin table

Phase 2:

- version diff
- auto-risk scoring
- evidence-backed reviewer UI

Phase 3:

- multi-jurisdiction model
- OCR support
- generated validation bundle for downstream invoicing systems

## Recommended Operating Model

1. Upload new regulation document
2. Parse and extract
3. Build candidate version
4. Diff against active published version
5. Review medium and high risk changes
6. Publish new bundle
7. Downstream systems pick bundle by effective date

That model is stable enough to survive frequent tax-law updates without turning your AI layer into an untraceable black box.
