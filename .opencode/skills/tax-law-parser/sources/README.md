# Source Registry

This directory stores official-source registries for jurisdictions handled by the
tax-law-parser skill.

The intent is to make source monitoring explicit before moving to per-pack
skills. For now, each jurisdiction gets its own `official_sources.yaml`.

## Principles

- Track landing pages first, not only direct PDF URLs.
- Treat direct download URLs as hints, not the source of truth.
- Record how a monitor should detect change:
  - landing page HTML checksum
  - attachment checksum
  - extracted version text from page or PDF
- Keep legal and technical sources separate.

## Layout

```text
sources/
  index.yaml
  hr/
    official_sources.yaml
  rs/
    official_sources.yaml
```

## Monitor command

```bash
python .opencode/skills/tax-law-parser/scripts/monitor_official_sources.py \
  --outdir artifacts/tax-source-monitor
```

Filter by jurisdiction when needed:

```bash
python .opencode/skills/tax-law-parser/scripts/monitor_official_sources.py \
  --jurisdiction RS \
  --outdir artifacts/tax-source-monitor-rs
```

Use gate flags when wiring this into cron, CI, or future automations:

```bash
python .opencode/skills/tax-law-parser/scripts/monitor_official_sources.py \
  --outdir artifacts/tax-source-monitor \
  --fail-on-change \
  --fail-on-error
```

Generated artifacts now include:

- `current_snapshot.json`
- `latest_snapshot.json`
- `change_report.json`
- `change_report.md`
- `review_items.json`
- `review_items.md`
- `followups.json`
- `followups.md`

When a source is new, changed, or has a fetch error, the monitor also saves
local copies under:

- `source_artifacts/<source_id>/landing.*`
- `source_artifacts/<source_id>/attachment.*`
- `source_artifacts/<source_id>/artifact_meta.json`

This is meant to make the next parser rerun or manual review reproducible.

## Follow-up execution

Execute actionable specification follow-ups through the skill test chain:

```bash
python .opencode/skills/tax-law-parser/scripts/run_source_followups.py \
  --followups artifacts/tax-source-monitor-rs-fresh/followups.json \
  --runner test_extractor \
  --outdir artifacts/tax-followup-exec-rs
```

Dry-run first if you only want the planned commands:

```bash
python .opencode/skills/tax-law-parser/scripts/run_source_followups.py \
  --followups artifacts/tax-source-monitor-rs-fresh/followups.json \
  --runner test_extractor \
  --dry-run \
  --outdir artifacts/tax-followup-plan-rs
```

There is also a `tax_pipeline` runner for teams that want to route newly
downloaded source PDFs into the pipeline scaffold:

```bash
python .opencode/skills/tax-law-parser/scripts/run_source_followups.py \
  --followups artifacts/tax-source-monitor-rs-fresh/followups.json \
  --runner tax_pipeline \
  --dry-run \
  --outdir artifacts/tax-followup-pipeline-plan-rs
```

## Field conventions

- `source_kind`: broad class of source such as `specification`, `law`, or `legal_basis`.
- `landing_url`: primary human-facing page that should be monitored.
- `attachment_url`: currently observed downloadable file, if one exists.
- `monitor_strategy`: how automation should poll and detect changes.
- `version_signal`: where the most useful version text is currently found.
- `current_observation`: facts verified manually on the recorded date.

## Monitoring rule of thumb

When a landing page and an attachment disagree, trust neither blindly.
Store both signals and send the source to review.
