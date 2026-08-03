---
id: extractor
kind: worker
title: Extractor
surface: opencode_transport
transport_role: reviewer
opencode_agent: build
mode: propose_patches
model_policy: extraction_reasoning
persona: persona.yaml
composes:
- memory
- extractor
- extract-pdf
- extract-tables
- extract-controls
- extract-entities
- extract-html
- debug-pdf
- pdf-lab
- extractor-quality-check
- scillm
consult_personas: []
icon: scan-text
---

# Extractor

Transport wrapper for the `extractor` subagent.

See `persona.yaml` for the authoritative role, state, helper, model-policy, and output contract.
