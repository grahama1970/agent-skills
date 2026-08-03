---
id: unsloth-studio
kind: monitor
title: Unsloth Studio Monitor
surface: opencode_transport
transport_role: debugger
opencode_agent: build
mode: workspace_write
model_policy: ops_reasoning
persona_attached: false
composes:
  - memory
  - unsloth-studio
  - ops-docker
  - ops-huggingface
  - scillm
  - brave-search
  - surf
  - loop
  - project-knowledge
consult_personas: []
icon: brain-circuit
---

# Unsloth Studio Monitor

Transport wrapper for the `unsloth-studio` subagent.

See `persona.yaml` for the authoritative role, state, helper, model-policy,
and output contract.
