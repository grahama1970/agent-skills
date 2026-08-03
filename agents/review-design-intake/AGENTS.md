---
id: review-design-intake
kind: worker
title: Review-design intake
surface: opencode_transport
transport_role: reviewer
opencode_agent: explore
mode: propose_patches
composes:
- memory
- scillm
- project-knowledge
- best-practices-design
consult_personas: []
icon: compass
---

# Review-design intake

Normalizes `$review-design` scope, personas, acceptance criteria, non-goals,
risk statements, and fail-closed evidence gates before branching the review lane.
