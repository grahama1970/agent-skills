---
id: doc-qra
kind: worker
title: Doc QRA
surface: opencode_transport
transport_role: reviewer
opencode_agent: build
mode: propose_patches
model_policy: extraction_reasoning
persona: persona.yaml
composes:
- memory
- doc2qra
- taxonomy
- prompt-lab
- scillm
consult_personas: []
icon: messages-square
---

# Doc QRA

Transport wrapper for the `doc-qra` subagent.

See `persona.yaml` for the authoritative role, state, helper, model-policy, and output contract.
