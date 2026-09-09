---
name: explain-project
description: >
  Generate and validate end-of-work feature explainers for technical interviews
  and developer transparency: strict JSONL records, teleprompter notes,
  source/debugger bindings, editable Excalidraw architecture boards, optional
  SVG previews, and question routing.
triggers:
  - explain project
  - walk me through this code
  - interview cockpit
  - explain what the agent built
  - architecture interview prep
provides:
  - feature-explainer-jsonl
  - interview-cockpit-input
  - post-agent-explainability
composes:
  - best-practices-explain-project
  - debugger
  - create-architecture
  - create-svg
  - ops-excalidraw
  - live-evidence
  - agentic-evals
runtime_self_improvement: basic
disciplines:
  - developer-tooling
  - human-collaboration
  - ui-design-engineering
---

# Explain Project

Create or validate a project-wide explainability package after substantial code
or skill work. This is for technical interviews and for developers who need to
understand what an agent changed.

Default output location: `docs/explain/explainers.jsonl` in the target project.
Each line is a strict Pydantic `project.feature_explainer.v1` record.

## Commands

```bash
skills/explain-project/run.sh validate docs/explain/explainers.jsonl
skills/explain-project/run.sh list docs/explain/explainers.jsonl
skills/explain-project/run.sh ask docs/explain/explainers.jsonl --question "What breaks first at scale?"
skills/explain-project/run.sh sample --output docs/explain/explainers.jsonl
skills/explain-project/run.sh eval-browser-sync --out-dir /tmp/explain-project-browser-sync
skills/explain-project/run.sh bridge --repo <workspace> --base-url http://127.0.0.1:15174 --out-dir <artifacts> --execute
skills/explain-project/run.sh eval-bridge-execution --out-dir /tmp/explain-project-bridge-eval
```

## Record contract

A record maps a question to what the cockpit should show:

```text
question -> teleprompter notes -> Excalidraw/SVG node -> VS Code range -> optional debugger stop
```

Use Excalidraw as the default editable architecture source. Use SVG as a rendered
portable artifact when stable or when `$create-svg` verification has produced a
safe self-contained diagram. Use `$debugger` only when live runtime state answers
the question.

## Browser synchronization

The React cockpit polls the existing bootstrap endpoint once per second after
loading (one in-flight request, five-second request deadline). External question
intake and catalog imports update the already-open page. Late responses cannot
replace a newer revision. On HTTP 409 the page refreshes state and shows that the
action was **not replayed**; the human must review the current step and retry.
Sync failures remain visible until a successful read. This is local polling,
not instantaneous streaming; API process restarts still require page reload.

`eval-browser-sync` starts disposable API/preview processes and an actual Chrome
tab through Surf. It retains API/DOM snapshots for replay intake, deduplication,
next/previous, a real stale-action 409, delayed response ordering, and external
catalog imports. It closes only its own tab/processes. No capture devices,
debugger execution, model providers, or whiteboard mutations are exercised.

## Adapter bridge

`bridge` fulfills the cockpit's explicit Reveal source / Prepare target intents
through the owning `$debugger` skill: it reads the loopback API, dispatches one
`$debugger request` (reveal or addBreakpoints) against the trusted workspace,
validates the extension-owned native status artifact against the selected
source range, and posts a revision-fenced `adapter.receipt` back. Dry-run is
the default; `--watch` requires `--execute`; a named VS Code launch requires a
separate one-shot `--run-breakpoint <config>` and a validated
`debugger.proof.v1` before `PROOF_RECEIVED`. Superseded intents are never
replayed (STALE/IDLE), failures post honest `BLOCKED` receipts, and cockpit
mutations require loopback host + loopback origin + `application/json`.
Imported explainer `runtime_launch` commands are never executed.

## Current scope

The current implementation validates/list/searches explainer JSONL, runs a
headless cockpit proof, serves a loopback cockpit API, and ships a React cockpit
harness under `ui/`. It ingests typed Live Evidence question candidates,
debugger source/proof receipts, and ops-excalidraw proposal receipts. It does not
claim live microphone transcription, arbitrary visible VS Code control, debugger
execution from navigation, or accepted Excalidraw board mutation without the
owning skill receipts.
