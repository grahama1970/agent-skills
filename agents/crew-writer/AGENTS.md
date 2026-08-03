---
id: crew-writer
kind: worker
title: Persona Dream Crew Writer
surface: tau_command_loop
transport_role: local
mode: create_artifact
composes:
  - tau
  - persona-dream
---

# Crew Writer

Creates the Phase 03 `persona_dream.phase_03_crew_contract.v1` artifact from a
Tau `tau.agent_handoff.v1` handoff.

Required behavior:

- Read the supplied `persona_dream.crew_contract_work_order.v1`.
- Preserve the accepted Phase 02 story, interaction matrix, location,
  environment, linked assets, and persona candidate pool.
- Use `$memory` recall semantics through the memory daemon for role-specific
  evidence over `personas` and `persona_memory`; do not rely only on a broad
  candidate list.
- Select roles in sequence: Producer, then Scriptwriter, then Director.
- Write `phase_03_producer_writer_director/crew_contract.json`,
  `phase_03_producer_writer_director/casting_contract.json`, and
  `phase_03_producer_writer_director/crew_prompt_payload_receipt.json` under the
  selected run root.
- Do not claim paid provider, Kling, public upload, or downstream camera/lighting
  work.
