# xsd_spec_pdf

Use this family for specification PDFs where the source is organized as element and attribute blocks rather than flat field tables.

## Signals

- Headings like `Elemento:`, `Atributos`, `Descripción`, `Uso`, `Tipo Base`, `Longitud`, `Patrón`
- Paths are implied by nested sections
- The PDF is mostly prose and section blocks, not dictionary tables

## Good fit

- Mexico CFDI Anexo 20 style specifications
- Similar tax authority PDFs that document XML nodes and attribute constraints

## Bad fit

- EN16931 / BT-BG field dictionaries
- API manuals dominated by request/response examples
- ZIP/XLSX bundles without a primary specification PDF

## Extraction mindset

- Segment blocks first
- Reconstruct hierarchy second
- Build normalized field records last
