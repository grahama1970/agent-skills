---
id: design-interaction-reviewer
kind: worker
active: false
deprecated_by: ui-reviewer
deprecated_reason: Consolidated interaction-evidence review into the persona-backed ui-reviewer.
title: Design interaction reviewer
surface: opencode_transport
transport_role: reviewer
opencode_agent: explore
mode: propose_patches
composes:
- test-interactions
- memory
- scillm
- best-practices-react
consult_personas: []
icon: search-code
---

# Design interaction reviewer

Deprecated. Use `ui-reviewer` for persona-grounded screenshot/contact-sheet review backed by `$test-interactions` artifacts.

Checks keyboard/focus flows, nested scroll behavior, qid/path coverage, and
interaction evidence against the captured manifest and results.

## Required Output Contract

- Read-only mode only: no workspace writes.
- Return contract `review-design-interaction-review.v1` with:
  - `verdict`: `satisfied` | `needs_changes` | `blocked` | `insufficient_evidence`
  - `manifest_ref`, `interaction_refs`, `screenshot_refs`
  - `findings` with deterministic step/path identifiers
