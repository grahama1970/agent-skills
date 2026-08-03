---
id: mathematics
kind: worker
title: Mathematics
surface: opencode_transport
transport_role: reviewer
opencode_agent: build
mode: propose_patches
model_policy: cheap_deterministic
persona: persona.yaml
composes:
- memory
- edge-verifier
- scillm
consult_personas: []
icon: calculator
---

# Mathematics

Transport wrapper for the `mathematics` subagent.

See `persona.yaml` for the authoritative role, state, helper, model-policy, and output contract.
