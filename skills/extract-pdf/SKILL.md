---
name: extract-pdf
description: >
  Self-improving PDF extraction engine. Rust-native via pdf_oxide.
  Replaces PyMuPDF (AGPL) with MIT-licensed extraction: text, blocks,
  sections, tables, figures, profiling, engineering detection. Shadow-LEGO
  cascade for automatic quality improvement via predict-extract-verify loop.
allowed-tools: Bash, Read, Write
triggers:
  - extract pdf
  - pdf extraction
  - process pdf
  - extract text from pdf
  - survey pdf
  - profile pdf
metadata:
  short-description: "Rust-native PDF extraction replacing PyMuPDF (MIT)"
  project-path: ${HOME}/workspace/experiments/pdf_oxide

provides:
  - pdf-extraction
  - pdf-text
  - pdf-tables
  - pdf-figures
  - pdf-profiling
  - pdf-sections
  - pdf-annotations

composes:
  - assistant       # Shadow classifier: extraction strategy, header validation
  - memory          # Learned extraction parameters per document domain
  - extract-tables  # Camelot delegation for complex table extraction
  - taxonomy        # Bridge tagging for cross-domain parameter transfer
  - task-monitor    # Progress tracking for batch extraction
  - pdf-lab         # Convergence loop: extract -> compare -> tune
  - analytics       # Prediction accuracy metrics across corpus
  - agentic-evals
taxonomy:
  - extraction
  - precision
  - ingestion
disciplines:
  - extraction
---

> STOP. READ THIS ENTIRE SKILL.MD BEFORE CALLING ANY ENDPOINT.

# /extract-pdf

Rust-native PDF extraction engine via pdf_oxide. MIT-licensed replacement for
PyMuPDF across the Embry OS pipeline.

## Quick Start

```bash
# Extract a single PDF (full pipeline: profile + blocks + sections + tables + figures)
./run.sh extract document.pdf

# Extract with JSON output to directory
./run.sh extract document.pdf --output-dir ./results/

# Survey a PDF (lightweight profiling — no full extraction)
./run.sh survey document.pdf

# Batch extraction
./run.sh batch /path/to/pdfs/ --output-dir ./results/

# Raw text extraction (fast, no pipeline)
./run.sh text document.pdf

# Health check
./sanity.sh
```

## Architecture

```
PDF input
    |
    v
[pdf_oxide PdfDocument] ---- Rust: parse, decrypt, text, spans, images
    |
    v
[survey_document()] -------- Python: page-by-page scan (tables, figures,
    |                         equations, columns, sections, TOC)
    |                         + Rust profile_document() enrichment
    v
[extract_document()] ------- Rust: full pipeline
    |   - profile_document()     domain, preset, complexity, is_scanned
    |   - classify_blocks()      header, body, equation, boilerplate, etc.
    |   - build_flat_sections()  section hierarchy from headers
    |   - predict_extraction()   cascade decision points
    v
[Post-extraction] ---------- Python: thin orchestrator
    |   - LLM calls (via /assistant, /scillm)
    |   - Camelot delegation (via /extract-tables)
    |   - Output assembly (JSON envelope)
    v
[Shadow Logger] ------------ Self-correction: log predictions vs outcomes
```

## Pipeline Output

Returns a JSON envelope consumed by `/extractor` or directly:

```json
{
  "version": "1.0",
  "engine": "pdf_oxide",
  "profile": { "domain": "...", "preset": "...", "complexity_score": 3, "is_scanned": false },
  "blocks": [{ "id": "...", "page": 0, "bbox": [...], "text": "...", "block_type": "header" }],
  "sections": [{ "title": "...", "level": 1, "page_start": 0, "page_end": 3 }],
  "tables": [{ "page": 5, "bbox": [...], "strategy": "lattice", "rows": [...] }],
  "figures": [{ "page": 2, "bbox": [...], "image_path": "..." }],
  "diagnostics": { "cascade_decisions": [...] }
}
```

## Shadow-LEGO Cascade

| Decision Point | Tier 0 (Heuristic) | Tier 0.5 (Classifier) | Tier 2 (LLM) |
|---|---|---|---|
| PDF profile/preset | filename + text regex | `preset_classifier` (sklearn) | DeepSeek domain classification |
| Header validation | font/size/numbering rules | `header-verdict` classifier | `/assistant` escalation |
| Extraction strategy | scanned→OCR, simple→native | `extraction-error-classifier` | DeepSeek strategy |
| Table strategy | line density routing | `table-strategy-selector` | -- |

## Commands

| Command | Description |
|---------|-------------|
| `./run.sh extract <pdf>` | Full extraction pipeline |
| `./run.sh survey <pdf>` | Lightweight page-by-page survey |
| `./run.sh text <pdf>` | Raw text extraction only |
| `./run.sh batch <dir>` | Batch extraction |
| `./run.sh profile <pdf>` | Document profiling only |
| `./run.sh shadow` | Show shadow correction log |
| `./run.sh status` | Health check |

## Key Files (in pdf_oxide project)

| File | Role |
|------|------|
| `src/document.rs` | Core extraction: extract_text, extract_spans, extract_document |
| `src/extractors/block_classifier.rs` | Block type classification + header validation |
| `src/extractors/section_hierarchy.rs` | Section tree builder |
| `src/extractors/document_extractor.rs` | Full pipeline: profile + classify + sections + predict |
| `src/python.rs` | PyO3 bindings |
| `python/pdf_oxide/survey.py` | Page-by-page survey (canonical profiler) |
| `python/pdf_oxide/pipeline.py` | Plugin-based pipeline orchestrator |

## Dependencies

- `pdf_oxide` (local wheel or editable install from `PDF_OXIDE_ROOT`)
- `loguru` for logging
- `typer` for CLI
- `httpx` for async HTTP (LLM calls)
