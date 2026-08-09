# Handoff Report: monitor-website / grahama.co Bespoke Design

**Timestamp**: 2026-08-09T19:02:45-04:00  
**Active Agent**: Codex  
**Human Direction**: Do not push this version to grahama.co. Do not claim READY/PASS for formal bespoke design without deterministic local receipts.

## 1. Project Overview

- **Ecosystem**: agent-skills monorepo; `site/` is a Next/TypeScript site; `skills/monitor-website` owns website audit/gate commands.
- **Core Purpose**: `README.md` describes this repo as a shared toolbox and playground for agent work: reusable capabilities, bounded workers, persona contracts, lifecycle hooks, and public evidence behind grahama.co.
- **Active Surface**: grahama.co public-site redesign and formal `$best-practices-bespoke-design` gate through `skills/monitor-website/run.sh design-world-check --json`.

## 2. Current State (Doc-Code Alignment)

- **Documented monitor-website contract**: `skills/monitor-website/SKILL.md` says website visual maintenance composes with `$best-practices-bespoke-design` and must not be reported ready from prose confidence.
- **Implemented reality**: `skills/monitor-website/scripts/design_world_check.py` now rejects responsive/blind/craft receipts unless they reference a section-cropped screenshot corpus.
- **Current formal status**: `FAIL / NOT_READY`.
- **Blocking gate**: G11 `distinctiveness_blind`.
- **Failure signature**: `G11 competitor-swap subgate failed: only 1 usable rater reported competitor-swap tension; threshold requires 4.`
- **Offline website audit drift**: `skills/monitor-website/run.sh audit --no-live --json` exited `1`; generated surfaces are stale against `HEAD d0afbcdfbf`: `inventory.json`, `artifacts.json`, `catalog.json`, `research-map.json`, `graph.json`, `resume.json`, `competence.json`.
- **Copy audit**: `skills/monitor-website/run.sh copy-audit --json` exited `0` with `status: PASS`.

## 3. What is Working Well

- **TypeScript**: `cd site && npx tsc --noEmit` exited `0`.
- **Section screenshot corpus**: `site/design-roundtable/rendered-screens/responsive-section-corpus-20260809T213528Z/manifest.json`
  - `viewports: 5`
  - `sections: 10`
  - `screenshots: 50`
  - `failures: 0`
  - SHA in gate: `951d8f7797cdb7b9a9fe2d42d156fc0ba24813d11cca4a73dcac4e3fd106f08b`
- **Responsive choreography gate**: `PASS`
  - receipt: `site/design-roundtable/responsive-geometry.r1.json`
  - `routes: 6`
  - `viewports: 5`
  - `checks: 30`
  - `failures: 0`
- **Craft integrity gate**: `PASS`
  - receipt: `site/design-roundtable/craft-integrity.r1.json`
  - visual assets check: `PASS`, `registered_assets: 31`, `public_visuals: 31`, `evidence_assets: 4`
  - effects check: `PASS`, `registered_effects: 5`, `removed_homepage_effects: 5`, `removed_public_effects: 3`
- **Tau repair loop**: latest successful receipt is `site/design-roundtable/tau-g11-repair-loop/run-20260809T2136Z/dag-receipt.json`.
- **Human-visible ledger**: `site/design-roundtable/live-collaboration-ledger.html`.
- **Ledger CDP proof**: `.codex/ui-verification/latest.json` points at `/tmp/codex-ui-verification/agent-skills/grahama-g11-rater-disposition-current/20260809T221611Z.png`.

## 4. What is Currently Broken

- **Formal bespoke design is not passing**:
  - command: `skills/monitor-website/run.sh design-world-check --json`
  - latest captured output: `/tmp/handoff-design-world.json`
  - exit code: `1`
  - status: `FAIL`
  - G11 usable raters: `4`
  - G11 competitor-swap tension: `1`
  - required competitor-swap tension: `4`
- **Fresh post-repair rater supply is not clean**:
  - disposition: `site/design-roundtable/g11-rater-disposition.r1.json`
  - post-repair attempts recorded: `4`
  - WebGPT availability: `site/design-roundtable/provider-receipts/webgpt-availability-20260809T2214.json`
    - `live: true`
    - `mocked: false`
    - `status: NEEDS_ATTENTION`
    - `provider_limited: true`
    - observed modal: `Too many requests`
  - Gemini lane: attachment unavailable / not a clean seat.
  - Claude lane: no submitted model response / not a clean seat.
  - Kimi lane: degraded text exists but receipt failed; do not count as formal seat.
- **The design failure is not only provider supply**: stored valid raters include real `COMPETITOR_SWAP_TENSION: no` votes, so do not describe the state as merely "waiting on WebGPT."
- **Generated site surfaces are stale** according to `monitor-website audit --no-live`.
- **Do not push/deploy**: human explicitly said not to push this version to grahama.co.
- **Missing formal receipts remain**:
  - fresh five-seat G11 blind rater packet against the post-repair section corpus
  - current accessibility receipt
  - current performance receipt
  - independent finish-loop receipt
  - asset-rights/license metadata receipt

## 5. Next Steps

1. Keep the formal state as `FAIL / NOT_READY` until `design-world-check --json` exits `0`.
2. Do not redesign broadly. The immediate proof step is clean G11 rater seats against `site/design-roundtable/rendered-screens/responsive-section-corpus-20260809T213528Z/contact-sheet.png`.
3. Before using WebGPT, rerun:
   ```bash
   skills/ask/run.sh browser-availability --provider webgpt --json
   ```
   Continue only if `provider_limited` is false and the provider is usable.
4. If WebGPT is still limited, repair or use independent non-GPT lanes one at a time. Do not launch a multi-provider run where one failed attachment lane cancels the others.
5. Stop condition for G11: at least `5` usable fresh-context raters and at least `4` with `COMPETITOR_SWAP_TENSION: yes`.
6. After G11 succeeds, run the remaining formal receipts: accessibility, performance, independent finish loop, and asset-rights/license validation.
7. Only after all required receipts exist, rerun:
   ```bash
   skills/monitor-website/run.sh design-world-check --json
   ```

## 6. Project Context for Success

- **Primary commands**:
  - `skills/monitor-website/run.sh design-world-check --json`
  - `skills/monitor-website/run.sh copy-audit --json`
  - `skills/monitor-website/run.sh audit --no-live --json`
  - `cd site && npx tsc --noEmit`
  - `~/.codex/hooks/verify-ui-cdp.sh --url file:///home/graham/workspace/experiments/agent-skills/site/design-roundtable/live-collaboration-ledger.html --name grahama-g11-rater-disposition-current`
- **Primary artifacts**:
  - `site/design-roundtable/g11-rater-disposition.r1.json`
  - `site/design-roundtable/live-collaboration-ledger.html`
  - `site/design-roundtable/provider-receipts/webgpt-availability-20260809T2214.json`
  - `site/design-roundtable/rendered-screens/responsive-section-corpus-20260809T213528Z/manifest.json`
  - `site/design-roundtable/rendered-screens/responsive-section-corpus-20260809T213528Z/contact-sheet.png`
  - `site/design-roundtable/tau-g11-repair-loop/run-20260809T2136Z/dag-receipt.json`
  - `.codex/ui-verification/latest.json`
- **Touched source paths in this lane**:
  - `site/app/page.tsx`
  - `site/app/globals.css`
  - `site/components/capability-search.tsx`
  - `site/components/capability-constellation.tsx`
  - `skills/monitor-website/scripts/design_world_check.py`
  - `skills/monitor-website/SKILL.md`
  - `skills/best-practices-bespoke-design/SKILL.md`
  - `site/scripts/capture_responsive_section_corpus.py`
  - `site/scripts/tau_g11_repair_node.py`
  - `site/scripts/tau_g11_review_node.py`
- **Recent commits before this handoff**:
  - `d0afbcdfbf` Add non-expert analyst bench to monitor-sparta agentic evals
  - `54582788b9` best-practices-resume: rule 18
  - `2729916f4b` ask: land browser seat windows on Desktop 2
  - `e3a5c080b7` ask: browser-availability probe hard-kills its process group on timeout (#1307)
  - `05ba743207` Add best-practices-font skill
- **Known handoff skill gap**: `.pi/skills/handoff/run.sh` is missing, so this handoff used deterministic local commands instead of that automated entrypoint.

## 7. Non-Negotiable Handoff Warnings

- Do not count a degraded provider response as a formal rater if the lane receipt is `NEEDS_ATTENTION`.
- Do not count the whole-page image as G11 proof. Use section/component/page-state crops.
- Do not push to grahama.co from this state.
- Do not claim `PASS`, `READY`, `done`, `fixed`, `green`, or `verified` for the formal bespoke goal unless `design-world-check --json` and all required receipts prove it.
- Every user-facing status must include the immutable line:
  ```text
  Immutable Goal: NOT_MET
  ```
