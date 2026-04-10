Use the `tax-law-parser` skill to adapt the parser to a new tax-law PDF format.

Required workflow:

1. Use the attached PDF directly. Do not ask the user for repository paths, virtualenv commands, or model configuration.
2. Inspect the new PDF and compare it to existing extractors in `.opencode/skills/tax-law-parser/extractors/`.
3. If no existing extractor fits, scaffold a new extractor with:
   `python .opencode/skills/tax-law-parser/scripts/bootstrap_extractor.py --name <name> --description <desc> --filename-hint <hint> --text-hint <hint>`
4. Implement or refine deterministic extraction directly in the extractor Python module.
5. Update `extractors/registry.json` hints if needed.
6. Validate the changed code:
   - `python3 -m py_compile <changed_python_files>`
7. Run the parser or the combined test script:
   - `python .opencode/skills/tax-law-parser/scripts/run_tax_parser.py --pdf <pdf> --outdir <outdir> --extractor <name>`
   - or `python .opencode/skills/tax-law-parser/scripts/test_extractor.py --pdf <pdf> --extractor <name> --outdir <outdir> --baseline <baseline_json>`
8. If the extractor still fails badly, optionally run:
   - `python .opencode/skills/tax-law-parser/scripts/repair_extractor_brief.py --pdf <pdf> --extractor <name> --outdir <brief_outdir> --baseline <baseline_json>`
   Then read the generated brief and edit the extractor Python directly.
9. Validate the output:
   - `python .opencode/skills/tax-law-parser/scripts/validate_tax_output.py --json <outdir>/field_catalog.json`
10. If a trusted baseline exists, compare against it:
   - `python .opencode/skills/tax-law-parser/scripts/compare_field_catalogs.py --baseline <baseline_json> --candidate <outdir>/field_catalog.json --outdir <diff_outdir>`
11. Report:
   - chosen extractor
   - output paths
   - record count
   - what remains manual or uncertain

Constraints:

- Do not replace a working extractor for another document family.
- Keep parsing logic deterministic and document-specific.
- Do not claim success without an actual run against the target PDF.
- Prefer editing Python directly over calling a secondary model-invoking helper.
- The repair brief is diagnostic only. It must not modify code or call a model.
