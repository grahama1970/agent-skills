---
id: panel-creator
kind: worker
title: Panel Creator
surface: opencode_transport
transport_role: patch
opencode_agent: build
mode: workspace_write
model_policy: creative_generation
persona_attached: false
persona: persona.yaml
composes:
  - create-image
  - scillm
  - loop
  - panel-reviewer
  - persona-dream
  - best-practices-subagent
  - best-practices-kling-scene
  - best-practices-kling-contact-sheet
  - memory
consult_personas: []
icon: image-plus
---

# Panel Creator

Transport wrapper for the `panel-creator` subagent.

See `persona.yaml` for the authoritative role, state, helper, model-policy,
tool-policy, retry, and output contract.
