---
id: watch
kind: worker
title: Watch
surface: opencode_transport
transport_role: explore
opencode_agent: build
mode: propose_patches
model_policy: retrieval_ops
persona: persona.yaml
composes:
- memory
- brave-search
- watch
- ingest-youtube
- ingest-movie
- doc2qra
- scillm
- task-monitor
consult_personas: []
icon: eye
---

# Watch

Transport wrapper for the `watch` subagent.

See `persona.yaml` for the authoritative role, state, helper, model-policy, and output contract.
