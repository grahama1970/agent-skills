---
id: approach-owner
kind: worker
title: Approach Owner
surface: opencode_transport
transport_role: patch
opencode_agent: build
mode: workspace_write
model_policy: research_reasoning
persona: persona.yaml
composes:
- memory
- interview
- surf
- ask
- dogpile
- brave-search
- context7
- github-search
- project-knowledge
- project-state
- best-practices-subagent
- scillm
consult_personas: []
icon: route
---

# Approach Owner

Transport wrapper for the `approach-owner` subagent.

See `persona.yaml` for the authoritative role, state, helper, model-policy, and output contract.
