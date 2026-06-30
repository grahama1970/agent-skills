---
name: data-audit
description: >
  Report on data completeness for the SPARTA QRA pipeline (Control -> URL -> Knowledge -> QRA).
  Queries DuckDB to show coverage percentages at each stage.
triggers:
  - audit sparta
  - check coverage
  - data completeness
  - pipeline status
metadata:
  short-description: SPARTA data completeness auditor.
  project-path: ${HOME}/workspace/experiments/pi-mono/.agent/skills/data-audit

provides:
  - data-audit
composes:
  - create-figure
  - task-monitor
---

# Data Audit

Audits the SPARTA pipeline data coverage.

## Usage

```bash
# Run full audit
.agent/skills/data-audit/run.sh

# Run for specific run ID (points to specific DB path if needed)
.agent/skills/data-audit/run.sh --run-id <run-id>
```

## Logic

Connects to SPARTA DuckDB and calculates coverage for:

1. **Controls**: Base set.
2. **URLs**: Controls mapped to at least one URL.
3. **Knowledge**: Controls mapped to URLs that have extracted chunks.
4. **QRA**: Controls that have generated QRA pairs.

## Visualization

After generating coverage data, offer to visualize via `/create-figure`:

```bash
# Pipeline coverage as stacked bar chart
create-figure metrics --input audit.json --output coverage.png --type bar --title "SPARTA Pipeline Coverage"

# Coverage heatmap by category
create-figure heatmap --input audit.json --output coverage-heatmap.png
```

**When to offer:** After presenting coverage percentages, ask: "Want me to chart the pipeline coverage?"

## Common Mistakes

### WRONG: Running audit without a DuckDB path when needed
```bash
./run.sh  # may fail if DuckDB path is not configured
```

### RIGHT: Specify run ID or verify default DB path
```bash
./run.sh --run-id <run-id>  # explicit run
```

### WRONG: Reporting raw counts without coverage percentages
```
Controls: 800, URLs: 500, QRAs: 200  # raw numbers are meaningless
```

### RIGHT: Report coverage ratios at each pipeline stage
```
Controls: 800 → URLs: 500 (62.5%) → Knowledge: 350 (43.8%) → QRA: 200 (25.0%)
```

### WRONG: Not visualizing results for stakeholder communication
```bash
./run.sh  # text output only, hard to share
```

### RIGHT: Generate charts via /create-figure after audit
```bash
./run.sh > audit.json
create-figure metrics --input audit.json --output coverage.png --type bar
```
