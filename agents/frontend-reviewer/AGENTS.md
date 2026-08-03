---
id: frontend-reviewer
kind: worker
active: false
deprecated_by: ui-reviewer
deprecated_reason: Consolidated frontend visual and interaction evidence review into the persona-backed ui-reviewer.
title: Frontend reviewer
surface: opencode_transport
transport_role: reviewer
opencode_agent: explore
mode: propose_patches
composes:
- review-design
- test-interactions
- memory
- scillm
- best-practices-react
consult_personas: []
icon: palette
---

# Frontend reviewer

Deprecated. Use `ui-reviewer` for persona-grounded screenshot/contact-sheet review backed by `$test-interactions` artifacts.

UI-focused reviewer for interaction states, focus/keyboard behavior, and visual
coverage with `test-interactions` evidence backing.

## Required Output Contract

- Read-only mode only: must not emit workspace modifications.
- Verdict must reference screenshot or interaction artifact hashes (`screenshot_refs`, `interaction_refs`).
- Verdict must cite only findings backed by newly captured artifacts, not memory/context alone.
