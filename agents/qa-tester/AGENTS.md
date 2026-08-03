---
id: qa-tester
kind: worker
title: QA Tester
surface: opencode_transport
transport_role: reviewer
opencode_agent: build
mode: propose_patches
model_policy: test_reasoning
persona: persona.yaml
composes:
- memory
- test
- test-interactions
- test-lab
- quality-audit
- fixture-tricky
- extractor-quality-check
- best-practices-react
- best-practices-cots
- surf
- scillm
consult_personas: []
icon: flask-conical
---

# QA Tester

Transport wrapper for the `qa-tester` subagent.

See `persona.yaml` for the authoritative role, state, helper, model-policy, and output contract.
