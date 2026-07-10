---
id: video-distiller-reviewer
kind: reviewer
title: Video Distiller Reviewer
surface: opencode_transport
transport_role: review
opencode_agent: build
mode: workspace_read
model_policy: review
persona_attached: false
persona: persona.yaml
composes:
  - persona-dream
  - best-practices-subagent
  - best-practices-kling-scene
  - memory
consult_personas:
  - assurance
icon: scan-eye
---

# Video Distiller Reviewer

Transport wrapper for the `video-distiller-reviewer` subagent.

See `persona.yaml` for the authoritative read-only review contract.
