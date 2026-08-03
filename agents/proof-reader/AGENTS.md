---
id: proof-reader
kind: worker
title: Proof Reader
surface: opencode_transport
transport_role: reviewer
opencode_agent: build
mode: propose_patches
model_policy: language_review
persona: persona.yaml
composes:
- memory
- review-prompt
- review-readme
- review-question
- create-sentence-markup
- clean-text
- best-practices-prompt
- best-practices-report
- scillm
consult_personas: []
icon: spell-check
---

# Proof Reader

Transport wrapper for the `proof-reader` subagent.

See `persona.yaml` for the authoritative role, state, helper, model-policy, and output contract.
