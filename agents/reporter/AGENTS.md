---
id: reporter
kind: worker
title: Reporter
surface: opencode_transport
transport_role: reviewer
opencode_agent: build
mode: propose_patches
model_policy: report_reasoning
persona: persona.yaml
composes:
- memory
- ask
- create-report
- batch-report
- corpus-report
- best-practices-report
- create-text
- clean-text
- project-knowledge
- scillm
consult_personas: []
icon: file-text
---

# Reporter

Transport wrapper for the `reporter` subagent.

See `persona.yaml` for the authoritative role, state, helper, model-policy, and output contract.
