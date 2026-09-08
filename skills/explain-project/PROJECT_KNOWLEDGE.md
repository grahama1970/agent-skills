# Project Knowledge: explain-project

**Last updated:** 2026-09-08 by agent
**Status:** Active development; cockpit immutable goal locally complete with proof-bound live-integration gaps.

## Current Understanding

- `explain-project` is a reusable interview cockpit for explaining agent-built work through strict `project.feature_explainer.v1` records.
- The cockpit source of truth is one `explain_project.cockpit_state.v1` reducer revision that projects teleprompter, source, debugger, diagram, integration health, and adapter receipts.
- The immutable goal is `explain-project-interview-cockpit-v1`, hash `sha256:ffcc1465f1e222c3043e3730a5113de05b898aa5f398dbb5f87d3f9cb0b9c00d`.
- Latest deterministic proof: `/tmp/explain-project-primary-cockpit-proof.json` has `status=PASS`; `/tmp/explain-project-primary-agentic-eval.json` has `readiness=READY`, `PASS=15`, `FAIL=0`, `BLOCKED=0`.
- `$ops-excalidraw` integration is proposal-safe: owning receipt `/tmp/explain-project-excalidraw-proof/ops-proposal-receipt.json` is `ops_excalidraw.push_board.v1`, `status=PASS`, `mode=proposal`.
- `$debugger` integration ingests source reveal and runtime proof receipts; proof files are `/tmp/explain-project-live-debugger-source-reveal-receipt.json` and `/tmp/explain-project-live-debugger-runtime-proof-receipt.json`.
- `$live-evidence` integration is typed intake/deduplication only unless a consented listener receipt exists. Live microphone transcription is not part of the current cockpit completion claim.
- README now links helper skill contracts (`live-evidence`, `debugger`, `ops-excalidraw`, `create-svg`, `test-interactions`, `surf`, `agentic-evals`) and includes `assets/readme/cockpit-screenshot.png` plus `assets/readme/cockpit-flow.svg`.

## Recent Decisions

| Date | Decision | Why |
| --- | --- | --- |
| 2026-09-08 | Treat WebGPT implementation output as historical help, not final verification. | Current search found WebGPT code/design output, not an independent post-implementation verdict that the immutable goal is met. |
| 2026-09-08 | Create skill-local `README.md`, `DESIGN.md`, and `PROJECT_KNOWLEDGE.md`. | The cockpit needs a developer map, a design contract, and a readable knowledge projection separate from `SKILL.md`. |
| 2026-09-08 | Add README screenshot and create-svg diagram assets. | A cold reader should see the cockpit and flow before reading command details. |
| 2026-09-08 | Keep Live Evidence live microphone proof out of the completion claim. | Current service status shows consent is false and listener is none; typed intake proof is valid but not audio proof. |

## Open Questions

- [ ] Should a fresh `$ask webgpt` review be run against the current committed implementation and proof packet to provide independent final verification?
- [ ] Should the next release require a consented Live Evidence microphone or dual-channel listener receipt?
- [ ] Should `SKILL.md` be updated to replace stale MVP wording with the current cockpit command set?

## Key Files

| File | Purpose |
| --- | --- |
| `README.md` | Developer-facing map and proof/non-claim summary. |
| `DESIGN.md` | Cockpit design premise, visual rules, and integration boundaries. |
| `SKILL.md` | Runtime skill contract. Currently contains stale MVP wording. |
| `immutable_goal.json` | Frozen goal and completion criteria. |
| `scripts/explain_project_core/models.py` | Strict Pydantic boundary models. |
| `scripts/explain_project_core/reducer.py` | Revisioned cockpit reducer. |
| `scripts/explain_project_core/server.py` | Loopback cockpit API and Live Evidence intake seam. |
| `ui/src/` | React cockpit implementation. |
| `fixtures/agentic_eval.json` | Retained proof suite. |

## Infrastructure State

- Repository: `/home/graham/workspace/experiments/agent-skills`
- Branch policy: work only on `main`; stage/commit/push only task-relevant paths.
- Current proof artifacts are local `/tmp` receipts; retain durable copies before relying on them across sessions.
