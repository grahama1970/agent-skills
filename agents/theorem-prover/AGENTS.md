---
id: theorem-prover
kind: worker
title: Theorem Prover
surface: opencode_transport
transport_role: reviewer
opencode_agent: build
mode: propose_patches
model_policy: formal_reasoning
persona: persona.yaml
composes:
- memory
- lean4-prove
- code-runner
- scillm
- edge-verifier
- embedding
- task-monitor
consult_personas: []
icon: square-function
---

# Theorem Prover

Transport wrapper for the `theorem-prover` subagent.

See `persona.yaml` for the authoritative role, state, helper, model-policy, and output contract.
