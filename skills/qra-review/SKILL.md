---
name: qra-review
description: >
  Human-in-the-loop QRA assessment interface. Prodigy-style Textual TUI for
  reviewing WARN-grade QRA candidates from sparta_qra_candidates collection.
  Accept, reject, or amend candidates with Embry chat support, /slash skills,
  and PersonaPlex voice. Phase 1: Textual TUI. Phase 2: Embry-OS Tauri page.
triggers:
  - review QRAs
  - QRA assessment
  - QRA review
  - review candidates
  - human review QRA
metadata:
  short-description: Human-in-the-loop QRA review TUI
  version: "1.0.0"
provides:
  - qra-candidate-review
  - human-assessment-tui
requires:
  - memory
  - scillm
  - taxonomy
  - dogpile
  - create-figure
---

# /qra-review

Human-in-the-loop assessment interface for WARN-grade QRA candidates.

## Usage

```bash
# Launch TUI with all pending candidates
./run.sh

# Filter by framework
./run.sh --framework SPARTA --limit 50

# Batch mode (no TUI, auto-reject low-grounding)
./run.sh --mode batch --auto-reject-below 0.55
```

## Workflow

1. `assess_qra()` routes WARN-grade QRAs to `sparta_qra_candidates` collection
2. `/qra-review` TUI displays candidates one at a time
3. Human reviews with keyboard shortcuts:
   - **A** = Accept (promote to `sparta_qra`)
   - **R** = Reject (stays in staging)
   - **E** = Edit answer, re-assess, promote if PASS
   - **S** = Skip (next candidate)
   - **/** = Chat with Embry (context-aware)
   - **F5** = Bulk regex reject
   - **Q** = Quit

## Chat Commands

In the Embry chat panel:
- Free text: Ask Embry about the current QRA
- `/dogpile <query>`: Deep research with citations
- `/create-figure <control_id>`: Graph visualization
- `/memory recall <query>`: Graph memory search
- `/taxonomy extract <text>`: Extract taxonomy tags
