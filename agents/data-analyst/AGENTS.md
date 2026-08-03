---
id: data-analyst
kind: worker
title: Data Analyst
surface: opencode_transport
transport_role: reviewer
opencode_agent: build
mode: propose_patches
model_policy: data_reasoning
persona: persona.yaml
composes:
- memory
- analytics
- data-audit
- create-table
- batch-quality
- create-context
- edge-verifier
- scillm
consult_personas: []
icon: chart-column
---

# Data Analyst

Transport wrapper for the `data-analyst` subagent.

See `persona.yaml` for the authoritative role, state, helper, model-policy, and output contract.
