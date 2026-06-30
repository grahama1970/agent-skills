---
name: extract-tables
description: >
  Composable PDF table extraction skill. Hybrid Rust+compiled-Python
  architecture replacing Camelot. Rust hotspots (image processing, geometry)
  via PyO3, compiled Python parsers (lattice, stream, network, hybrid),
  pdf_oxide for text extraction, polars for output. Shadow-LEGO self-correcting
  with strategy routing via /assistant classify. Agentic: builds and
  self-corrects its own extraction pipeline.
allowed-tools: Bash, Read, Write
triggers:
  - extract tables
  - table extraction
  - extract tables from pdf
  - pdf table extraction
  - read tables
  - get tables from
  - camelot extract
metadata:
  short-description: "Hybrid Rust+Python PDF table extraction (replaces Camelot)"
  project-path: ${HOME}/workspace/experiments/camelot

provides:
  - table-extraction
  - pdf-table-detection
  - table-metrics
  - table-export

composes:
  - assistant      # Shadow classifier: strategy routing (lattice/stream/network)
  - memory         # Learned extraction parameters per document domain
  - taxonomy       # Bridge tagging for cross-domain parameter transfer
  - task-monitor   # Progress tracking for batch extraction
  - table-lab      # Parameter tuning convergence loop
  - create-table-classifier  # MobileNetV2 strategy predictor (Tier 0.5)
  - extractor      # Pipeline consumer (s05 integration point)

taxonomy:
  - extraction
  - precision
  - ingestion
  - table-detection
---

> STOP. READ THIS ENTIRE SKILL.MD BEFORE CALLING ANY ENDPOINT.

# /extract-tables

Composable, self-correcting PDF table extraction. Replaces Camelot with a
hybrid Rust + compiled-Python architecture for 5-15x speed and 5-8x memory
improvement.

## Quick Start

```bash
# Extract tables from a PDF
./run.sh extract document.pdf --output tables.json

# Extract with specific strategy
./run.sh extract document.pdf --strategy lattice --line-scale 15

# Extract with auto-strategy (Shadow-LEGO routing)
./run.sh extract document.pdf --auto

# Batch extraction
./run.sh batch /path/to/pdfs/ --output-dir /path/to/results/

# Python API (drop-in replacement for camelot.io.read_pdf)
python -c "from extract_tables import read_pdf; tables = read_pdf('doc.pdf')"

# Health check
./sanity.sh
```

## Architecture

```
PDF input
    |
    v
[pdf_oxide] ---- Rust: text extraction + layout analysis (replaces pdfminer)
    |
    v
[Strategy Router] -- Shadow-LEGO 3-tier cascade:
    |                  T0:   Heuristic (line density, text gaps)
    |                  T0.5: /assistant classify(task="table-strategy")
    |                  T2:   /scillm teacher (novel layouts)
    v
[Parser] ----------- Compiled Python (mypyc):
    |                  - Lattice: calls Rust image_proc for OpenCV ops
    |                  - Stream: pure algorithm (text positioning)
    |                  - Network: alignment-based detection
    |                  - Hybrid: lattice + stream combination
    v
[Rust image_proc] -- PyO3 module (replaces OpenCV Python):
    |                  - adaptive_threshold
    |                  - morphological ops (erode, dilate)
    |                  - find_contours
    |                  - find_lines (Hough transform)
    v
[Table Construction] Compiled Python: cell assignment, spanning cells
    |
    v
[polars DataFrame] - Output (replaces pandas)
    |
    v
[Shadow Logger] ---- Self-correction: log quality, compare strategies
```

## Shadow-LEGO Strategy Routing

The strategy router follows the 3-tier cascade pattern:

| Tier | Component | Cost | Latency |
|------|-----------|------|---------|
| T0 | Heuristic: line density > 0.3 → lattice, else stream | Free | <1ms |
| T0.5 | `/assistant classify(task="table-strategy-router")` | Free | ~10ms |
| T1.5 | `/create-table-classifier` MobileNetV2 prediction | Free | ~50ms |
| T2 | `/scillm` teacher validation (novel layouts only) | Paid | ~2s |

Escalation stops at first confident tier (confidence >= 0.7).

## Self-Correction Loop

```
1. Extract tables with predicted strategy
2. Compute quality metrics (accuracy, whitespace, fragmentation)
3. If quality < threshold:
   a. Log disagreement to shadow.jsonl
   b. Try alternative strategy
   c. Compare results
   d. Learn: update /memory with winning parameters
4. Nightly: /table-lab tunes parameters from shadow logs
```

## Rust Crate (PyO3)

```
src/rust/
├── Cargo.toml
├── src/
│   ├── lib.rs          # PyO3 module entry
│   ├── image_proc.rs   # Threshold, morphology, contours
│   ├── geometry.rs     # Line merging, bbox math, scaling
│   └── pdf_bridge.rs   # pdf_oxide integration
```

Built with maturin. Exposes:
- `extract_tables.rust.adaptive_threshold(image_path) -> (img, threshold)`
- `extract_tables.rust.find_lines(threshold, direction, line_scale) -> lines`
- `extract_tables.rust.find_contours(vertical, horizontal) -> contours`
- `extract_tables.rust.find_joints(contours, vertical, horizontal) -> joints`
- `extract_tables.rust.merge_close_lines(lines, tolerance) -> merged`
- `extract_tables.rust.scale_coordinates(coords, scalers) -> scaled`

## Python API (drop-in Camelot replacement)

```python
from extract_tables import read_pdf

# Same interface as camelot.io.read_pdf
tables = read_pdf(
    "document.pdf",
    pages="1",
    flavor="lattice",      # or "stream", "network", "hybrid", "auto"
    line_scale=15,
    process_background=False,
)

# Each table has:
table = tables[0]
table.df           # polars DataFrame
table.accuracy     # float
table.whitespace   # float
table.page         # int
table.order        # int
table.bbox         # (x1, y1, x2, y2)

# Export
table.to_csv("output.csv")
table.to_json("output.json")
table.to_excel("output.xlsx")
tables.export("output.csv", f="csv", compress=True)
```

## Extractor Integration

The `/extractor` pipeline (s05_table_extractor.py) calls:

```python
# Before (Camelot):
from camelot import io as camelot_io
tables = camelot_io.read_pdf(str(pdf_path), pages=page_str, flavor=flavor, **params)

# After (extract-tables):
from extract_tables import read_pdf
tables = read_pdf(str(pdf_path), pages=page_str, flavor=flavor, **params)
```

## Dependencies

### Rust (compiled into PyO3 wheel)
- pdf_oxide — PDF text extraction + layout
- opencv-rust or imageproc — Image processing
- ndarray — Array operations
- pyo3 + maturin — Python bindings

### Python (compiled with mypyc)
- polars — DataFrame output
- click — CLI

### Docker (optional, for ghostscript/poppler backends)
- ghostscript — Alternative PDF rendering
- poppler-utils — pdftoppm rendering

## Metrics

| Metric | Description |
|--------|-------------|
| accuracy | % of text correctly placed in cells |
| whitespace | % of empty space in table |
| fragmentation | Score indicating over-split cells |
| strategy_confidence | Shadow-LEGO routing confidence |

## Files

```
~/.claude/skills/extract-tables/
├── SKILL.md              # This file
├── run.sh                # Entry point
├── sanity.sh             # Health check
├── src/
│   ├── rust/             # Rust crate (PyO3)
│   │   ├── Cargo.toml
│   │   └── src/
│   │       ├── lib.rs
│   │       ├── image_proc.rs
│   │       ├── geometry.rs
│   │       └── pdf_bridge.rs
│   └── python/
│       ├── __init__.py
│       ├── extract_tables.py  # Main API: read_pdf()
│       ├── strategy_router.py # Shadow-LEGO strategy selection
│       ├── table.py           # Table/Cell data structures
│       ├── metrics.py         # Accuracy, whitespace, fragmentation
│       ├── export.py          # CSV, JSON, Excel, HTML, Markdown
│       └── parsers/
│           ├── __init__.py
│           ├── base.py
│           ├── lattice.py
│           ├── stream.py
│           ├── network.py
│           └── hybrid.py
├── docker/
│   ├── Dockerfile.ghostscript
│   └── Dockerfile.poppler
├── shadow.jsonl           # Self-correction logs
├── tests/
│   ├── fixtures/          # PDF test files
│   └── test_extract.py
└── sanity/
    └── check_deps.sh
```
