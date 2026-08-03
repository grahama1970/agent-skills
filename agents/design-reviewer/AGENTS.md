---
id: design-reviewer
kind: worker
active: false
deprecated_by: ui-reviewer
deprecated_reason: Consolidated rendered UI, screenshot, and panel review into the persona-backed ui-reviewer.
title: Design reviewer
surface: opencode_transport
transport_role: reviewer
opencode_agent: explore
mode: propose_patches
composes:
- review-design
- memory
- scillm
- best-practices-design
- best-practices-react
consult_personas: []
icon: palette
---

# Design reviewer

Deprecated. Use `ui-reviewer` for persona-grounded screenshot/contact-sheet review backed by `$test-interactions` artifacts.

Reviews UI screenshots and design tokens. Composes ``/review-design``.
