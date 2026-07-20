# Handoff Report: Persona Dream

**Timestamp:** 2026-07-19 (post-pilot-execution; M5 human gates pending)
**Repository:** `/home/graham/workspace/experiments/agent-skills-main` (branch `main`, canonical remote agent-skills@main; latest handoff-relevant commit `864f6cf5`)
**Skill root:** `skills/persona-dream`
**Controlling goal:** `GOAL_V2.md` (immutable; supersedes GOAL.md v1, which carries a pointer note)
**Goal checker:** `python3 scripts/check_goal_v2_boundary.py --json` — the single machine proof; exit 0 + `PASS_GOAL_V2_P0_BOUNDARY` = goal complete
**Active revision:** `rev_successor_943b01ecd9a3`
**Current truth page:** `CURRENT_STATE.md` (generated; `generate_current_state.py --check` is in the test suite)

## 1. Where This Stands (checker state, VERIFIED 2026-07-19)

| Criterion | State | Authority |
|---|---|---|
| P0.1 human acceptance | **MISSING — HUMAN ONLY** | operator watches `provider_return.mp4` (sha256 `59b9ff3155d6…e211fff`) and authors `RR/human_acceptance_receipt.v1.json` (`author:"human"`, video sha, verdict). Agents must never author it. |
| P0.2 v2 lineage | PASS | `RR/watch_gauntlet/59b9ff3155d6/cognitive_loop_v2/lineage_receipt.v1.json` |
| P0.3 routing semantics | PASS | `RR/routing_semantics_calibration_receipt.v1.json` (montage 6/6 exact) |
| P0.4 GMO pin | PASS | `RR/gmo_deployment_pin.v1.json` |
| P0.5 phase16 v2 | PASS | `RR/phase_16_behavior_evaluation/phase16_v2_lineage_receipt.v1.json` |
| P0.6 voice expression | PASS | `RR/voice_expression/voice_expression_evaluation_receipt.v1.json` (text+audio PASS, LatentSync 1.5 canary `output_ready`, zero paid video calls) |
| P0.7 pilot result | **MISSING — waits on the two human gates below, then two agent commands** | `contracts/pilot_c_vs_f_result_receipt.v1.json` (checker requires `published_under == pilot_c_vs_f_frozen_protocol.v3` + final protocol hash `483fb170…d0ee0a6` + supersession lineage + `m5_read_author:"human"`) |

`RR` = `reports/pipeline-complete/.persona-dream/revisions/rev_successor_943b01ecd9a3`.

## 2. THE ONLY REMAINING WORK

**Human gate A — M5 blind read** (`reports/pilot_c_vs_f/m5/`):
Operator reads `pair_r1_X.md` vs `pair_r1_Y.md`, then `pair_r2_X.md` vs
`pair_r2_Y.md` (no agent summaries), and writes `judgment_r1.json` +
`judgment_r2.json` per `OPERATOR_INSTRUCTIONS.md` in that directory
(`author:"human"` required; assembler hard-blocks otherwise). X/Y order is
sealed per pair behind sha256 commitments (`sealed/`, commitments alongside).

**Human gate B — P0.1 acceptance receipt** (see P0.1 row above).

**Then the successor agent runs exactly:**
1. Per pair: `python3 scripts/pilot_m5_presentation.py unseal --pair-id r1 --out-dir reports/pilot_c_vs_f/m5 --judgment reports/pilot_c_vs_f/m5/judgment_r1.json` (and r2) — verifies commitments, reveals mapping.
2. Verify the manifest first: `python3 scripts/pilot_run_manifest.py --verify` must exit 0. Then assemble:
   `python3 scripts/pilot_result_receipt.py --metrics-dir reports/pilot_c_vs_f/metrics --m5-dir reports/pilot_c_vs_f/m5 --blinding-dir <staging dir> --scope-notes <optional>`
   (NOTE: the assembler expects `blinding_<RUN>.json` all in ONE dir — copy
   the four from `reports/pilot_c_vs_f/runs/<RUN>/blinding_<RUN>.json` into a
   staging dir first. Metrics receipts already exist at
   `reports/pilot_c_vs_f/metrics/metrics_<RUN>.json`.)
3. `python3 scripts/check_goal_v2_boundary.py --json` — with both human
   receipts present this should exit 0. Regenerate `CURRENT_STATE.md`
   (`generate_current_state.py`), commit, push.

**Expected result: NULL** (a valid completion under the frozen decision rule) —
precommitted in amendment v1: R1-F's N1 negative-control failure is retained
literally (the R1-F dream legitimately contains SN15 launch-vehicle imagery
matching the "orbital telemetry" control; premise break documented, no waiver).

## 3. What Was Done This Session (all receipt-backed, committed, pushed)

- **P0.6 complete**: voice pipeline (Tau text → chatterbox_turbo `/synthesize`
  — response `audio` is a CONTAINER path `/out/<label>.wav`, host mount
  `~/workspace/experiments/chatterbox/logs`; Whisper CPU ASR accuracies
  0.966/1.0/0.917/1.0) + LatentSync **1.5** lip-sync canary (8 GB VRAM path:
  dedicated venv `~/workspace/experiments/LatentSync/.venv-latentsync`, ckpt
  `checkpoints-v1.5/latentsync_unet.pt`, config `stage2.yaml`; chatterbox
  container stopped for VRAM during the run and restarted, health verified).
- **P0.7 protocol lineage**: v2 selection ruled gameable by webgpt →
  **protocol v3** (`contracts/pilot_c_vs_f_frozen_protocol.v3.md`): frozen
  cluster ontology (age-band × person-tag), biographical recency, seeded-hash
  tie-break, first-original-order disjoint R2, K=3 member cap, fail-closed
  timestamps. R1 = `age23_current:person:brandon`, R2 =
  `age19_23:person:marketa_lawson` (addendum appended; selection deterministic).
- **GOAL_V2 checker correction** (webgpt-approved, stricter): p0_7 requires v3
  + final protocol hash + lineage (the goal text said v2; the round-2 ruling
  explicitly accepted this pre-run authority correction; disclosed to the
  operator in-session).
- **Four arms executed in frozen order** R1-C → R1-F → R2-F → R2-C
  (runners: `run_pilot_arm.py` for C, `run_pilot_arm_f.py` for F). All
  persisted through the certified transactional path and ACTIVATED
  (`/persona-dream/commit/activate`), produced records read back `active`:
  `dream_pilot_r1_c`, `dream_pilot_r1_f`, `dream_pilot_r2_f`, `dream_pilot_r2_c`.
  F frames: gpt-image-2 via the standard phase_c engine; **the prompt MUST name
  the Embry contact-sheet absolute path** (codex `view_image` loads it —
  without it ArcFace cosines drop to ~0.22; with it 0.72–0.80 vs gate 0.421).
- **Measurement amendment lineage v1→v1.5** (all pre-M5, originals preserved
  in `reports/pilot_c_vs_f/metrics_original_v1/`), through 9 adversarial
  webgpt rounds ending **PASS_CURRENT_GATE**:
  real claim-level M2 (persist-snapshot keyset hash ownership + edge/endpoint
  resolution), M4 fail-closed typed classifier, M3 = **closed enum contract**
  (DENIED/AFFIRMED/UNCERTAIN/CONTRADICTORY + record_class vs stored kind;
  free text audit-only — the v1.1–v1.4 regex classifier stack is retired),
  deletion-only M5 redaction, N1 precommitment.
- **Final metrics** (uniform, committed): M3 PASS ×4 (all DENIED + correct
  class), M4 PASS ×4 (7 anchors byte-unchanged incl. dream-004 node), M2 0.0
  ×4 — REAL symmetric finding: both arms' `grounds_interpretation` edges cite
  watch-evidence vertices never persisted (runners passed `watch_vertices=[]`);
  reported, not patched. M1 positives absent ×4 (frozen dream-004 probes don't
  match new content; symmetric).

## 4. Standing Constraints (unchanged)

- Only /tau reaches /scillm (strict checker exit 0). ArcFace buffalo_l 0.421 is
  the sole identity authority; VLM advisory only. Evidence classes never
  silently convert. Paid video calls forbidden; imagegen via the established
  scillm lane is normal operation. WebGPT reviews: tab 837359230, routing proof
  required every submit; `-p persona-dream` route.
- GMO daemon `embry-memory` (127.0.0.1:8601): default `/list` hides pending
  records (add `visibility_state` to filters to bypass). It wedged once this
  session (worker pool stuck during an unrelated 22 GB SPARTA Arango scan
  burst; app-container restart fixed it — DB untouched). The scillm proxy 502s
  during the same window; a 502 on `/v1/chat/completions` with "JSON
  validation failed after repair" in proxy logs means the MODEL answered in
  prose — the prompt must explicitly demand strict JSON (or use the closed
  enum contract).
- Harness kills long background tasks in this environment (multiple kills this
  session; NOT the operator — confirmed in-session). Run long webgpt
  submits/extracts in FOREGROUND with `timeout ≤580`; extraction with the
  sentinel via `surf webgpt.extract --tab-id 837359230 --sentinel ... --wait`
  recovers responses whose submit process was killed after injection (receipt
  `submitted: true` tells you which case you're in).

## 5. Known Residual Risks / Deferred

- M2's dangling-citation defect (watch-evidence vertices not persisted by arm
  runners) is a producer-machinery fix for any successor protocol — do NOT
  re-persist the executed arms.
- Brandon/Marketa have no identity reference sheets (Embry-only ArcFace
  certification; disclosed in F receipts as scope notes).
- The M1 probe set is dream-004-specific; a successor protocol needs
  content-matched probes frozen at selection time.
- `local/webgpt-bundles/` holds all 9 review rounds (bundle + response +
  routing meta per round) — the full adversarial audit trail.
