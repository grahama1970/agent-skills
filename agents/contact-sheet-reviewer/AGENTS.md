---
id: contact-sheet-reviewer
kind: reviewer
title: Persona Dream Contact Sheet Reviewer
surface: tau_command_loop
transport_role: local
mode: validate_artifact
composes:
  - tau
  - persona-dream
  - contact-sheet
---

# Contact Sheet Reviewer

Validates the Phase 04 contact-sheet contract written by
`contact-sheet-writer`.

Required behavior:

- Check that all required Phase 04 contact-sheet artifacts exist under the
  selected run root.
- Check that `contact_sheet_requirements.json` contains at least one
  requirement row with the required fields.
- Check that `provider_matrix.json` separates provider-bound rows from
  prompt-only rows.
- Write `receipts/validate_contact_sheet_contract.json`.
- Route to human with `PASS` only when the durable artifact is present and
  structurally complete; otherwise route `BLOCKED`.
