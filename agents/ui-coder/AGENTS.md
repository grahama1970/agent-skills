---
id: ui-coder
kind: worker
title: UI Coder
surface: opencode_transport
transport_role: patch
opencode_agent: build
mode: workspace_write
model_policy: code_reasoning
persona: persona.yaml
composes:
- memory
- code-runner
- test-interactions
- debugger
- brave-search
- github-search
- best-practices-react
- best-practices-d3
- best-practices-cots
- best-practices-design
- best-practices-chat-ux
- treesitter
- scillm
consult_personas: []
icon: panel-top
---

# UI Coder

Transport wrapper for the `ui-coder` subagent.

See `persona.yaml` for the authoritative role, tool policy, memory policy, retry policy, and output contract.
