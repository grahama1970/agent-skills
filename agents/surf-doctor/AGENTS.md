---
id: surf-doctor
kind: worker
title: Surf Doctor
surface: opencode_transport
transport_role: reviewer
opencode_agent: explore
mode: propose_patches
model_policy: maintainer_reasoning
persona: persona.yaml
composes:
- surf
- best-practices-subagent
- debugger
- test
- ticket
- scillm
consult_personas: []
icon: stethoscope
---

# Surf Doctor

Transport wrapper for the `surf-doctor` subagent.

See `persona.yaml` for the authoritative role, state, helper, model-policy, and output contract.
