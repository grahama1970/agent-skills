# Pitch-deck bundle

This directory is the source-controlled handoff for a README-derived deck.

1. Edit `source_manifest.yaml` and point it at local README files.
2. Run `pitchdeck plan` into a generated subdirectory.
3. Review every candidate in `claim_ledger.yaml`.
4. Edit the deck manifest so each slide has one message, a source, and a visual plan.
5. Build, verify, render, inspect the contact sheet, then import the PPTX into Google Slides.

Do not commit large exports here. Store generated PPTX/PDF/PNG outputs on the configured
artifact volume and link the receipts from project documentation.
