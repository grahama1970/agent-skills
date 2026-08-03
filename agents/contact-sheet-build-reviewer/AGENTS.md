---
id: contact-sheet-build-reviewer
kind: reviewer
title: Persona Dream Contact Sheet Build Reviewer
surface: tau_command_loop
transport_role: local
mode: validate_artifact
composes:
  - tau
  - persona-dream
  - contact-sheet
  - memory
---

# Contact Sheet Build Reviewer

Validates the Phase 04 contact-sheet build evidence written by
`contact-sheet-builder`.

Required behavior:

- Check that `contact_sheet_build_receipt.json`,
  `contact_sheet_memory_recall_evidence.json`, and `blocked_assets.json` exist.
- Check every required contact-sheet row has either a real `existing_assets`
  entry or an exact blocked asset record naming the missing requirement.
- Write `receipts/validate_contact_sheet_build.json`.
- Route to human only after PASS or explicit BLOCKED evidence exists.

