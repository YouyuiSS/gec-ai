# Tax Skill Installation Guide

This guide is for external users who want to install and run the tax parser skills from this repository.

## Skills

This repository exposes three installable skills:

- `tax-parser-core`
  Shared runtime, validator, monitor, follow-up runner, and quality gate.
- `tax-pack-rs-einvoice`
  Serbia eInvoice pack.
- `tax-pack-hr-einvoice`
  Croatia eInvoice pack.

Install `tax-parser-core` together with at least one country pack.

## What To Install

Choose one of these combinations:

- Serbia only:
  `tax-parser-core` + `tax-pack-rs-einvoice`
- Croatia only:
  `tax-parser-core` + `tax-pack-hr-einvoice`
- Both countries:
  `tax-parser-core` + `tax-pack-rs-einvoice` + `tax-pack-hr-einvoice`

## Prerequisites

1. Codex must already be installed.
2. You need a Python interpreter with the parser dependencies available.
3. After installing skills, restart Codex so the new skills are discovered.

Minimum parser dependency for execution is `pdfplumber`.

If you are running from a checkout of this repository, install dependencies from [requirements.txt](/Users/xueyunsong/Documents/GitHub/gec-ai/requirements.txt):

```bash
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
```

If you are only installing the skills and not cloning the repository, install the required runtime packages directly into the Python environment you will use to run the pack scripts.

Minimum example:

```bash
python -m venv .venv
. .venv/bin/activate
pip install pdfplumber
```

## Install From GitHub

Use Codex's built-in installer script:

```bash
python ~/.codex/skills/.system/skill-installer/scripts/install-skill-from-github.py \
  --repo YouyuiSS/gec-ai \
  --path skills/tax-parser-core skills/tax-pack-rs-einvoice skills/tax-pack-hr-einvoice
```

Install only Serbia:

```bash
python ~/.codex/skills/.system/skill-installer/scripts/install-skill-from-github.py \
  --repo YouyuiSS/gec-ai \
  --path skills/tax-parser-core skills/tax-pack-rs-einvoice
```

Install only Croatia:

```bash
python ~/.codex/skills/.system/skill-installer/scripts/install-skill-from-github.py \
  --repo YouyuiSS/gec-ai \
  --path skills/tax-parser-core skills/tax-pack-hr-einvoice
```

If you need to install from a branch before merge, add `--ref <branch>`.

Example:

```bash
python ~/.codex/skills/.system/skill-installer/scripts/install-skill-from-github.py \
  --repo YouyuiSS/gec-ai \
  --ref codex/tax-skill-split \
  --path skills/tax-parser-core skills/tax-pack-rs-einvoice skills/tax-pack-hr-einvoice
```

The installer places these skills under `~/.codex/skills/` by default:

- `~/.codex/skills/tax-parser-core`
- `~/.codex/skills/tax-pack-rs-einvoice`
- `~/.codex/skills/tax-pack-hr-einvoice`

## Run After Install

Use the Python interpreter that has your parser dependencies installed.

Serbia pack test:

```bash
python ~/.codex/skills/tax-pack-rs-einvoice/scripts/pack_cli.py test \
  --pdf <pdf_path> \
  --extractor rs-srbdt-ext-2025 \
  --outdir <outdir>
```

Croatia pack quality gate:

```bash
python ~/.codex/skills/tax-pack-hr-einvoice/scripts/pack_cli.py quality-gate \
  --pdf <pdf_path> \
  --extractor hr-einvoice-legacy \
  --outdir <outdir>
```

Monitor Serbia official sources:

```bash
python ~/.codex/skills/tax-pack-rs-einvoice/scripts/pack_cli.py monitor \
  --outdir <outdir>
```

Monitor Croatia official sources:

```bash
python ~/.codex/skills/tax-pack-hr-einvoice/scripts/pack_cli.py monitor \
  --outdir <outdir>
```

## How The Three Skills Work Together

- `tax-parser-core` owns shared runtime behavior.
- Country packs own `sources`, `profiles`, `overlays`, and `baselines`.
- Each pack delegates execution to the installed sibling `tax-parser-core`.
- Pack commands fail if the matching `tax-parser-core` skill is not installed alongside them.

## Known Limits

- These skills do not install Python packages for you.
- Source monitoring depends on upstream government sites staying reachable.
- Croatia source monitoring can still surface upstream `HTTP 500` errors from `porezna.gov.hr`; that is a source-side issue, not an installation problem.
