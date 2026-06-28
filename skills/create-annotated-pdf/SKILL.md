---
name: create-annotated-pdf
description: >
  Generate annotated PDFs from extraction pipeline run data. Overlays color-coded
  bounding boxes (text, tables, figures, equations) from S02/S05/S06 onto the
  original PDF. Supports single PDF, run directory, batch from blacklist, and
  interactive review server.
triggers:
  - annotate pdf
  - annotated pdf
  - show me the annotations
  - show extraction boxes
  - give me the annotated pdf
  - review extraction
  - spot check extraction
  - overlay bboxes
  - visualize extraction
  - create annotated pdf
  - review pdf annotations
  - review failed pdfs
  - batch annotate
metadata:
  short-description: "Annotated PDFs from extraction pipeline data"

provides:
  - create-annotated-pdf
composes: [task-monitor]
---

# create-annotated-pdf

Generate annotated PDFs showing what the extraction pipeline detected. Color-coded
bounding boxes for text blocks, tables, figures, equations overlaid on the original PDF.

## Quick Start

### Single PDF (from run directory)

```bash
cd /path/to/extractor
uv run python -m extractor.pipeline.tools.render_annotated_pdf from-run \
  --pdf /path/to/original.pdf \
  --run-dir /path/to/run_directory \
  --out /tmp/annotated.pdf \
  --export-pages --png-dpi 144
```

### Single PDF (by stem — auto-discovers run dir)

```bash
cd /path/to/agent-skills/skills/create-annotated-pdf
uv run --script annotate_from_stem.py <stem> [--out /tmp/annotated.pdf] [--png]
```

### Batch (all blacklisted/failed PDFs)

```bash
uv run --script annotate_from_stem.py --batch-blacklist [--out-dir /tmp/annotated_failures/]
```

### Interactive Review Server

```bash
# Terminal 1: API server
cd /path/to/extractor/prototypes/tabbed/api
uv run --script review_server.py

# Terminal 2: Frontend
cd /path/to/extractor/prototypes/tabbed/html
VITE_REVIEW_API=http://127.0.0.1:8003 npm run dev

# Open http://localhost:8080/review
```

## What Gets Annotated

| Stage | Element | Color | Source File |
|-------|---------|-------|-------------|
| S02 | Text blocks | Gray | `02_marker_blocks.json` |
| S02 | Section headers | Orange | `02_marker_blocks.json` |
| S02 | Equations | Purple | `02_marker_blocks.json` |
| S05 | Tables | Blue | `05_tables.json` |
| S06 | Figures | Green | `06_figures.json` |

## Outputs

- **Annotated PDF**: Original PDF with colored bbox rectangles and type labels
- **PNG pages**: Per-page raster images (optional, `--export-pages`)
- **Tabbed-compatible JSON**: Normalized (0-1) box coordinates for interactive editing
- **Corrections JSONL**: Human review corrections saved per-stem

## Run Directory Discovery

The skill searches these locations (NVMe first, then HDD):
1. `$PI_HOME/skills/review-pdf/extracted_runs_staging/`
2. `$ARTIFACT_STORAGE_ROOT/skills/review-pdf/extracted_runs/`

Run directories are named `{stem}_{hash10}` and contain stage outputs as subdirectories.

## Integration Points

- **`/learn-datalake`**: Blacklist provides failed PDF list for batch annotation
- **`/create-classifier`**: Corrections feed back as ground truth training labels
- **`/pdf-lab`**: Convergence loop can request annotated PDFs for diagnosis
- **`/review-pdf`**: Run directories are the primary data source
- **`/memory`**: Corrections can be stored as extraction quality signals

## Dependencies

- `pymupdf` (fitz) — PDF rendering and annotation
- `fastapi` + `uvicorn` — Review server (optional, for interactive mode)
- Tabbed prototype (`prototypes/tabbed/html`) — Interactive UI (optional)
