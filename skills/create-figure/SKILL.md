---
name: create-figure
description: >
  Create publication-quality figures, charts, and diagrams.
  Multi-backend: Graphviz, Mermaid, NetworkX/D3, matplotlib, plotly, seaborn.
  50+ visualization types for any domain.
allowed-tools: Bash, Read
triggers:
  # General
  - create figure
  - create chart
  - create diagram
  - create plot
  - generate figure
  - make chart
  - publication figure
  - IEEE figure
  # Architecture & Code
  - architecture diagram
  - dependency graph
  - class diagram
  - UML diagram
  - module dependencies
  - workflow diagram
  - pipeline diagram
  # Metrics & Data
  - metrics visualization
  - bar chart
  - pie chart
  - line chart
  - heatmap
  - correlation matrix
  # Compliance & Assurance
  - gsn diagram
  - assurance case diagram
  - safety case diagram
  - goal structuring notation
  # Control Systems
  - bode plot
  - nyquist plot
  - root locus
  # ML/LLM
  - confusion matrix
  - ROC curve
  - training curves
  - scaling law
  - attention heatmap
  # Biology
  - violin plot
  - volcano plot
  - survival curve
metadata:
  short-description: "Create figures, charts, diagrams (50+ types)"

provides:
  - create-figure
composes:
  - extract-entities
  - memory
  - analytics
  - create-gsn-diagram
  - agentic-evals
disciplines:
  - content-creation
  - ui-design-engineering
---

# create-figure

Generate publication-quality figures from code analysis data for academic papers.

## Quick Start for Agents

**First gate: extract intent and data references.** Before choosing a rendering
backend, run `/extract-entities` on the user request. Treat its output as the
structured front door for:

- figure type and interface command mentions (`$create-figure`, D3, Graphviz, chart, table)
- controls, taxonomy tags, project/domain terms, and unresolved terms
- dataset/source references, file-like paths, Hugging Face dataset names, and prompt-supplied data cues

Then resolve data in this order:

1. Prompt-supplied data or attached artifacts.
2. Project files or run artifacts named by the user.
3. `/memory recall --q "<figure request>" --brief` for project context, prior examples, and provenance.
4. `/analytics describe <file>` for JSONL/JSON/CSV or Hugging Face dataset exports.
5. Clarify if required data is still missing.

Do **not** silently invent chart data. Synthetic data is allowed only when the
user explicitly asks for `sample`, `demo`, `example`, `mock`, or `fictional`
data. Otherwise return a clarification request that names the exact missing
fields.

**Don't get overwhelmed by 50+ commands!** Use domain navigation:

```bash
# Step 1: Find your domain
create-figure domains

# Step 2: List commands for your domain
create-figure list --domain ml        # ML/LLM projects
create-figure list --domain control   # Aerospace/control systems
create-figure list --domain bio       # Bioinformatics

# Step 3: Or get recommendations by data type
create-figure recommend --data-type classification
create-figure recommend --data-type time_series
create-figure recommend --show-types  # See all data types
```

### Domain Quick Reference

| Domain | Use For | Key Commands |
|--------|---------|--------------|
| **core** | Any project | `metrics`, `workflow`, `architecture`, `deps` |
| **ml** | ML/LLM evaluation | `confusion-matrix`, `roc-curve`, `training-curves`, `scaling-law` |
| **control** | Aerospace, control systems | `bode`, `nyquist`, `rootlocus`, `state-space` |
| **field** | Nuclear, thermal, physics | `contour`, `vector-field`, `heatmap` |
| **project** | Scheduling, requirements | `gantt`, `pert`, `radar`, `sankey` |
| **math** | Pure mathematics | `3d-surface`, `complex-plane`, `phase-portrait` |
| **bio** | Bioinformatics, medical | `violin`, `volcano`, `survival-curve`, `manhattan` |
| **hierarchy** | Breakdowns, fault trees | `treemap`, `sunburst`, `force-graph` |

---

## Architecture

Multi-backend design for maximum compatibility:

| Backend | Use Case | Output Formats |
|---------|----------|----------------|
| **Graphviz** | Deterministic layouts, CI-friendly | PDF, PNG, SVG, DOT |
| **Mermaid** | Quick documentation, GitHub-compatible | PDF, PNG, SVG, MMD |
| **NetworkX** | Graph manipulation, D3 export | JSON, PDF, PNG |
| **matplotlib/seaborn** | Publication charts (IEEE settings) | PDF, PNG, SVG |
| **plotly** | Interactive Sankey, sunburst, treemap | PDF, PNG, HTML |
| **pydeps** | Python module dependencies | via Graphviz |
| **pyreverse** | UML class diagrams | via Graphviz |

## Data Resolution Contract

`/create-figure` behaves like `/create-evidence-case`: it can synthesize a
visual artifact from grounded inputs, but it must not fabricate the underlying
data. A renderable chart requires a resolved data source or explicit permission
to use sample data.

### Required flow

1. **Extract:** Run `/extract-entities` on the full user request to identify
   controls, terms, commands, figure type, dataset references, file references,
   and unresolved terms.
2. **Recall:** Query `/memory recall --brief` for project context and prior
   lessons. Memory may supply provenance, prior examples, or known dataset
   locations, but it does not authorize fabrication.
3. **Discover:** If a file or dataset is available, run `/analytics describe`
   before choosing the chart. For Hugging Face datasets, load using server-side
   `HF_TOKEN` from `.env`; never echo tokens to logs, artifacts, or prompts.
4. **Recommend:** Use analytics recommendations or `create-figure recommend`
   to select the chart type/backend.
5. **Render:** Generate durable artifacts (`.svg`, `.png`, `.pdf`, `.html`,
   `.json`, or `.d3.json`) and record the source path/dataset/config/split.
6. **Clarify:** If data is missing, ask for the minimum required structure.

### Clarification examples

For a D3 family tree, required data is:

```json
{
  "nodes": [{"id": "alice", "label": "Alice"}],
  "links": [{"source": "alice", "target": "bob", "relationship": "parent"}]
}
```

If the user asks “show me a D3 graph of a family tree” without nodes/links, ask
for people and relationships or ask whether sample data is acceptable. If the
user asks for “a sample family tree,” render immediately with synthetic sample
data and mark the artifact as sample-derived.

For dataset charts, required data is:

```json
{
  "source": "file path, artifact path, or Hugging Face dataset id",
  "split": "train/test/validation or explicit subset",
  "columns": "optional requested columns or target variables"
}
```

If the dataset is unknown or private access fails, clarify with the dataset id,
config, split, or file path needed.

## Common Commands

### `deps` - Dependency Graph

```bash
./run.sh deps --project /path/to/package --output deps.pdf
./run.sh deps -p ./src -o deps.svg --backend mermaid --depth 3
```

### `architecture` - Architecture Diagram

```bash
./run.sh architecture --project ./assess_output.json --output arch.pdf
```

### `metrics` - Metrics Chart

```bash
./run.sh metrics --input data.json --output metrics.pdf --type bar
./run.sh metrics -i data.json -o chart.pdf --type pie --title "Issue Distribution"
```

Chart types: `bar`, `hbar`, `pie`, `line`

### `workflow` - Workflow Diagram

```bash
./run.sh workflow --stages "Scope,Analysis,Search,Learn,Draft" --output workflow.pdf
```

### `confusion-matrix` - Confusion Matrix

```bash
./run.sh confusion-matrix --input results.json --output confusion.pdf --normalize
```

### `roc-curve` - ROC Curve

```bash
./run.sh roc-curve --input roc_data.json --output roc.pdf
```

### `bode` - Bode Plot

```bash
./run.sh bode --num 1,2 --den 1,3,2 --output bode.pdf
```

### `heatmap` - Heatmap

```bash
./run.sh heatmap --input matrix.json --output flux.pdf --cmap plasma
```

### `sankey` - Sankey Diagram

```bash
./run.sh sankey --input flows.json --output sankey.pdf
```

### `from-assess` - Generate All Figures

Generate all figures from /assess output in one command:

```bash
./run.sh from-assess --input assess_output.json --output-dir ./figures/
```

Generates:
- `architecture.pdf` - System architecture diagram
- `dependencies.pdf` - Module dependency graph
- `features.pdf` - Feature distribution chart
- `issues.pdf` - Issue severity pie chart

## Publication Quality Settings

matplotlib figures use IEEE publication settings:
- Font: 8pt Times New Roman (serif)
- DPI: 600 for saving, 300 for display
- Column widths: Single (3.5"), Double (7.16")
- TrueType fonts for Illustrator compatibility

## Dependencies

**Required:**
- Python 3.10+
- typer
- numpy

**Optional (enables features):**

| Package | Features Enabled |
|---------|------------------|
| matplotlib | All charts, plots, diagrams |
| seaborn | Heatmaps, publication styling |
| plotly | Sankey, sunburst, treemap, interactive |
| networkx | Force-directed graphs, PERT |
| scipy | Bode/Nyquist fallback, contours |
| control | Bode, Nyquist, root locus |
| graphviz | Dependency/architecture diagrams |

## Installation

```bash
# Core
pip install typer numpy matplotlib

# Full installation (all features)
pip install typer numpy matplotlib seaborn plotly networkx pandas squarify scipy control pydeps pylint

# System dependencies
apt install graphviz  # Debian/Ubuntu
npm install -g @mermaid-js/mermaid-cli
```

## Common Mistakes

```bash
# WRONG: Render a graph with invented real-world data
./run.sh force-graph --output family.d3.json
# → User did not provide people/relationships and did not request sample data
# RIGHT: Run extract-entities + memory recall, then clarify missing nodes/links

# WRONG: Skip analytics on unknown tabular data
./run.sh metrics --input hf_export.json --type bar
# → Unknown schema; likely wrong chart or wrong columns
# RIGHT: Run analytics describe first, then render the recommended chart

# WRONG: Use generic 'metrics' for ML evaluation data
./run.sh metrics --input results.json
# → Bar chart for data that needs a confusion matrix
# RIGHT: Run describe to get domain-specific recommendation
./run.sh describe results.json
# → "Detected: classification. Recommend: confusion-matrix, roc-curve"

# WRONG: Wrong backend for output format
./run.sh deps --project ./src --output deps.json
# → Graphviz can't write JSON; falls back to .dot silently
# RIGHT: Match backend to output format needs

# WRONG: 50+ commands — agent picks wrong one by guessing
# RIGHT: Always use domain navigation (describe) first, not guessing
```
