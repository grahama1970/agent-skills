# extractor

![Extractor card](../../docs/assets/project-cards/extractor-workshop.webp)

Extractor turns messy documents into structured material agents can inspect,
route, and reuse. It profiles the input, chooses a preset, extracts sections,
tables, figures, requirements, and metadata, then exports the useful pieces as
JSON, Markdown, database records, or downstream QRA inputs.

Agents must treat [`SKILL.md`](SKILL.md) as the runtime contract. This README is
the quick human guide.

## Start Here

```bash
# Auto-detect format and document type
./run.sh paper.pdf

# Write outputs somewhere explicit
./run.sh paper.pdf --out ./results

# Fast first pass, no LLM
./run.sh paper.pdf --fast

# Full extraction lane with LLM/VLM help
./run.sh paper.pdf --accurate

# OCR scanned PDFs when needed
./run.sh scanned.pdf --auto-ocr
```

Use `--profile-only` when you want to see what extractor thinks the document is
before spending time or model budget on a full run.

## What It Handles

| Input | Notes |
|---|---|
| PDF | Main lane; delegates PDF work to the Rust-native `/extract-pdf` core |
| DOCX / PPTX / XLSX | Native office-document parsing where practical |
| HTML / XML / Markdown / RST / EPUB | Structured text extraction and parity checks |
| Images / scanned PDFs | OCR/VLM-assisted lanes when enabled |
| YouTube URLs | Transcript-oriented extraction through composed skills |

## What Comes Out

| Output | Why it matters |
|---|---|
| Sections | The document hierarchy agents can reason over |
| Tables | Extracted tabular evidence and strategy metadata |
| Figures | Images and optional descriptions |
| Requirements | SHALL/MUST/WILL-style mined claims for engineering docs |
| Markdown | Human-readable export |
| JSON / DuckDB / ArangoDB | Structured surfaces for tools, review, and memory |
| QRA pairs | Optional downstream recall material through `/doc2qra` |

## Preset-First Flow

Extractor works best when it can pick or receive a preset:

1. Profile the document layout and content.
2. Match a preset such as `arxiv`, `requirements_spec`, or `auto`.
3. Run the cheapest useful lane first.
4. Escalate to accurate mode only when the document deserves the cost.
5. Keep proof artifacts with the output so later agents can inspect what
   happened.

## Maintainer Notes

- Keep runtime rules in `SKILL.md`.
- Keep this README short, visual, and operator-friendly.
- Do not add large generated outputs to the skill directory.
- Prefer `sanity.sh` for local confidence before changing the contract.
