---
name: tax-pack-hr-einvoice
description: Croatia eInvoice parser pack. Use for Croatia HR extension parsing, source monitoring, follow-up reruns, and pack-scoped quality gate.
---

## What I do

- Provide Croatia eInvoice profiles, overlays, baselines, and official source definitions.
- Delegate execution to the installed `tax-parser-core` skill.

## When to use me

- The target PDF is a Croatia eInvoice specification.
- You need to monitor Croatia eInvoice official sources.
- You need to rerun or gate the Croatia pack.

## Requirement

- Install `tax-parser-core` alongside this pack.

## Main command

```bash
python scripts/pack_cli.py test \
  --pdf <pdf_path> \
  --extractor hr-einvoice-legacy \
  --outdir <outdir>
```
