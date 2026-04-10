Generate a deterministic Python extractor module for a tax regulation PDF.

Hard requirements:

- Return Python code only.
- Do not use markdown fences.
- The module must start with `from __future__ import annotations`.
- The module must define:
  - `PROFILE_NAME = "<target_extractor_name>"`
  - `extract(pdf_path: Path) -> list[dict[str, object]]`
- The returned records must use the exact required keys provided in the payload.
- Keep parsing deterministic. Use Python logic and `pdfplumber`. Do not call an LLM from inside the extractor.
- The module may define helper functions.
- The module must compile.
- `field_id` must represent field identifiers, not business rule identifiers.
- If the source document contains rule codes such as `BR-*` or `HR-BR-*`, keep them in `rules` and do not emit them as `field_id`.

Implementation guidance:

- Prefer document-specific parsing over a fake generic parser.
- Use the supplied PDF summary, table previews, template module, and reference module to infer parsing strategy.
- If table-like structure is visible, parse rows from tables first, then enrich from surrounding text.
- If the PDF appears paragraph-driven, parse sections and headings deterministically.
- When a value is not found, return an empty string or empty list rather than inventing content.
- Populate `extractor_name` with `PROFILE_NAME`.
- `rules` must be a list of strings.
- `source_pages` must be a list of integers.
- Prefer `BT-*`, `BG-*`, `HR-BT-*`, or `HR-BG-*` style identifiers for field records when those are the document's field conventions.

Avoid:

- placeholder functions that always raise `NotImplementedError`
- free-form guesses with no parsing logic
- returning partial keys
- importing project modules that will not exist in another workspace unless the payload clearly indicates they are reusable
