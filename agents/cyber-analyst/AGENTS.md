---
id: cyber-analyst
kind: worker
title: Sparta Cyber Analyst
surface: opencode_transport
transport_role: reviewer
opencode_agent: build
mode: propose_patches
model_policy: cyber_reasoning
persona: persona.yaml
composes:
- memory
- best-practices-sparta
- review-sparta
- reality-check-sparta
- sparta-stress-test
- taxonomy
- match-requirement
- governance
- compliance-timeline
- monitor-sparta
- monitor-security
- best-practices-security
- scillm
consult_personas: []
icon: radar
---

# Sparta Cyber Analyst

Transport wrapper for the `cyber-analyst` subagent.

See `persona.yaml` for the authoritative role, state, helper, model-policy, and output contract.
