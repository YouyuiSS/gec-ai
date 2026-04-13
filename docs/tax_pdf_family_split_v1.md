# Tax PDF Family Split v1

## Purpose

This note narrows the current parser scope to the two PDF families that matter most for e-invoice onboarding:

1. `field_dictionary_pdf`
2. `xsd_spec_pdf`

The goal is to stop treating "PDF" as a single parser family. The country split is too unstable on its own; the document-shape split is what actually drives parser design.

## Why this split exists

Recent smoke tests showed that "new country" is not the right abstraction boundary:

- Germany XRechnung behaves like a field dictionary PDF.
- Mexico CFDI Anexo 20 behaves like an XSD node-and-attribute specification PDF.
- These are both PDFs, but they are not parseable by the same row model.

Trying to force both into one generic PDF parser creates a brittle if/else family. The right move is to keep packs country-specific while keeping parser families document-shape-specific.

## Family 1: `field_dictionary_pdf`

### Typical shape

- Repeating field/group identifiers such as `BT-*` and `BG-*`
- Strong table layout
- Semantics appear as row-based dictionaries
- Cardinality and type are usually adjacent to the field row
- Notes may appear in continuation rows

### Current example

- Germany XRechnung 3.0.x PDF

### Current implementation anchor

- [en16931_ubl/base.py](/Users/xueyunsong/Documents/GitHub/gec-ai/.opencode/skills/tax-law-parser/tax_parser_runtime/families/en16931_ubl/base.py)

### Parser strategy

- Table extraction first
- Row classification
- Record merging across summary and detail tables

## Family 2: `xsd_spec_pdf`

### Typical shape

- Element-centric prose such as `Elemento: Receptor`
- Nested sections like `Atributos`, `Descripción`, `Uso`, `Tipo Base`, `Longitud`, `Patrón`
- Diagrams may exist, but the useful content is mostly paragraph/block text
- Identifiers are node names and attribute names, not `BT-*` style semantic terms
- Paths are usually implied by hierarchy rather than listed as explicit UBL paths on every row

### Current example

- Mexico CFDI Anexo 20 PDF

### Parser strategy

- Text extraction first
- Section segmentation by headings
- Element/attribute block grouping
- Hierarchy reconstruction from heading sequence

## What should stay country-specific

Each jurisdiction should still own a thin pack:

- source registry
- profile registry
- overlay/config
- baseline
- fixtures

The family parser should only own the stable mechanics for that document shape.

## Practical rule

When onboarding a new PDF source, classify it in this order:

1. Is it row-oriented field dictionary PDF?
2. Is it node-and-attribute XSD specification PDF?
3. If neither, do not force it into a PDF family. Create or reuse a different source family.

## Immediate consequence for this repo

- Keep Germany on `field_dictionary_pdf` behavior through the current EN16931-like table family.
- Start Mexico on `xsd_spec_pdf`.
- Do not expand `en16931_ubl` to absorb XSD-style PDFs.
