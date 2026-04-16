---
name: tax-pack-xx-einvoice
description: Template pack for a new country-specific tax parser. Copy this directory, rename it, and replace placeholders before use.
---

## What I do

- Provide a starting pack structure for a new country or new tax domain.
- Show where to put registry, overlay, sources, baselines, and fixtures.
- Delegate execution to a sibling `tax-parser-core` skill after placeholders are replaced.

## Before Use

- Copy this template under `skills/`
- Rename the directory
- Update `pack.json`
- Update `profiles/registry.json`
- Replace placeholder values in the overlay and source definitions

## Main commands after customization

```bash
python scripts/pack_cli.py test \
  --pdf <pdf_path> \
  --extractor xx-example-profile \
  --outdir <outdir>
```
