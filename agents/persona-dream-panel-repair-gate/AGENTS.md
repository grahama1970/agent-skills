---
id: persona-dream-panel-repair-gate
kind: worker
title: Persona dream panel repair gate
surface: opencode_transport
transport_role: patch
opencode_agent: build
mode: workspace_write
persona_attached: false
persona: persona.yaml
composes:
  - persona-dream
  - best-practices-subagent
  - best-practices-script-writer
  - best-practices-self-improvement-loop
  - best-practices-kling-scene
  - best-practices-kling-contact-sheet
  - memory
  - create-image
  - scillm
  - loop
  - panel-creator
  - panel-reviewer
consult_personas: []
icon: scan-eye
---

# Persona Dream Panel Repair Gate

Transport wrapper for the `persona-dream-panel-repair-gate` subagent.

See `persona.yaml` for the authoritative role, tool policy, helper policy,
retry policy, output contract, and proof tasks.
