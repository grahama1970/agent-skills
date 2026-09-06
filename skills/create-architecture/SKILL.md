---
name: create-architecture
description: >
  Explain a module or codebase with source-grounded architecture diagrams.
  Read the implementation, choose the view that answers the question, then
  compose existing diagram skills. Use for system structure, dependencies,
  execution flow, lifecycle, and assurance explanations.
triggers:
  - create architecture
  - architecture diagram
  - explain this codebase
  - diagram this module
  - draw pipeline
allowed-tools: Bash, Read, Write, Edit
provides:
  - architecture-diagram
  - pipeline-visualization
  - excalidraw-scene
composes:
  - phart-dag-chart
  - create-svg
  - create-gsn-diagram
  - create-figure
  - ux-lab
  - ops-excalidraw
  - project-infographic
  - memory
  - agentic-evals
complies:
  - best-practices-skills
  - best-practices-python
runtime_self_improvement: basic
taxonomy: [visualization, create]
disciplines: [ui-design-engineering, content-creation]
metadata:
  short-description: Read source, choose the explanation, compose the diagram
---

# create-architecture

The human supplies a module/codebase and, optionally, a question or desired
surface. **The agent does the reading, selection, and diagram authoring.** Do
not make the human choose a renderer, write JSON, provide a creation brief, or
operate a multi-stage workflow for an ordinary architecture explanation.

## Default Workflow

1. Establish the actual checkout and scope. Use relevant memory as a hint,
   then examine live source. `./run.sh /path/to/module-or-repo` inventories
   candidate files and fingerprints; with no arguments it uses the caller's
   current directory. This is a starting aid, NOT semantic analysis.
2. Read entrypoints, interfaces, callers, dependencies, state, and failure
   paths relevant to the question. Narrow a truncated inventory; do not infer
   a system from filenames, imports alone, or README claims. Distinguish
   implemented behavior from proposed behavior and unknowns.
3. Choose the view first: structure, DAG, sequence, dataflow, lifecycle, or
   assurance. Choose the smallest view that answers the question; use multiple
   views only when one would hide important behavior. Cite files and lines for
   the important nodes, edges, and branches. Never invent sequential edges.
4. Choose a compatible surface below. Read the selected specialist's current
   `SKILL.md`, author its native input, and invoke its documented runtime.
   For executable routes, use the hub's `render` command to retain source and
   artifact hashes. The typed request is internal plumbing, not user homework.
5. Read back the artifact and compare its meaning with the source. Complete
   the specialist's visual and human-approval gates. Deliver the diagram link,
   a short explanation, source citations, and any uncertainty. For SVG bundles,
   link `preview.html` for fitted viewing and the SVG for reuse. Do not stop at
   an inventory, route receipt, plan, or unexecuted handoff.

Ask a question only when a real ambiguity changes the explanation. Otherwise
choose and briefly state a reasonable scope. Source reading is performed by
the invoking agent, not by a hidden classifier or an autonomous CLI model.

## Select The Specialist

| Need | Owner | Hub support |
| --- | --- | --- |
| Compact execution DAG in a terminal | `/phart-dag-chart` | Executable: `dag` + `terminal` |
| Static component/dependency structure | `/create-figure` | Executable: `structure` + `publication` |
| Polished vector/animated explanation fitting a native template | `/create-svg` | Executable: `svg`; bounded native templates only |
| Claims, arguments, evidence, and assurance | `/create-gsn-diagram` | Executable: `assurance` + `svg` or `publication` |
| Interactive inspection/editing in an application | `/ux-lab` owning React Flow components | Agent handoff; no generic CLI adapter |
| Editable whiteboard | `/ops-excalidraw` | Agent handoff; legacy commands remain available |
| Narrative or multi-view document | `/project-infographic` | Agent handoff; agent chooses appropriate notation |

Automatic defaults are publication for structure/assurance, terminal for DAG,
and document for sequence/dataflow/lifecycle. `auto` chooses a surface after
the agent chooses semantics; it does not interpret code. PHART cannot express
cycles. A sequence or state machine must not be flattened into a DAG. SVG is
a format, not a semantic notation: the current template must actually fit.
Read application-owned React Flow components before selecting one; do not
create another React Flow framework here. Archify integration is deferred.

```bash
./run.sh /path/to/module.py
./run.sh route --view dag --surface terminal
./run.sh render /path/to/agent-authored-request.json
./run.sh render /path/to/request.json --output-dir /mnt/storage12tb/skills/create-architecture/outputs/new-draft
```

See [request contract](references/hub-contract.md) for internal request fields,
renderer limits, and failure handling. `agent-handoff` requires the agent to
continue with the named skill; `render` deliberately refuses to fake execution.

## Safety And Evidence

- No backend service is needed for examination or routing. Rendering needs
  the selected skill and its documented prerequisites. SVG bundles also use
  `/create-svg preview` for a fitted local HTML view, not a new viewer.
- Hub renderings are immutable **DRAFT** bundles. Source hashes establish
  freshness, not semantic truth. Structural SVG checks are not visual proof.
- Never upload proprietary source to public services without authorization.
  Exclude secrets and build/dependency directories from source evidence.
- Preserve explicit execution locks and human mutation authorization. Drafts
  do not authorize executing a proposed system or publishing to UX Lab.
- `create`, `add-component`, and `list` remain available for existing callers;
  their full contract is in [legacy Excalidraw](references/legacy-excalidraw.md).
  Agents cannot author a human authorization gate on the human's behalf.
- Python environment and default outputs live under
  `/mnt/storage12tb/skills/create-architecture/`. No provider-local skill copies.

## Verification

`./sanity.sh` checks the real CLI and source inventory. `./sanity-live.sh`
exercises source-bound diagram generation through existing renderers and
adversarial failures. Run `/agentic-evals` with `fixtures/agentic_eval.json`
for multi-trial evidence. Read its report before claiming readiness; local
renderer checks do not establish source interpretation, full GSN evidence coverage,
React Flow integration, or visual/human acceptance.
