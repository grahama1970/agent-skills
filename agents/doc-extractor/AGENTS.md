---
id: doc-extractor
kind: worker
title: Doc Extractor
surface: opencode_transport
transport_role: reviewer
opencode_agent: build
mode: propose_patches
model_policy: extraction_reasoning
persona: persona.yaml
composes:
- memory
- extractor
- clean-text
- extractor-quality-check
- ingest-youtube
- scillm
consult_personas: []
icon: file-scan
---

# Doc Extractor

Transport wrapper for the `doc-extractor` subagent.

See `persona.yaml` for the authoritative role, state, helper, model-policy, and output contract.
