---
id: researcher
kind: worker
title: Researcher
surface: opencode_transport
transport_role: explore
opencode_agent: build
mode: propose_patches
model_policy: cheap_factual
persona: persona.yaml
composes:
- memory
- ask
- arxiv
- brave-search
- consume-youtube
- dogpile
- episodic-archiver
- embedding
- vector-store
- taxonomy
- project-knowledge
- project-state
- monitor-memory
- scillm
consult_personas: []
icon: search
---

# Researcher

Transport wrapper for the `researcher` subagent.

See `persona.yaml` for the authoritative role, state, helper, model-policy, and output contract.
