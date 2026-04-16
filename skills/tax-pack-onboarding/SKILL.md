---
name: tax-pack-onboarding
description: Create a new country-specific tax parser pack from the repository template, wire registry and overlay files, add official source monitoring, and validate the pack with test and quality gate before treating it as ready.
---

## What I do

- Onboard a new country or new tax-domain pack under `skills/`.
- Reuse the existing `tax-parser-core` runtime when possible.
- Keep country-specific logic in the pack and avoid unnecessary `core` changes.
- Drive the pack through `test`, baseline setup, `quality-gate`, and source monitoring.

## When to use me

- A new country needs eInvoice or tax-law parsing support.
- A new jurisdiction should be added as a pack instead of extending an existing pack.
- You want a repeatable onboarding workflow rather than ad hoc parser edits.

## First decision

Before creating a pack, decide whether the target PDF fits an existing parser family.

- If it matches an existing family such as EN16931/UBL, create a new pack and a thin overlay.
- If it does not fit any existing family, stop and extend `tax-parser-core/tax_parser_runtime/families/` first. Do not force a bad fit into an overlay.

## Pack creation workflow

1. Copy the template directory:
   - `templates/tax-pack-country-template`
   - Destination: `skills/tax-pack-<country>-<domain>/`
2. Rename placeholder values in:
   - `pack.json`
   - `profiles/registry.json`
   - `profiles/overlays/country_overlay.py`
   - `sources/official_sources.yaml`
3. Keep changes pack-local unless the issue is clearly shared across multiple countries.
4. Add one real fixture PDF and use it for the first parser run.
5. Run the pack through `test`.
6. If the output is trusted, create the pack baseline.
7. Run `quality-gate`.
8. Run `monitor` and inspect `change_report`, `review_items`, and `followups`.

## Template files

Use these template files as the starting point:

- `templates/tax-pack-country-template/pack.json`
- `templates/tax-pack-country-template/profiles/registry.json`
- `templates/tax-pack-country-template/profiles/overlays/country_overlay.py`
- `templates/tax-pack-country-template/scripts/pack_cli.py`
- `templates/tax-pack-country-template/sources/official_sources.yaml`

## Required edits

### `pack.json`

Set:

- `pack_name`
- `jurisdiction`
- `tax_domain`
- `entry_profile`
- `default_family`

### `profiles/registry.json`

Set:

- real `name`
- `stability`
- `module_path`
- `baseline_path`
- `filename_contains`
- `text_contains`
- `document_language`

Use `experimental` until the pack has a trusted baseline and passes the quality gate.

### `profiles/overlays/*.py`

Keep the overlay thin. Put only country-specific details here:

- table header markers
- note prefixes
- family config tweaks

Do not move generic parsing fixes into the overlay if they belong in the family base.

### `sources/official_sources.yaml`

Treat this as the monitoring contract, not a loose bookmark list.

For each source, define:

- `landing_url`
- `attachment_url` when applicable
- `monitor_strategy`
- `version_signal`
- `review_if`

Prefer stable landing pages over direct PDF links.

## Validation commands

Test the new pack:

```bash
python skills/tax-pack-<country>-<domain>/scripts/pack_cli.py test \
  --pdf <pdf_path> \
  --extractor <profile_name> \
  --outdir <outdir>
```

Run the pack quality gate:

```bash
python skills/tax-pack-<country>-<domain>/scripts/pack_cli.py quality-gate \
  --pdf <pdf_path> \
  --extractor <profile_name> \
  --outdir <outdir>
```

Run source monitoring:

```bash
python skills/tax-pack-<country>-<domain>/scripts/pack_cli.py monitor \
  --outdir <outdir>
```

Run generated follow-ups:

```bash
python skills/tax-pack-<country>-<domain>/scripts/pack_cli.py followups \
  --followups <followups.json> \
  --runner test_extractor \
  --outdir <outdir>
```

## Hard rules

- Do not create a new pack by cloning an existing country pack and leaving hidden country-specific assumptions behind.
- Do not mark a new profile as `stable` until it has a trusted baseline and passes `quality-gate`.
- Do not promote a baseline from an unreviewed parser run.
- Do not edit `tax-parser-core` unless the parser problem is genuinely cross-country.
- Prefer monitoring official landing pages and version signals over search-engine discovery.

## Expected outcome

A successful onboarding ends with:

- a new pack under `skills/`
- a real registry entry and overlay
- a trusted baseline
- a passing `quality-gate`
- a working `official_sources.yaml`
- a runnable `monitor -> followups` loop
