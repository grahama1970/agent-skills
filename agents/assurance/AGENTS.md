---
id: assurance
kind: worker
title: Assurance
surface: opencode_transport
transport_role: reviewer
opencode_agent: build
mode: propose_patches
model_policy: assurance_reasoning
persona: persona.yaml
composes:
- memory
- project-knowledge
- sparta-review
- qra-review
- sparta-qra-validator-gpt
- review-assurance-case
- create-evidence-case
- create-qras
- cmmc-assessor
- doc2qra
- taxonomy
- edge-verifier
- scillm
consult_personas: []
icon: shield-check
---

# Assurance

Transport wrapper for the `assurance` subagent.

See `persona.yaml` for the authoritative role, state, helper, model-policy, and output contract.
