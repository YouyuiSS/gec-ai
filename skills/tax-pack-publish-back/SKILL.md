---
name: tax-pack-publish-back
description: Take a locally modified tax parser pack, map it back to the editable repository source, run test and quality gate, and prepare a controlled patch, commit, or PR instead of treating the installed skill directory as the source of truth.
---

## What I do

- Handle publish-back for locally modified tax parser packs.
- Keep GitHub as the source of truth.
- Prevent direct long-term editing of installed skill directories under `~/.codex/skills/`.
- Ensure pack updates go through validation before being published back.

## When to use me

- A user modified a local installed pack and wants the change pushed upstream.
- A local pack fix should become a repo commit or PR.
- You need to move from “local repair” to “reviewed upstream update”.

## Core rule

Treat installed skill directories as runtime copies, not as the authoritative repository state.

Preferred truth source:

- editable repo clone

Not preferred truth source:

- `~/.codex/skills/tax-pack-*`

## Required workflow

1. Identify the modified pack.
2. Determine whether the changes live in:
   - installed skill directory
   - editable repo clone
   - temporary override workspace
3. If the changes are only in an installed skill directory, copy or replay them into the editable repo clone.
4. Run pack validation from the repo clone:
   - `test`
   - `quality-gate`
5. Only after validation passes:
   - create a commit
   - push a branch
   - open or update a PR

## What to look for

Inspect:

- `pack.json`
- `profiles/registry.json`
- `profiles/overlays/*.py`
- `sources/official_sources.yaml`
- `baselines/` only if a trusted baseline promotion is explicitly intended

## Hard rules

- Do not treat `~/.codex/skills/` as the permanent source of truth.
- Do not publish back unvalidated parser changes.
- Do not promote a baseline from an unreviewed local run.
- Do not bypass `quality-gate` for a profile that should be `stable`.
- Do not assume GitHub can infer local installed-skill edits automatically.

## Validation commands

From the editable repo clone, run:

```bash
python skills/tax-pack-<country>-<domain>/scripts/pack_cli.py test \
  --pdf <pdf_path> \
  --extractor <profile_name> \
  --outdir <outdir>
```

```bash
python skills/tax-pack-<country>-<domain>/scripts/pack_cli.py quality-gate \
  --pdf <pdf_path> \
  --extractor <profile_name> \
  --outdir <outdir>
```

## Expected outcome

A successful publish-back ends with:

- the fix replayed into the editable repo clone
- validation evidence captured
- a commit or PR against the GitHub source repository

The installed skill may still exist locally, but it is no longer the only copy that matters.
