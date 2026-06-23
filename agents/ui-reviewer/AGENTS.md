---
id: ui-reviewer
kind: worker
title: UI Reviewer
surface: opencode_transport
transport_role: reviewer
opencode_agent: explore
mode: read_only_review
model_policy: visual_review_reasoning
persona: persona.yaml
composes:
- memory
- test-interactions
- review-design
- best-practices-react
- best-practices-cots
- best-practices-subagent
- scillm
consult_personas: []
icon: monitor-check
---

# UI Reviewer

Transport wrapper for the `ui-reviewer` subagent.

See `persona.yaml` for the authoritative role, state, helper, model-policy, and output contract.
