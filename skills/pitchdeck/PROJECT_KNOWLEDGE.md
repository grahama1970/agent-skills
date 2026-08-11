# Project Knowledge: agent-skills

**Last updated:** 2026-08-10 10:24 by agent
**Status:** Active development

## Current Understanding

- Project initialized, knowledge tracking started

## Recent Decisions

| Date | Decision | Why |
|------|----------|-----|
| 2026-08-07 | Initialize project knowledge | Enable shared human/agent context |
| 2026-08-07 | Voice layer = bounded proposal compiler (model proposes style, transform verifier proves meaning, human approves exact strings); filed as #1311-#1316; contract at /mnt/storage12tb/skills/pitchdeck/outputs/webgpt-voice-layer-contract-2026-08-07.md | Agent blind rating failed decisively (generated median 2 vs exemplar 5); corpus encodes the voice rules but the candidate pool never used them; webgpt consult + style-transfer literature (TinyStyler) support exemplar-conditioned proposal under fail-closed transform validation |
| 2026-08-10 | Ship PPTX as the only publication candidate; PDF and React are previews until each has delivered-artifact verification | The audit showed the browser-vs-LibreOffice check is an unimplemented strict xfail that I had been counting inside 'all gates green', and PDF/React have no target-specific proof. One verified target beats three advertised ones. |

## Open Questions

- [ ] What are the key architectural decisions?
- [ ] What are the known issues?
- [ ] What attribution/identity strip is factually valid for Sparta Explorer product decks (ES-Group/sponsor strips from conference decks are not)?
- [ ] Is the React deck a publication-equivalent output or only a review surface? This scopes whether verify-publish needs an HTML/React arm (#1329).

## Key Files

| File | Purpose |
|------|---------|
| PROJECT_KNOWLEDGE.md | Shared project knowledge |

## Infrastructure State

<!-- Auto-populated from /project-state --quick -->

## Current State

- 2026-08-07: README->deck pipeline complete and defect-free: five human-approved renderings, materializer, house chrome, native PPTX + HTML emitters, all gates green (design-lint PASS, render-oracle in envelope, 61 tests). webgpt visual review: two fix cycles -> READY. Agent blind rating (3 fresh-context judges, 4 labeled references, 12 unlabeled items): generated median 2 vs exemplar 5 — gate (median>=4) FAIL, judges discriminated 12/12. Tells: no valid identity/footer strip; uniform circled icons vs hand-drawn multi-element line-art; sparse full-sentence headers vs dense witty chevrons; mechanical symmetry. Density/asymmetry/dotted-meander pass applied; chevrons drop-not-clip. Remaining gap: candidate rendering pool has no short voice-matched assertions — corpus encodes the voice (headline-as-assertion, humor, density-5x5) but propose-renderings has not been driven from it.
- 2026-08-10: P0 CLOSED (#1328) — every emitted string, diagram node/edge labels included, carries its own binding; verify-publish consumes compiler-emitted AssertionAtoms from the approved document rather than a hand-maintained approvals list. Proven both ways: with ALL diagram text stripped from approvals, verify-publish PASSES (36 strings, 0 findings); retyping an edge label to 'relevance always establishes support' is REFUSED. Adversarial state audit (webgpt, outputs/state-review-2026-08-08.md) returned NOT_READY and reclassified all 9 of my WORKING claims; its corrections are now recorded in SKILL.md: 'all gates green' was never true while a strict xfail exists; PPTX is the only publication candidate with PDF/React as previews; house-conformance was validated on POSITIVE controls only; a corpus median is descriptive not normative; authorship is not a machine gate. Ticket board reduced 28 -> 5 open, all claim-integrity: #1329 single publishable target, #1330 VisualAssertion, #1331 asset registry, #1332 template contract + build manifest, #1333 conformance calibration. Deletions executed (#1335): anti-mechanical scene invariant demoted to advisory (symmetry can encode a truthful claim), layout retrieval marked research-only, unused primitives removed. Gates: 89 tests, sanity PASS, ui-contracts PASS, design-lint PASS, oracle within envelope, house-conformance 1 advisory finding.
