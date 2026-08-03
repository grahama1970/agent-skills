---
id: interaction-manifest-author
kind: worker
title: Interaction manifest author
surface: opencode_transport
transport_role: reviewer
opencode_agent: explore
mode: propose_patches
composes:
- test-interactions
- memory
- scillm
- dogpile
consult_personas: []
icon: search-code
---

# Interaction manifest author

Builds deterministic `/test-interactions` manifests and coverage maps for
interactive review, including qid focus, interaction steps, and evidence paths.
