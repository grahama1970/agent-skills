---
id: designer
kind: worker
title: Designer
surface: opencode_transport
transport_role: reviewer
opencode_agent: build
mode: propose_patches
model_policy: design_reasoning
persona: persona.yaml
composes:
- memory
- create-design
- create-mockup
- create-react-designs
- create-styleguide
- best-practices-design
- best-practices-chat-ux
- create-figure
- best-practices-d3
- phart-dag-chart
- create-gsn-diagram
- figure-lab
- project-infographic
- create-annotated-pdf
- create-image
- create-icon
- create-storyboard
- scillm
consult_personas: []
icon: panels-top-left
---

# Designer

Transport wrapper for the `designer` subagent.

See `persona.yaml` for the authoritative role, state, helper, model-policy, and output contract.
