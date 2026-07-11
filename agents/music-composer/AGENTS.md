---
id: music-composer
kind: worker
title: Battle Music Director
surface: opencode_transport
transport_role: patch
opencode_agent: build
mode: propose_patches
model_policy: creative_reasoning
persona: persona.yaml
composes:
- memory
- battle
- best-practices-subagent
- create-midi
- scillm
consult_personas: []
icon: music
---

# Battle Music Director

Transport wrapper for the `music-composer` subagent.

See `persona.yaml` for the authoritative role, state, helper, model-policy, and output contract.
