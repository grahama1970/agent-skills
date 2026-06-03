# Plan ASCII

```text
Graph: debugger-proof-and-memory-improvements
Goal: Complete remaining debugger phases: redacted lesson distillation, advisory memory recall, docs/workflow updates, validation, and commit/push to agent-skills main.
Phase ledger: phase-02-safe-lesson-distillation [planned]

Legend: [DONE]=completed, [ACTIVE]=in progress, [PENDING]=not yet completed, [BLOCKED]=blocked, [MANUAL]=manual action required, [READY]=runtime-ready.
Sequential order is top to bottom. Nodes in the same lane are concurrent after prior lanes complete.

Lane 1 (concurrent):
  [PENDING] [READY] commit-and-push-main
       Publish accepted debugger updates to agent-skills main.
       next: compile or submit this runtime node after required fields are present
  [PENDING] [READY] phase-02-safe-lesson-distillation
       Validate redacted proof-to-lesson distillation.
       next: compile or submit this runtime node after required fields are present
  [PENDING] [READY] phase-03-memory-recall-integration
       Validate advisory-only memory recall normalization.
       next: compile or submit this runtime node after required fields are present
  [PENDING] [READY] phase-04-docs-workflow-update
       Validate debugger docs and full workflow checks.
       next: compile or submit this runtime node after required fields are present
```
