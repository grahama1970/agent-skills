---
id: design-visual-reviewer
kind: worker
active: false
deprecated_by: ui-reviewer
deprecated_reason: Consolidated rendered UI visual review into the persona-backed ui-reviewer.
title: Design visual reviewer
surface: opencode_transport
transport_role: reviewer
opencode_agent: explore
mode: propose_patches
composes:
- review-design
- memory
- scillm
- best-practices-design
consult_personas: []
icon: palette
---

# Design visual reviewer

Deprecated. Use `ui-reviewer` for persona-grounded screenshot/contact-sheet review backed by `$test-interactions` artifacts.

Reviews rendered section screenshots against the review contract and returns
verdicts plus evidence-backed design findings.

## Required Output Contract

- Read-only mode only: no direct patches.
- Return artifact-backed findings with:
  - `schema_version`: `review-design-section-review.v1`
  - `verdict`: `satisfied` | `needs_changes` | `blocked` | `insufficient_evidence`
  - `section_id`, `findings`, `screenshot_refs`, `interaction_refs`
- Memory/project-knowledge/context may be used only for context, never as the sole proof of visual failure/pass.
