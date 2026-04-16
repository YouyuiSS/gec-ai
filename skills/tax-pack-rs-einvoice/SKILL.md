---
name: tax-pack-rs-einvoice
description: Serbia eInvoice parser pack. Use for Serbia EN16931 extension parsing, source monitoring, follow-up reruns, and pack-scoped quality gate.
---

## What I do

- Provide Serbia eInvoice profiles, overlays, baselines, and official source definitions.
- Delegate execution to the installed `tax-parser-core` skill.

## When to use me

- The target PDF is a Serbia eInvoice specification.
- You need to monitor Serbia eInvoice official sources.
- You need to rerun or gate the Serbia pack.

## Requirement

- Install `tax-parser-core` alongside this pack.

## Main command

```bash
python scripts/pack_cli.py test \
  --pdf <pdf_path> \
  --extractor rs-srbdt-ext-2025 \
  --outdir <outdir>
```
