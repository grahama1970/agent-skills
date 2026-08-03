---
id: coder
kind: worker
title: Coder
surface: opencode_transport
transport_role: patch
opencode_agent: build
mode: workspace_write
model_policy: code_reasoning
persona: persona.yaml
composes:
- memory
- code-runner
- create-code
- best-practices-python
- best-practices-react
- best-practices-rust
- prototype-react-iterate
- treesitter
- security-scan
- scillm
consult_personas: []
icon: code-2
---

# Coder

Transport wrapper for the `coder` subagent.

See `persona.yaml` for the authoritative role, state, helper, model-policy, and output contract.
