---
id: devops
kind: worker
title: DevOps
surface: opencode_transport
transport_role: debugger
opencode_agent: build
mode: workspace_write
model_policy: ops_reasoning
persona: persona.yaml
composes:
- memory
- ops-runpod
- ops-docker
- ops-workstation
- monitor-workstation
- ops-llm
- ops-chutes
- ops-huggingface
- service-status
- scillm
consult_personas: []
icon: server-cog
---

# DevOps

Transport wrapper for the `devops` subagent.

See `persona.yaml` for the authoritative role, state, helper, model-policy, and output contract.
