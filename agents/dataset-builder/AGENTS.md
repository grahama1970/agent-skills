---
id: dataset-builder
kind: worker
title: Dataset Builder
surface: opencode_transport
transport_role: patch
opencode_agent: build
mode: propose_patches
model_policy: extraction_reasoning
persona_attached: false
composes:
  - memory
  - fetcher
  - extractor
  - ingest-youtube
  - doc2qra
  - prompt-reviewer
  - prompt-lab
  - dataset-builder
  - brave-search
  - surf
consult_personas: []
icon: layers
---

# Dataset Builder

Transport wrapper for the `dataset-builder` subagent.

See `persona.yaml` for the authoritative role, state, helper, model-policy,
and output contract.
