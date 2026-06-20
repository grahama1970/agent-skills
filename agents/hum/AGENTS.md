---
id: hum
kind: worker
title: Hum
surface: opencode_transport
transport_role: media
opencode_agent: build
mode: workspace_write
model_policy: research_reasoning
persona: persona.yaml
composes:
- memory
- hum
- brave-search
- ingest-youtube
- create-stems
- surf
- project-knowledge
- task-monitor
- best-practices-subagent
consult_personas:
- embry
icon: audio-lines
---

# Hum

Transport wrapper for the `hum` subagent.

This worker owns bounded persona humming source discovery, guide preparation,
ElevenLabs STS bakeoff execution, review-page generation, and status receipts.
It does not own final human listening approval or cache publication.

See `persona.yaml` for the authoritative role, state, tool, status, and output
contract.
