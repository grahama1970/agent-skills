---
id: dreamer
kind: persona
title: Persona Dream Pipeline Orchestrator
surface: opencode_transport
transport_role: patch
opencode_agent: build
mode: workspace_write
model_policy: creative_orchestration
persona: persona.yaml
composes:
  - persona-dream
  - memory
  - project-knowledge
  - brave-search
  - scillm
  - loop
  - create-image
  - panel-reviewer
  - persona-dream-panel-repair-gate
  - best-practices-subagent
consult_personas:
  - script-writer
  - producer
  - panel-reviewer
icon: lightbulb
---

# Dreamer

Transport wrapper for the `dreamer` subagent.

See `persona.yaml` for the authoritative role, state, helper, model-policy,
orchestration, gate, retry, and output contract.
