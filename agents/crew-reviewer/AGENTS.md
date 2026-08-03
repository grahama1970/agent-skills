---
id: crew-reviewer
kind: reviewer
title: Persona Dream Crew Reviewer
surface: tau_command_loop
transport_role: local
mode: validate_artifact
composes:
  - tau
  - persona-dream
---

# Crew Reviewer

Validates the Phase 03 crew contract written by `crew-writer`.

Required behavior:

- Check that Producer, Scriptwriter, and Director selections include persona IDs
  and display names.
- Check that each role has a rationale.
- Check that source story text, interaction matrix, location, environment,
  linked assets, and prompt payload receipt are present.
- Check that role-specific `$memory` recall evidence from `personas` and
  `persona_memory` is present for Producer, Scriptwriter, and Director.
- Write `receipts/validate_crew_contract.json`.
- Route to human with `PASS` only when the durable artifact is present and
  structurally complete; otherwise route `BLOCKED`.
