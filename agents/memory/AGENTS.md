---
id: memory
kind: worker
title: Project Memory
surface: opencode_transport
transport_role: explore
opencode_agent: build
mode: propose_patches
model_policy: memory_reasoning
persona: persona.yaml
composes:
- memory
- embedding
- vector-store
- taxonomy
- edge-verifier
- project-knowledge
- project-state
- monitor-memory
- task-monitor
- scillm
consult_personas: []
icon: database
---

# Project Memory

Transport wrapper for the `memory` subagent.

See `persona.yaml` for the authoritative role, state, helper, model-policy, and output contract.
