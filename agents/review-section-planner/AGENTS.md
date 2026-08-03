---
id: review-section-planner
kind: worker
title: Review section planner
surface: opencode_transport
transport_role: reviewer
opencode_agent: explore
mode: propose_patches
composes:
- dogpile
- memory
- scillm
- test-interactions
consult_personas: []
icon: clipboard-check
---

# Review section planner

Divides the surface into review sections with screenshot bundles, failure
intent, and per-section constraints so feedback stays section-scoped and
evidence-resolvable.
