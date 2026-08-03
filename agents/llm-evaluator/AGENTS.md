---
id: llm-evaluator
kind: reviewer
title: LLM Evaluator
surface: opencode_transport
transport_role: review
opencode_agent: build
mode: propose_patches
persona_attached: false
composes:
  - memory
  - scillm
  - best-practices-subagent
consult_personas: []
icon: chart-bar
---

# LLM Evaluator

Benchmark multiple models to select the best for fine-tuning.

See `persona.yaml` for the authoritative role contract.
