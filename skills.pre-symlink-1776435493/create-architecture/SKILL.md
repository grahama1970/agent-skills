---
name: create-architecture
description: >
  Create and update architecture diagrams programmatically in UX Lab's Architecture Editor.
  Agents define pipeline components, connections, and file attachments — the skill generates
  proper Excalidraw elements and saves via the Express API. Diagrams are visible at
  localhost:3002/#architecture and stored in ArangoDB for recall.
triggers:
  - create architecture
  - architecture diagram
  - draw pipeline
  - update architecture
  - add component to architecture
  - create pipeline diagram
allowed-tools:
  - Bash
  - Read
  - Write
  - Edit
provides:
  - architecture-diagram
  - pipeline-visualization
  - excalidraw-scene
composes:
  - ux-lab
  - memory
metadata:
  short-description: Programmatic architecture diagram creation for UX Lab Excalidraw canvas
taxonomy:
  - visualization
  - create
---

> STOP. READ THIS ENTIRE SKILL.MD BEFORE CALLING ANY ENDPOINT.

# create-architecture

Create architecture diagrams from pipeline definitions. Generates Excalidraw-compatible
elements with labeled shapes, connecting arrows, and file attachments.

## Usage

```bash
# Create from a YAML pipeline definition
./run.sh create --input pipeline.yaml

# Create from inline JSON
./run.sh create --name "QuerySpec Pipeline" --json '[{"id":"step1","label":"Classifier","tech":"SetFit"}]'

# Add a component to an existing architecture
./run.sh add-component --project queryspec-pipeline --label "New Step" --after recall

# List saved architectures
./run.sh list
```

## Pipeline YAML Format

```yaml
name: "QuerySpec Pipeline"
components:
  - id: omnibar
    label: Omnibar
    tech: "React input"
    latency: "0ms"
    color: purple        # purple|green|blue|amber|red
    files:
      - packages/ux-lab/src/components/binary-explorer/BinaryExplorerView.tsx

  - id: intent
    label: Intent Classifier
    tech: "SetFit 0.5B"
    latency: "<10ms"
    color: green
    files:
      - src/graph_memory/intent/_t05.py

connections:
  - from: omnibar
    to: intent
```

## How It Works

1. Parses pipeline definition (YAML or JSON)
2. Generates Excalidraw elements: rectangles with bound text labels, arrows with bindings
3. Lays out components vertically with consistent spacing
4. Saves via `PUT /api/architecture/:id` on the UX Lab Express server
5. Architecture appears at `localhost:3002/#architecture`

## Colors

| Name | Hex | Use |
|------|-----|-----|
| purple | #7c3aed | UI/frontend components |
| green | #00ff88 | Deterministic/verified steps |
| blue | #4a9eff | Search/retrieval steps |
| amber | #ffaa00 | LLM/model inference steps |
| red | #ff4444 | Error/warning states |
