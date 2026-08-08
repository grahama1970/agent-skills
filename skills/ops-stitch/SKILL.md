---
name: ops-stitch
version: 0.1.0
description: >
  Bundle design context (screenshots, DESIGN.md, references, prompt) for Google Stitch sessions.
  Prepares a context-bundle directory with current-state screenshots, design tokens, reference images,
  and a structured prompt ready for upload to the Stitch web UI.
triggers:
  - bundle for stitch
  - stitch context
  - prepare stitch
  - design with stitch
  - ops-stitch
provides:
  - stitch-context-bundle
composes:
  - agentic-evals
runner: python
disciplines:
  - ui-design-engineering
  - developer-tooling
---

# ops-stitch

Bundle design context for Google Stitch sessions.

## What it does

Takes a target view/component name and produces a `context-bundle/` directory containing everything
needed for a Stitch design session:

1. **Screenshot** — headless Chrome captures the current state of the target URL
2. **DESIGN.md** — copied from the project (auto-detected in cwd or parent, or explicit path)
3. **Reference images** — any inspiration/reference images you want Stitch to see
4. **PROMPT.md** — the prompt text plus instructions for the human on what to upload
5. **manifest.json** — metadata (target, timestamp, URL, prompt, image list)

The output directory is ready for manual upload to the Stitch web UI. Stitch SDK is text-only,
but the web UI accepts image uploads — the human drags in the screenshots and references.

## Usage

```bash
# Bundle context for a component
./run.sh bundle \
  --target design-board-canvas \
  --url http://localhost:3001 \
  --hash music-lab-pipeline \
  --prompt "Redesign the pipeline view with better spacing and hierarchy" \
  --references /path/to/inspo1.png /path/to/inspo2.png

# List previous bundles
./run.sh list-bundles
```

## Output structure

```
captures/{target}/context-bundle/
  current-state.png    # headless Chrome screenshot
  DESIGN.md            # design tokens / spec
  PROMPT.md            # prompt + upload instructions
  manifest.json        # metadata
  ref-*.png            # reference images (renamed copies)
```
