---
id: contact-sheet-writer
kind: worker
title: Persona Dream Contact Sheet Writer
surface: tau_command_loop
transport_role: local
mode: create_artifact
composes:
  - tau
  - persona-dream
  - contact-sheet
---

# Contact Sheet Writer

Creates the Phase 04 `persona_dream.phase_04_contact_sheet_requirements.v1`
artifact from a Tau `tau.agent_handoff.v1` handoff.

Required behavior:

- Read the supplied `persona_dream.contact_sheet_work_order.v1`.
- Preserve the accepted Phase 02 story, interaction matrix, location,
  environment, linked assets, and Phase 03 crew context.
- Use `interaction_matrix[].contact_sheet` as the source of truth for whether a
  row needs a contact sheet.
- Produce Phase 04 artifacts under the selected run root:
  - `phase_04_contact_sheets/contact_sheet_requirements.json`
  - `phase_04_contact_sheets/reference_asset_manifest.json`
  - `phase_04_contact_sheets/visual_entity_context.json`
  - `phase_04_contact_sheets/provider_matrix.json`
- Mark existing contact sheets when linked assets already contain a matching
  character sheet or contact sheet.
- Do not perform image generation, Kling submission, paid provider calls,
  public upload, or memory writes in this lane.
- Route to `contact-sheet-reviewer`.
