---
name: create-gsn-diagram
description: >
  GSN (Goal Structuring Notation) diagrams + OMG SACM 2.2 XML export from compliance graph.
  Supports taxonomy context mapping (Mind tags → SACM Context nodes), OSCAL evidence linking,
  and Lean4 proof references.
triggers:
  - "gsn diagram"
  - "gsn render"
  - "safety case diagram"
  - "sacm export"
  - "assurance case xml"
allowed-tools:
  - Bash
provides:
  - create-gsn-diagram
  - sacm-export
composes:
  - memory
  - task-monitor
  - taxonomy
  - export-oscal
  - lean4-prove
  - agentic-evals
disciplines:
  - compliance-security
  - content-creation
---

# create-gsn-diagram

Generate Goal Structuring Notation (GSN) assurance case diagrams from the
SPARTA compliance graph stored in ArangoDB. Supports three output formats:

| Format | Standard | Use Case |
|--------|----------|----------|
| **SVG/PNG** | Graphviz | Human-readable diagrams |
| **DOT** | Graphviz | Manual rendering, CI pipelines |
| **SACM XML** | OMG SACM 2.2 | Machine-readable, tool interoperability |

## Standards Alignment

| Standard | Status | Integration |
|----------|--------|-------------|
| **GSN** | De facto | Visual notation (boxes, circles, parallelograms) |
| **OMG SACM 2.2** | Approved (2024) | XML export via `export-sacm` |
| **ISO/IEC 15026** | Published (2019) | Assurance case concepts |
| **OSCAL** | NIST v1.1 | Evidence references in Solution nodes |
| **SPARTA Taxonomy** | Internal | Mind tags → SACM Context nodes |

## Usage

### Render GSN diagram (SVG/PNG)

```bash
./run.sh render --control AC-1
./run.sh render --framework NIST-800-171 --output ./diagrams/
```

### Export DOT notation

```bash
./run.sh export-dot --control AC-1
./run.sh export-dot --control AC-1 | dot -Tsvg > diagram.svg
```

### Export SACM XML (machine-readable)

```bash
# To stdout
./run.sh export-sacm --control AC-1 --dry-run

# To file
./run.sh export-sacm --control AC-1 --output ac1_assurance.xml

# Full framework
./run.sh export-sacm --framework SPARTA --output sparta_assurance.xml
```

## SACM Export Features

The `export-sacm` command produces OMG SACM 2.2 compliant XML with:

### Taxonomy → Context Mapping

SPARTA Mind tags (Detect, Evade, Exploit, Harden, Isolate, Model, Persist, Restore)
are mapped to SACM `InformationElement` (Context) nodes:

```xml
<arg:InformationElement gid="C2" name="C2: Tactical scope: Harden, Detect">
  <base:implementationConstraint content="taxonomy:mind=Harden,Detect"/>
</arg:InformationElement>
```

This enables:
- Filtering assurance cases by tactical category
- Validating tactical alignment across refinement chains
- Machine queries like "show all Harden arguments"

### OSCAL Evidence References

Solution nodes can reference OSCAL Assessment Result findings:

```xml
<arti:ArtifactReference gid="Sn1" name="Sn1: QRA evidence">
  <arti:externalReference location="oscal-ar://findings/ac1_qra" type="OSCAL-AR"/>
</arti:ArtifactReference>
```

### Lean4 Proof References

Solution nodes can reference formal proofs:

```xml
<arti:ArtifactReference gid="Sn2" name="Sn2: Formal proof">
  <arti:externalReference location="lean4://proofs/ac1_theorem" type="Lean4-Proof"/>
</arti:ArtifactReference>
```

## Options

| Flag            | Description                                         |
|-----------------|-----------------------------------------------------|
| `--control`     | NIST/CMMC/SPARTA control ID (e.g. `AC-1`, `SA-1`)  |
| `--framework`   | Framework name; processes all controls under it     |
| `--output`      | Output file path (format auto-detected by command)  |
| `--dry-run`     | Generate sample output without querying ArangoDB    |

## Integration Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│ /memory recall → control + QRA evidence + taxonomy                  │
│     ↓                                                               │
│ GSNGraph (internal model with taxonomy metadata)                    │
│     ├─→ graph_to_dot()  → SVG/PNG (human-readable)                 │
│     └─→ graph_to_sacm() → SACM XML (machine-readable)              │
│                              ↓                                      │
│                    /review-assurance-case (47 checks)              │
│                    /export-oscal (evidence export)                  │
│                    /lean4-prove (formal proofs)                     │
└─────────────────────────────────────────────────────────────────────┘
```

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

### WRONG: Using export-dot when you need machine-readable output
```bash
./run.sh export-dot --control AC-1 > assurance.txt  # not machine-parseable
```

### RIGHT: Use export-sacm for tool interoperability
```bash
./run.sh export-sacm --control AC-1 --output assurance.xml
```

### WRONG: Ignoring taxonomy context in assurance arguments
```bash
# Building an argument without tactical scope = weak argument
```

### RIGHT: Include taxonomy context (automatic with DB queries)
```bash
./run.sh export-sacm --control SA-1  # Mind tags auto-included as Context nodes
```
