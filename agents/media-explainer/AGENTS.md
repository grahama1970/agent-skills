---
id: media-explainer
kind: worker
title: Media Explainer
surface: opencode_transport
transport_role: analyze
opencode_agent: build
mode: workspace_write
persona_attached: true
persona: persona.yaml
composes:
  - memory
  - best-practices-subagent
  - watch
  - scillm
  - ingest-youtube
  - ingest-movie
consult_personas: []
icon: file-search
---

# Media Explainer

Transport wrapper for the `media-explainer` subagent.

See `persona.yaml` for the authoritative role, tool policy, helper policy,
retry policy, output contract, and proof tasks.
