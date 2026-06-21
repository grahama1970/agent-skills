# SPARTA Chat interface brief

## User job

Let an operator ask for work in chat, see the real worker/run state, inspect artifacts
and evidence, understand failures, and explicitly approve durable actions.

## Required states

- empty/new conversation
- active worker run with a compact timeline
- completed run with changed files and validation receipts
- blocked run with failed phase, evidence, and next action
- artifact inspector open and closed
- approval control for commit/merge/push-like actions
- narrow/mobile inspector drawer

## Constraints

- Chat remains the command surface.
- Runs, evidence, traces, receipts, and artifacts are typed objects, not chat bubbles.
- Reuse existing React, Tailwind, shadcn, and D3 components before adding dependencies.
- No invented metrics, backend fields, or fake evidence.
- No dashboard-first layout, marketing hero, decorative charts, or copied product chrome.
- Keyboard focus, readable contrast, reduced motion, and responsive behavior are required.

## Bakeoff question

Which interface direction gives the clearest operator workflow with the least chrome,
while preserving auditability and implementation realism?
