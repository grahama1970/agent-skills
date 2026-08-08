# Project Knowledge: agent-skills

**Last updated:** 2026-08-07 20:41 by agent
**Status:** Active development

## Current Understanding

- Project initialized, knowledge tracking started

## Recent Decisions

| Date | Decision | Why |
|------|----------|-----|
| 2026-08-07 | Initialize project knowledge | Enable shared human/agent context |
| 2026-08-07 | Voice layer = bounded proposal compiler (model proposes style, transform verifier proves meaning, human approves exact strings); filed as #1311-#1316; contract at /mnt/storage12tb/skills/pitchdeck/outputs/webgpt-voice-layer-contract-2026-08-07.md | Agent blind rating failed decisively (generated median 2 vs exemplar 5); corpus encodes the voice rules but the candidate pool never used them; webgpt consult + style-transfer literature (TinyStyler) support exemplar-conditioned proposal under fail-closed transform validation |

## Open Questions

- [ ] What are the key architectural decisions?
- [ ] What are the known issues?
- [ ] What attribution/identity strip is factually valid for Sparta Explorer product decks (ES-Group/sponsor strips from conference decks are not)?

## Key Files

| File | Purpose |
|------|---------|
| PROJECT_KNOWLEDGE.md | Shared project knowledge |

## Infrastructure State

<!-- Auto-populated from /project-state --quick -->

## Current State

- 2026-08-07: README->deck pipeline complete and defect-free: five human-approved renderings, materializer, house chrome, native PPTX + HTML emitters, all gates green (design-lint PASS, render-oracle in envelope, 61 tests). webgpt visual review: two fix cycles -> READY. Agent blind rating (3 fresh-context judges, 4 labeled references, 12 unlabeled items): generated median 2 vs exemplar 5 — gate (median>=4) FAIL, judges discriminated 12/12. Tells: no valid identity/footer strip; uniform circled icons vs hand-drawn multi-element line-art; sparse full-sentence headers vs dense witty chevrons; mechanical symmetry. Density/asymmetry/dotted-meander pass applied; chevrons drop-not-clip. Remaining gap: candidate rendering pool has no short voice-matched assertions — corpus encodes the voice (headline-as-assertion, humor, density-5x5) but propose-renderings has not been driven from it.
