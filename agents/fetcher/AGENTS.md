---
id: fetcher
kind: worker
title: Fetcher
surface: opencode_transport
transport_role: explore
opencode_agent: build
mode: propose_patches
model_policy: retrieval_ops
persona: persona.yaml
composes:
- memory
- fetcher
- brave-search
- ingest-website
- debug-fetcher
- task-monitor
- scillm
consult_personas: []
icon: download
---

# Fetcher

Transport wrapper for the `fetcher` subagent.

See `persona.yaml` for the authoritative role, state, helper, model-policy, and output contract.
