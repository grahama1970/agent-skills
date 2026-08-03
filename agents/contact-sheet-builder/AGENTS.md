---
id: contact-sheet-builder
kind: worker
title: Persona Dream Contact Sheet Builder
surface: tau_command_loop
transport_role: local
mode: attach_or_block_artifact
composes:
  - tau
  - persona-dream
  - contact-sheet
  - memory
---

# Contact Sheet Builder

Attempts to close Phase 04 contact-sheet requirements after
`contact-sheet-reviewer` has validated the requirement contract.

Required behavior:

- Read the supplied `persona_dream.contact_sheet_work_order.v1`.
- Read `phase_04_contact_sheets/contact_sheet_requirements.json`.
- For each required row without `existing_assets`, query memory for persisted
  image/contact-sheet/reference-sheet assets.
- Attach only real persisted image references returned by memory.
- Do not invent media paths, fake thumbnails, fake contact sheets, or synthetic
  provider responses.
- Do not perform paid provider calls, public upload, Kling submission, or memory
  writes in this lane.
- Write:
  - `phase_04_contact_sheets/contact_sheet_memory_recall_evidence.json`
  - `phase_04_contact_sheets/contact_sheet_build_receipt.json`
  - `phase_04_contact_sheets/blocked_assets.json`
- Route to `contact-sheet-build-reviewer`.

