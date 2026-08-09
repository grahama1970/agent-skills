# Handoff Report: grahama.co Bespoke-Design Compliance

**Timestamp**: 2026-08-09T16:45:52Z
**Active agent**: Codex
**Repository**: `/home/graham/workspace/experiments/agent-skills-font-integrate`
**Current commit inspected**: `70bbe47f054d0f0a354c5b72fd085460f12c930a`
**Immutable goal**: implement `best-practices-font`, compose it into grahama.co design workflows, then iterate grahama.co until `best-practices-bespoke-design` passes or a concrete blocker is reached.

## 1. Project Overview

- **Ecosystem**: Next.js static site under `site/`, skill tooling under `skills/monitor-website`.
- **Core purpose**: grahama.co presents Graham's agent-systems work through the selected Proof Workshop visual world: claim -> evidence -> bounded judgment.
- **Current source of truth**: this integration worktree, not the older dirty `/home/graham/workspace/experiments/agent-skills` checkout.

## 2. Current State

The full bespoke-design goal is **not achieved**. The deterministic site checks are strong, but the blind-distinctiveness gate remains unresolved.

Current deterministic evidence:

- `skills/monitor-website/run.sh design-world-check --json`
  - overall `status: NOT_TESTED`
  - `contract: PASS`
  - `provenance_source_lock: PASS`
  - `territory_separation: PASS`, `territory_count: 3`
  - `narrative_premise: PASS`, `selected_territory_id: T1`
  - `no_mono_on_human_labels: PASS`
  - `font_receipt: PASS`
  - `responsive_choreography: PASS`, `routes: 6`, `viewports: 5`, `checks: 30`, `failures: 0`
  - `craft_integrity_render: PASS`, `rendered_screens: 3`
  - `distinctiveness_blind: NOT_TESTED`, needs rendered screenshot corpus / blind-rater outputs
- `skills/monitor-website/run.sh design-world-check --json --distinctiveness-receipt skills/monitor-website/fixtures/design-world/distinctiveness/valid-distinctiveness-receipt.json`
  - fixture-only `distinctiveness_blind: PASS`
  - computed counts: `usable: 5`, `logo_off_correct: 5`, `generic_ai_template_primary: 0`, `competitor_swap_tension: 5`, `cross_screen_family: 5`
- `skills/monitor-website/run.sh design-world-check --json --distinctiveness-receipt skills/monitor-website/fixtures/design-world/distinctiveness/invalid-too-few-raters.json`
  - expected failure: `distinctiveness_blind: FAIL`
  - verifies too few raters, wrong logo-off match, missing classification/signals/invariants, generic-template vote, missing swap/family votes, and high leakage risk are rejected
- `skills/monitor-website/run.sh audit --no-live --json`
  - `ok: true`
  - `drift: []`
  - README/site stats: `skills: 346`, `sanity: 291`, `agents: 92`

Previously recorded deterministic checks in this worktree:

- `skills/monitor-website/run.sh visual-assets-check --json` -> `PASS`
- `skills/monitor-website/run.sh effects-check --json` -> `PASS`
- `skills/monitor-website/run.sh case-composition-check --json` -> `PASS`
- `skills/monitor-website/run.sh copy-audit --json` -> `PASS`
- `skills/monitor-website/sanity.sh` -> OK
- `cd site && python3 scripts/verify-data-qid.py` -> OK, 50 interactive elements checked
- `cd site && npm run verify:proof-pilot` -> OK
- `cd site && npm run verify:type-direction` -> OK
- `cd site && npm run build` -> passed
- `python3 scripts/check_mock_evidence_claims.py` -> OK

## 3. What Is Working

- `best-practices-font` exists and validates against `best-practices-skills`.
- The site has a selected visual world, territory selection, font receipt, craft-integrity receipt, visual asset registry, effects registry, and generated source surfaces.
- The major deterministic checks for provenance, territory separation, narrative premise, font role, responsive geometry, visual assets, effects, case compositions, copy, generated data, and build have usable local receipts.
- `design-world-check` now has a deterministic blind-rater receipt validator. It can accept a complete five-rater receipt and reject incomplete or contradictory normalized rater data. The production receipt is intentionally absent, so this does not establish G11.
- The rater prompt and contact sheet are stable:
  - `site/design-roundtable/distinctiveness-rater-prompt.r2.md`
  - prompt SHA-256: `0b77bd0f02f95581e040c8736dec872106688b057404ef85b0cdb7b744f33644`
  - `site/design-roundtable/rendered-screens/distinctiveness-blind-contact-sheet.jpg`
  - contact-sheet SHA-256: `694f7a3cd42a6401196e414b4daafdf5c5bf2d3e6268cdc148175c52383f109a`

## 4. What Is Currently Broken Or Unresolved

### G11 Distinctiveness Is Still Not Established

`best-practices-bespoke-design` requires blind, swap, family, and leakage testing. The current design-world checker still reports `distinctiveness_blind: NOT_TESTED`. Do not claim `READY`.

### Ask Browser Attachment Evidence Is Not Reliable Enough

Do not launch another broad `/ask` browser roundtable until the attachment path and provider metadata issue is handled.

Observed attempts:

- R3 WebGemini relative-path run:
  - run directory: `/mnt/storage12tb/skills/ask/outputs/.ask_artifacts/tau-dag-runs/grahama-distinctiveness-blind-r3-webgemini`
  - result: `BLOCKED` / `MISSING_SENTINEL`
  - concrete cause: `browser_attachment_missing: requested attachment(s) not readable: ../../site/design-roundtable/rendered-screens/distinctiveness-blind-contact-sheet.jpg`
  - response chars: `0`
- R4 WebGemini absolute-path run:
  - run directory: `/mnt/storage12tb/skills/ask/outputs/.ask_artifacts/tau-dag-runs/grahama-distinctiveness-blind-r4-webgemini-abs`
  - command was interrupted after the user objected to local-path churn, but artifacts exist
  - node receipt: `status: NEEDS_ATTENTION`
  - failure code: `browser_attachment_unavailable`
  - requested attachment path was absolute and locally readable
  - raw response contains a sentinel and a plausible rater answer, but Ask rejected it because attachment metadata was unavailable: `attachment.attached: false`
  - treat the R4 response as advisory only; do not count it toward the five-rater threshold

### Clipboard / Manual Bundle

A containment bundle was created and copied to the desktop clipboard as a file item:

- zip: `/tmp/grahama-bespoke-g11-handoff-20260809T164552Z.zip`
- SHA-256: `018418276d72f9caca63bd4a686a00aa82159b664081ddced3d7c04eb0a10f44`
- clipboard verification: `TARGET=text/uri-list`, `URI=file:///tmp/grahama-bespoke-g11-handoff-20260809T164552Z.zip`

Bundle contents:

- `rater-packet/distinctiveness-rater-prompt.r2.md`
- `rater-packet/distinctiveness-blind-contact-sheet.jpg`
- `rater-packet/grahama-distinctiveness-rater-packet.pdf`
- `ask-r3-webgemini-relative/` receipts for the failed relative-path run
- `ask-r4-webgemini-absolute/` receipts and advisory response for the interrupted absolute-path run
- `README.md` explaining why the receipts are not compliance proof

## 5. Next Steps

1. Stop broad browser-agent churn. Do not open more blank/unsubmitted browser windows.
2. Use the zip bundle for a human or manually controlled model review, or repair Ask/Surf attachment metadata first.
3. If using `/ask` again, run one lane only, with a single uploadable bundle and no local paths in the model-facing prompt. Inspect `node-receipt.json` before launching another lane.
4. To satisfy G11, collect at least five usable fresh-context rater outputs and create a validation receipt that `design-world-check` can consume.
5. Only after G11 has real receipts should `design-world-check` be changed from `NOT_TESTED` to `PASS` for distinctiveness.
6. After G11, run the final command set from the WebGPT eight-PR plan, including accessibility, performance, build, and receipt validation.

## 6. Key Files

- `skills/monitor-website/local/HANDOFF.md`
- `skills/monitor-website/scripts/design_world_check.py`
- `site/design-world.yml`
- `site/DESIGN_WORLD.md`
- `site/design-roundtable/visual-world-brief.r1.yaml`
- `site/design-roundtable/territory-selection.r1.json`
- `site/design-roundtable/distinctiveness-rater-prompt.r2.md`
- `site/design-roundtable/rendered-screens/distinctiveness-blind-contact-sheet.jpg`
- `site/design-roundtable/font-receipt.r1.json`
- `site/design-roundtable/responsive-geometry.r1.json`
- `site/design-roundtable/craft-integrity.r1.json`

## 7. Stop Condition

The original goal remains active and **not met** until either:

- every `best-practices-bespoke-design` gate, including G11, G16, G17, G18, G19, and G20, has a local receipt and the final verifier set passes; or
- the same Ask/browser attachment blocker repeats across the required blocked-audit turns and no manual/human or alternate rater route is available.
