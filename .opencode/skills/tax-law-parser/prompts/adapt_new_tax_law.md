Use the `tax-law-parser` skill to adapt the parser to a new tax-law PDF format.

Required workflow:

1. Use the attached PDF directly. Do not ask the user for repository paths, virtualenv commands, or model configuration.
2. Inspect the new PDF and compare it to existing profiles in `.opencode/skills/tax-law-parser/profiles/`, especially the relevant family base and overlay modules.
3. If the PDF still belongs to an existing family, scaffold a new overlay with:
   `python .opencode/skills/tax-law-parser/scripts/bootstrap_extractor.py --family en16931_ubl --name <name> --description <desc> --jurisdiction <code> --tax-domain <domain> --language <lang> --filename-hint <hint> --text-hint <hint>`
4. If no existing family fits yet, scaffold a flat extractor with:
   `python .opencode/skills/tax-law-parser/scripts/bootstrap_extractor.py --name <name> --description <desc> --filename-hint <hint> --text-hint <hint>`
5. Implement or refine deterministic extraction directly in the overlay or extractor Python module.
6. Update `profiles/registry.json` or `extractors/registry.json` hints if needed.
7. Read the family references when needed:
   - `.opencode/skills/tax-law-parser/references/parser-families.md`
   - `.opencode/skills/tax-law-parser/references/families/en16931-ubl.md`
   - `.opencode/skills/tax-law-parser/references/overlays.md`
   - `.opencode/skills/tax-law-parser/references/repair-playbook.md`
8. Validate the changed code:
   - `python3 -m py_compile <changed_python_files>`
9. Run the parser or the combined test script:
   - `python .opencode/skills/tax-law-parser/scripts/run_tax_parser.py --pdf <pdf> --outdir <outdir> --extractor <name>`
   - or `python .opencode/skills/tax-law-parser/scripts/test_extractor.py --pdf <pdf> --extractor <name> --outdir <outdir>`
   - add `--baseline <baseline_json>` only when you need to override the default baseline under `baselines/`
10. If the extractor still fails badly, optionally run:
   - `python .opencode/skills/tax-law-parser/scripts/repair_extractor_brief.py --pdf <pdf> --extractor <name> --outdir <brief_outdir> --baseline <baseline_json>`
   Then read the generated brief, use `repair-playbook.md` to choose the edit scope, and edit the extractor Python directly.
11. Validate the output:
   - `python .opencode/skills/tax-law-parser/scripts/validate_tax_output.py --json <outdir>/field_catalog.json`
12. If a trusted baseline exists, compare against it:
   - `python .opencode/skills/tax-law-parser/scripts/compare_field_catalogs.py --baseline <baseline_json> --candidate <outdir>/field_catalog.json --outdir <diff_outdir>`
13. Report:
   - chosen extractor
   - output paths
   - record count
   - what remains manual or uncertain

Constraints:

- Do not replace a working overlay or extractor for another document family.
- Keep parsing logic deterministic and document-specific.
- Do not claim success without an actual run against the target PDF.
- Prefer editing Python directly over calling a secondary model-invoking helper.
- The repair brief is diagnostic only. It must not modify code or call a model.
