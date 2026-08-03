---
id: fact-checker
kind: worker
title: Fact Checker
surface: opencode_transport
transport_role: reviewer
opencode_agent: build
mode: propose_patches
model_policy: evidence_reasoning
persona: persona.yaml
composes:
- memory
- project-knowledge
- dogpile
- brave-search
- taxonomy
- review-question
- scillm
consult_personas: []
icon: badge-check
---

# Fact Checker

Transport wrapper for the `fact-checker` subagent.

See `persona.yaml` for the authoritative role, state, helper, model-policy, and output contract.
