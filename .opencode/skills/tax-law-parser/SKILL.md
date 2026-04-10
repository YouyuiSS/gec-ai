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
  Main entry point. Selects a profile from the skill registry and writes `field_catalog.json`, `field_catalog.csv`, and `run_report.json`.
- `scripts/validate_tax_output.py`
  Validates the generated JSON output and fails fast on malformed records.
- `scripts/compare_field_catalogs.py`
  Compares a generated catalog to a trusted baseline and reports missing, extra, and changed fields.
- `scripts/test_extractor.py`
  Runs `py_compile`, parser execution, output validation, and optional baseline comparison in one step.
- `scripts/repair_extractor_brief.py`
  Optional helper that reruns `test_extractor.py`, scores the output, and writes a repair brief for the agent. It never calls a model.
- `scripts/bootstrap_extractor.py`
  Scaffolds either a family overlay under `profiles/` or a legacy flat extractor under `extractors/`.
- `scripts/promote_baseline.py`
  Copies a verified `field_catalog.json` into `baselines/` and writes provenance metadata.
- `profiles/registry.json`
  Primary registry for family-aware profiles. It maps filename and text hints to family overlays.
- `profiles/families/en16931_ubl/base.py`
  Shared parser for EN16931/UBL-style table specifications.
- `profiles/families/en16931_ubl/hr_overlay.py`
  Croatia overlay backed by the existing project script.
- `profiles/families/en16931_ubl/rs_overlay.py`
  Serbia overlay backed by the EN16931/UBL family parser.
- `extractors/registry.json`
  Legacy compatibility registry for flat extractors that have not migrated yet.
- `extractors/template_generic.py`
  Starting point for a legacy flat extractor when no family fits yet.
- `references/parser-families.md`
  Overview of supported parser families and when to reuse them.
- `references/overlays.md`
  Rules for what belongs in family base code versus jurisdiction overlays.
- `references/repair-brief.md`
  How to interpret the repair brief before editing parser code.
- `references/repair-playbook.md`
  Tactical repair rules: when to change registry, overlay, or family base, and what to verify before promoting a baseline.
- `baselines/<jurisdiction>/<profile>/field_catalog.json`
  Trusted profile baselines used by `test_extractor.py` when `--baseline` is omitted.
- `schemas/tax_field_catalog.schema.json`
  Canonical record shape for JSON outputs.
- `prompts/adapt_new_tax_law.md`
  Copy-ready instructions for adapting the skill to a new format.

## Standard workflow

1. Inspect the input PDF and decide whether an existing extractor still matches.
2. Try the current parser first.
3. If auto-selection fails or the output is obviously wrong:
   - inspect `profiles/registry.json`
   - if the PDF still matches a known family, create or update a family overlay in `profiles/families/<family>/`
   - if no family fits yet, create or update a document-specific extractor in `extractors/`
   - use the family references under `references/` before changing a base parser
   - update the appropriate registry
4. Test the extractor end-to-end:
   - run `scripts/test_extractor.py`
   - if a trusted baseline exists under `baselines/`, `test_extractor.py` will pick it up automatically
   - if the first pass is still wrong, run `scripts/repair_extractor_brief.py`, then read `references/repair-playbook.md`
5. Validate:
   - `python3 -m py_compile <changed_python_files>`
   - `python .opencode/skills/tax-law-parser/scripts/validate_tax_output.py --json <field_catalog.json>`
   - compare to a trusted baseline with `compare_field_catalogs.py` whenever one exists
6. Report the chosen extractor, output paths, record count, and any residual uncertainty.

## Hard rules

- Never overwrite a validated extractor for a different document family. Add a new extractor instead.
- Prefer a family overlay over a new flat extractor whenever the PDF still fits an existing document family.
- Only change a family base parser when the issue is clearly shared across multiple overlays.
- After reading a repair brief, decide the edit scope with `references/repair-playbook.md` before changing code.
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
  --family en16931_ubl \
  --name hr-v2-layout \
  --description "HR eInvoice spec, revised 2026 layout" \
  --jurisdiction HR \
  --tax-domain einvoice \
  --language en \
  --filename-hint "2026" \
  --text-hint "Business term"
```

Test an extractor end-to-end:

```bash
python .opencode/skills/tax-law-parser/scripts/test_extractor.py \
  --pdf <pdf_path> \
  --extractor <extractor_name> \
  --outdir <outdir>
```

If the default baseline is not present or you need to override it, add:

```bash
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

Promote a verified run to the default baseline:

```bash
python .opencode/skills/tax-law-parser/scripts/promote_baseline.py \
  --extractor <extractor_name> \
  --source <verified_field_catalog.json> \
  --force
```

## OpenCode user instructions

When the user uploads a new PDF, the agent should follow this order:

1. Run the parser with auto-selection.
2. If the result looks correct, validate and return the output paths.
3. If the result looks wrong, first decide whether the PDF belongs to an existing family.
4. If it does, create or update a family overlay. If it does not, create or update a flat extractor.
5. Run `test_extractor.py`.
6. If a baseline exists, run the compare script and summarize missing, extra, and changed fields.
7. If the first revision still fails badly, run `repair_extractor_brief.py`, inspect the brief, read `references/repair-playbook.md`, then edit the extractor directly.

The user should not need to know repository paths or environment setup for normal use.

## If the PDF format changed

- First check whether the PDF still belongs to an existing family under `profiles/families/`.
- If it does, start from that family's `template_overlay.py`.
- If no family fits yet, start from `extractors/template_generic.py`.
- Keep shared table logic in the family base parser and keep jurisdiction-specific logic in the overlay.
- Keep the parser logic deterministic and document-specific.
- Prefer deterministic extraction over free-form LLM extraction inside the extractor.
- Use the prompt in `prompts/adapt_new_tax_law.md` when asking the agent to update this skill.
