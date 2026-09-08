# Explain Project

![Explain Project cockpit screenshot](assets/readme/cockpit-screenshot.png)

`explain-project` turns finished agent work into an interview cockpit: a strict explainer record drives the teleprompter, source range, debugger target, and Excalidraw diagram state from one typed revision.

We needed it during the OpenAI work-trial interview prep because the submission had too many proof surfaces for a normal slide deck: frozen runtime, privacy boundaries, source ranges, debugger proof, diagrams, and likely interviewer follow-ups. This skill would have put the answer, the exact source, the proof boundary, and the safe live controls on one 15-inch presenter surface instead of forcing a scramble across notes, VS Code, Excalidraw, and receipts.

> **Runtime boundary.** `SKILL.md` is the command contract. This README is the developer map. Live microphone transcription, visible VS Code control, and accepted Excalidraw board edits require their own receipts; replay fixtures do not prove those live effects.

![Question to cockpit flow](assets/readme/cockpit-flow.svg)

## Start here

| Need | Run or read |
| --- | --- |
| Validate explainer JSONL | `skills/explain-project/run.sh validate <explainers.jsonl>` |
| Ask a question against explainers | `skills/explain-project/run.sh ask <explainers.jsonl> --question "..."` |
| Run deterministic cockpit proof | `skills/explain-project/run.sh cockpit --repo fixtures/cockpit/project --explainers fixtures/cockpit/project/docs/explain/explainers.jsonl --headless --script fixtures/cockpit/scripts/worker-crash-walkthrough.json --out <proof.json>` |
| Serve the React cockpit API | `skills/explain-project/run.sh cockpit --explainers <explainers.jsonl>` |
| Build the browser cockpit | `cd skills/explain-project/ui && npm run build` |
| Emit `$test-interactions` manifest | `skills/explain-project/run.sh interaction-manifest --base-url http://127.0.0.1:8766` |

## Helper skills

| Skill | How `explain-project` uses it |
| --- | --- |
| [`best-practices-explain-project`](../best-practices-explain-project/SKILL.md) | Defines the explainer record and cockpit route: question -> cue -> source -> debugger -> diagram. |
| [`live-evidence`](../live-evidence/SKILL.md) | Supplies consented or replayed `live_evidence.question_candidate.v1` question candidates; the cockpit only ingests typed candidates. |
| [`debugger`](../debugger/SKILL.md) | Owns source reveal, breakpoint setup, and runtime proof receipts; the cockpit never auto-runs it from navigation. |
| [`ops-excalidraw`](../ops-excalidraw/SKILL.md) | Owns editable `.excalidraw` boards and proposal-safe board pushes. |
| [`create-svg`](../create-svg/SKILL.md) | Renders safe portable SVG diagrams from semantic scenes or ops-excalidraw output. |
| [`test-interactions`](../test-interactions/SKILL.md) | Replays stable `[data-qid]` controls against the cockpit through Surf. |
| [`surf`](../surf/SKILL.md) | Captures browser proof and screenshots of the real cockpit surface. |
| [`agentic-evals`](../agentic-evals/SKILL.md) | Retains the proof suite that prevents regression of cockpit contracts. |

## What lives where

| Path | Purpose |
| --- | --- |
| `immutable_goal.json` | Frozen cockpit goal and proof boundary. |
| `scripts/explain_project_core/models.py` | Strict Pydantic contracts for explainers, cockpit state, adapter receipts, Live Evidence intake, debugger proof, and Excalidraw proposal receipts. |
| `scripts/explain_project_core/reducer.py` | Single reducer that keeps teleprompter, source, debugger, diagram, and health projections revision-aligned. |
| `scripts/explain_project_core/server.py` | Loopback HTTP API for the React cockpit and Live Evidence intake seam. |
| `ui/src/` | React/Tailwind-oriented cockpit components with stable `data-qid` controls. |
| `fixtures/` | Retained agentic evals and cockpit contract checks. |

## Integration status

| Integration | Current contract | Proven by |
| --- | --- | --- |
| [`$ops-excalidraw`](../ops-excalidraw/SKILL.md) | Proposal-safe receipts only; no silent board replacement. | [`proofs/current-proof-summary.json`](proofs/current-proof-summary.json). |
| [`$debugger`](../debugger/SKILL.md) | Source reveal and runtime proof receipts are ingested only after debugger-owned proof validates. | [`proofs/current-proof-summary.json`](proofs/current-proof-summary.json). |
| [`$live-evidence`](../live-evidence/SKILL.md) | Accepts typed/replayed `live_evidence.question_candidate.v1` and suppresses duplicates. | [`proofs/current-proof-summary.json`](proofs/current-proof-summary.json). |
| React cockpit | 15-inch 1080p teleprompter layout, qid controls, keyboard navigation, native page/slider controls. | [`proofs/current-proof-summary.json`](proofs/current-proof-summary.json) and current Surf screenshot `assets/readme/cockpit-screenshot.png`. |

## Proof and non-claims

Verified in the latest local readback:

- `skills/explain-project/run.sh cockpit ... --headless ...` produced `explain_project.cockpit_proof.v1` with `status=PASS`.
- `skills/agentic-evals/run.sh run skills/explain-project/fixtures/agentic_eval.json` produced `agentic_evals.report.v2` with `readiness=READY`, `PASS=15`, `FAIL=0`, `BLOCKED=0`.
- [`proofs/current-proof-summary.json`](proofs/current-proof-summary.json) records the current receipt summary for README readers.

Not claimed:

- independent WebGPT final acceptance of this exact committed state unless the current review receipt is cited separately;
- real microphone transcription into Live Evidence;
- human acceptance of an Excalidraw proposal in the browser;
- arbitrary visible VS Code GUI control;
- arbitrary debugger adapter support beyond the validated debugger proof contract.
