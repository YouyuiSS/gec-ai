---
name: tax-law-parser
description: Parse tax regulation PDFs into structured field catalogs, update extractor scripts when document structure changes, and validate outputs before delivery.
license: Internal
compatibility: opencode
metadata:
  domain: tax
  language: python
  workflow: document-parsing
---

## What I do

- Parse tax regulation PDFs into structured JSON and CSV field catalogs.
- Reuse an existing extractor when the document layout still matches a known template.
- Create or update a Python extractor directly when the PDF layout changes.
- Validate the output before reporting success.

## When to use me

- A new tax law PDF needs field extraction.
- An existing tax-law parser no longer matches the latest PDF format.
- You need a repeatable parser script that can be maintained over time.

## OpenCode-native behavior

- Assume the user can attach the PDF directly in chat.
- Use the attached file or the path already available in the agent context.
- Do not ask the user to `cd`, activate a virtualenv, or export model variables unless they explicitly ask for manual CLI instructions.
- Do not ask the user to configure a model when running inside OpenCode. Use the model OpenCode already has.
- Edit extractor Python files directly, then use the local scripts in this skill to test them.

## Directory layout

- `scripts/run_tax_parser.py`
  Main entry point. Selects an extractor and writes `field_catalog.json`, `field_catalog.csv`, and `run_report.json`.
- `scripts/validate_tax_output.py`
  Validates the generated JSON output and fails fast on malformed records.
- `scripts/compare_field_catalogs.py`
  Compares a generated catalog to a trusted baseline and reports missing, extra, and changed fields.
- `scripts/test_extractor.py`
  Runs `py_compile`, parser execution, output validation, and optional baseline comparison in one step.
- `scripts/repair_extractor_brief.py`
  Optional helper that reruns `test_extractor.py`, scores the output, and writes a repair brief for the agent. It never calls a model.
- `scripts/bootstrap_extractor.py`
  Scaffolds a new extractor module and appends a stub registry entry.
- `extractors/registry.json`
  Maps filename and text hints to extractor modules.
- `extractors/hr_einvoice_legacy.py`
  Working profile that wraps the existing Croatia eInvoice parser.
- `extractors/template_generic.py`
  Starting point for a new extractor when a PDF format changes.
- `schemas/tax_field_catalog.schema.json`
  Canonical record shape for JSON outputs.
- `prompts/adapt_new_tax_law.md`
  Copy-ready instructions for adapting the skill to a new format.

## Standard workflow

1. Inspect the input PDF and decide whether an existing extractor still matches.
2. Try the current parser first.
3. If auto-selection fails or the output is obviously wrong:
   - inspect `extractors/registry.json`
   - create or update a document-specific extractor in `extractors/`
   - use `template_generic.py` as the starting point when needed
   - update `extractors/registry.json`
4. Test the extractor end-to-end:
   - run `scripts/test_extractor.py`
   - if the first pass is still wrong, optionally run `scripts/repair_extractor_brief.py`
5. Validate:
   - `python3 -m py_compile <changed_python_files>`
   - `python .opencode/skills/tax-law-parser/scripts/validate_tax_output.py --json <field_catalog.json>`
   - compare to a trusted baseline with `compare_field_catalogs.py` whenever one exists
6. Report the chosen extractor, output paths, record count, and any residual uncertainty.

## Hard rules

- Never overwrite a validated extractor for a different document family. Add a new extractor instead.
- Keep old extractors available so historical PDFs remain reproducible.
- Do not claim a parser works until it has been executed against the target PDF.
- Always run `py_compile` on changed Python files before finishing.
- Always run the output validator before finishing.
- Whenever a trusted baseline exists, run the compare script before finishing.
- If no extractor matches, say that clearly and create a new extractor rather than forcing the old one.
- Prefer editing Python directly over calling a secondary model-invoking helper.
- Use diagnostic scripts to produce evidence, then edit extractor Python directly in the agent.

## Output contract

Each record in `field_catalog.json` must include:

- `field_id`
- `field_name`
- `field_description`
- `note_on_use`
- `data_type`
- `cardinality`
- `invoice_path`
- `credit_note_path`
- `report_path`
- `sample_value`
- `value_set`
- `interpretation`
- `rules`
- `source_pages`
- `min_char_length`
- `max_char_length`
- `min_decimal_precision`
- `max_decimal_precision`
- `extractor_name`

## Common commands

Run the parser:

```bash
python .opencode/skills/tax-law-parser/scripts/run_tax_parser.py \
  --pdf <pdf_path> \
  --outdir <outdir>
```

Scaffold a new extractor:

```bash
python .opencode/skills/tax-law-parser/scripts/bootstrap_extractor.py \
  --name hr-v2-layout \
  --description "HR eInvoice spec, revised 2026 layout" \
  --filename-hint "2026" \
  --text-hint "Business term"
```

Test an extractor end-to-end:

```bash
python .opencode/skills/tax-law-parser/scripts/test_extractor.py \
  --pdf <pdf_path> \
  --extractor <extractor_name> \
  --outdir <outdir> \
  --baseline <baseline_field_catalog.json>
```

Generate a repair brief:

```bash
python .opencode/skills/tax-law-parser/scripts/repair_extractor_brief.py \
  --pdf <pdf_path> \
  --extractor <extractor_name> \
  --outdir <brief_outdir> \
  --baseline <baseline_field_catalog.json>
```

Validate output:

```bash
python .opencode/skills/tax-law-parser/scripts/validate_tax_output.py \
  --json artifacts/tax-skill/demo/field_catalog.json
```

Compare to a trusted baseline:

```bash
python .opencode/skills/tax-law-parser/scripts/compare_field_catalogs.py \
  --baseline <baseline_field_catalog.json> \
  --candidate <candidate_field_catalog.json> \
  --outdir <diff_outdir>
```

## OpenCode user instructions

When the user uploads a new PDF, the agent should follow this order:

1. Run the parser with auto-selection.
2. If the result looks correct, validate and return the output paths.
3. If the result looks wrong, create or update an extractor Python module directly.
4. Run `test_extractor.py`.
5. If a baseline exists, run the compare script and summarize missing, extra, and changed fields.
6. If the first revision still fails badly, run `repair_extractor_brief.py`, inspect the brief, then edit the extractor directly.

The user should not need to know repository paths or environment setup for normal use.

## If the PDF format changed

- Start from `extractors/template_generic.py`.
- Copy it into a new document-specific extractor and implement parsing logic there.
- Keep the parser logic narrow and document-specific.
- Prefer deterministic extraction over free-form LLM extraction inside the extractor.
- Use the prompt in `prompts/adapt_new_tax_law.md` when asking the agent to update this skill.
