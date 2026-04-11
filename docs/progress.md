# Progress

- current target PDF: `artifacts/germany-smoke/de-xrechnung-3.0.1.pdf`
- chosen extractor: `de-xrechnung-3-0-x`
- last gate result: `pass` via `python scripts/harness/quality_gate.py --pack-dir .opencode/skills/tax-law-parser/packs/tax-pack-de-xrechnung --pdf artifacts/germany-smoke/de-xrechnung-3.0.2.pdf --extractor de-xrechnung-3-0-x --outdir artifacts/germany-smoke/gate-de-pack-302`
- known bad fields: no blocking extraction defects in the smoke sample; `BT-24`, `BT-82`, `BT-83`, `BT-146`, and `BT-150` now parse with the expected `data_type` and `cardinality`.
- next smallest change: decide whether to promote a trusted baseline for `tax-pack-de-xrechnung`, because parser, gate, auto-match, and source monitor now all pass without a pack-specific baseline.
