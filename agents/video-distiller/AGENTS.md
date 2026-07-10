---
id: video-distiller
kind: worker
title: Video Distiller
surface: opencode_transport
transport_role: patch
opencode_agent: build
mode: workspace_write
model_policy: provider_distillation
persona_attached: false
persona: persona.yaml
composes:
  - persona-dream
  - best-practices-subagent
  - best-practices-kling-scene
  - best-practices-kling-contact-sheet
  - memory
consult_personas: []
icon: clapperboard
---

# Video Distiller

Transport wrapper for the `video-distiller` subagent.

See `persona.yaml` for the authoritative role, provider-best-practice input
contract, tool policy, retry policy, output contract, and proof tasks.
