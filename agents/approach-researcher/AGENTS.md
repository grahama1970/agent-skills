---
id: approach-researcher
kind: worker
title: Approach Researcher
surface: opencode_transport
transport_role: explore
opencode_agent: build
mode: propose_patches
model_policy: research_reasoning
persona: persona.yaml
composes:
- memory
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

# Approach Researcher

Transport wrapper for the `approach-researcher` subagent.

See `persona.yaml` for the authoritative role, state, helper, model-policy, and output contract.
