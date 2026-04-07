---
name: create-gsn-diagram
description: GSN (Goal Structuring Notation) diagrams from compliance graph
triggers:
  - "gsn diagram"
  - "gsn render"
  - "safety case diagram"
allowed-tools:
  - Bash
provides:
  - create-gsn-diagram
composes: [task-monitor]
---

# create-gsn-diagram

Generate Goal Structuring Notation (GSN) assurance case diagrams from the
SPARTA compliance graph stored in ArangoDB.  GSN is the standard notation
for structured safety and security arguments (ISO/IEC 15026, OMG SACM).

## Usage

Render a single control as an SVG assurance case:

```bash
./run.sh render --control AC-1
```

Render every control under a framework:

```bash
./run.sh render --framework NIST-800-171
```

Export raw DOT notation (pipe to `dot` yourself or inspect):

```bash
./run.sh export-dot --control AC-1
```

### Options

| Flag            | Description                                         |
|-----------------|-----------------------------------------------------|
| `--control`     | NIST/CMMC control ID (e.g. `AC-1`, `SC-7`)         |
| `--framework`   | Framework name; renders all controls under it        |
| `--output`      | Output file path (`.svg` default, `.png` supported) |
| `--dry-run`     | Generate sample GSN without querying ArangoDB        |

`--dry-run` with `export-dot` requires no external dependencies at all
(no ArangoDB, no graphviz system package).  `--dry-run` with `render`
requires the graphviz system package but not ArangoDB.

## Common Mistakes

### WRONG: Rendering without checking ArangoDB connectivity
```bash
./run.sh render --control AC-1  # fails silently if ArangoDB is down
```

### RIGHT: Use --dry-run to test, or verify ArangoDB first
```bash
./run.sh render --control AC-1 --dry-run  # works without ArangoDB
# Or verify: curl -s http://127.0.0.1:8529/_api/version
```

### WRONG: Rendering a full framework without output path
```bash
./run.sh render --framework NIST-800-171  # dumps many SVGs to current dir
```

### RIGHT: Specify output directory for batch renders
```bash
./run.sh render --framework NIST-800-171 --output ./gsn_diagrams/
```

### WRONG: Piping export-dot output without checking graphviz is installed
```bash
./run.sh export-dot --control AC-1 | dot -Tsvg > diagram.svg  # dot not found
```

### RIGHT: Check graphviz availability first
```bash
command -v dot >/dev/null || sudo apt install graphviz
./run.sh export-dot --control AC-1 | dot -Tsvg > diagram.svg
```
