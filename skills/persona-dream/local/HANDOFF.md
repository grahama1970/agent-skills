# Handoff Report: Persona Dream

**Timestamp:** 2026-07-26T12:17:44-04:00 / 20260726T161744Z
**Active agent:** Codex
**Repository:** `grahama1970/agent-skills`
**Target branch:** `main`
**Worktree used:** `/home/graham/workspace/experiments/agent-skills-persona-dream-asr-main`
**Skill root:** `skills/persona-dream`
**Current local commit before this handoff:** `39beeec1060f1f0c380fd863263acca399e41387`

## Operating Model

`GOAL.md` is the active immutable-goal source for current work. The controlling
objective is PCTOM-R: a text-first prospective Theory-of-Mind reliability lane
with provenance-bound recall residue, deterministic hidden-state social
episodes, valid ToM distributions, sealed prediction commitments, deterministic
scoring, non-destructive belief revision, and fail-closed checks.

Provider video, media-spine delivery, Chatterbox voice expression, subjective
dream quality, dashboards, and human-facing dream-content review are historical
or supporting lanes unless the operator explicitly reactivates them. Do not
promote voice or provider work to the critical path from README context alone.

The current `persona-dream/SKILL.md` contract still covers the broader dream
packet and media planning skill. It explicitly treats voiced dream videos as an
audio handoff lane: `persona-dream` may emit `timed_transcript.json` and
`voice_handoff_plan.json`, but TTS rendering, voice cloning/fine-tuning, eval,
mix, mux, and final audio identity review belong to downstream audio/movie
skills. Paid provider modes require explicit cost, entitlement, and provider
readiness gates.

## Current State

Recent commits relevant to this handoff:

- `39beeec10` - `persona-dream: record supporting voice lane`
- `6b880673b` - `persona-dream: close ASR batch emotion proof`
- `4f4864905` - `persona-dream: handoff -- weighted-emotion voice complete (3 repos merged, live)`
- `14ee49f91` - `persona-dream: close the loop -- memory.intent emits emotion weight -> audible voice`

The latest issue-oriented work closed GitHub issue `#1009` by recording the
weighted-emotion Chatterbox ASR batch work as a supporting voice lane in
`GOAL.md`. That did not change the active immutable goal: PCTOM-R remains the
controlling research objective.

The previous `local/HANDOFF.md` was stale. It described the 2026-07-20 live
Memory recall rung and said the handoff helper was unavailable. On this run,
`skills/handoff/run.sh` exists and exited 0; its output was captured at:

```text
/tmp/persona-dream-handoff-20260726T161744Z/handoff-run.txt
```

## Evidence Map

### PCTOM-R Evidence

`GOAL.md` records the current PCTOM-R evidence snapshot. The reported hardening
bundle includes:

- `PASS_PCTOM_GOAL_COVERAGE` with 15 required coverage ids seen, 43 evidence
  receipts, 31 positive rows, 12 negative rows, 19 live positive rows, and 0
  unbound evidence rows.
- `PASS_PCTOM_SUCCESS_CRITERIA_AUDIT` with 6 input receipts checked, 0 input
  receipt self-hash mismatches, 0 forbidden counters, and every current
  hard-success criterion true within the text-first PCTOM-R evidence scope.
- `PASS_PCTOM_OBJECTIVE_EVIDENCE_AUDIT` over 43 child evidence receipts, 15/15
  coverage ids, 19 live positive rows, 12 negative rows, 0 human-content-judgment
  rows, 0 LLM-judge rows, and 0 mocked-not-false rows.
- Variant 25-26 cross-family evidence: 128 deterministic social episodes, 32/32
  live Tau calls in the small balanced-planning slice, and fail-closed mutated
  action negatives.

These claims are recorded in `GOAL.md`; this handoff did not rerun the full
PCTOM-R bundle. Do not turn the recorded PCTOM-R receipts into claims about paid
provider execution, semantic dream quality, multimodal perception, or complete
live Phase 01-16 media runtime.

### Weighted-Emotion Voice Lane

The supporting Chatterbox voice lane now has a live, non-mocked ASR batch proof:

```text
skills/persona-dream/reports/goal_v5/emotion_proof/asr_batch/RECEIPT.json
```

Receipt summary:

- `mocked: false`
- `live: true`
- Endpoint: `POST http://127.0.0.1:8018/synthesize-batch`
- Request carried `voice_delivery` with `tone=firm_boundary`,
  `intensity=0.9`, `valence=-0.7`, `use_base_emotion=true`, and
  `source=memory.intent`.
- Result selected `chatterbox_base` for top-level, chunk, cache-material, and
  ASR candidate engine metadata.
- Derived emotion knobs: `exaggeration=1.11`, `cfg_weight=0.36`,
  `temperature=0.7`, `intensity=0.9`, `valence=-0.7`.
- ASR transcript exactly matched `I will hold the boundary clearly.` with
  `WER=0.0` and no failed gates.
- Chatterbox fix commit: `d6d2c436d5d7e9981703a8bbdd1493946b9c6c44`.
- Focused Chatterbox tests: 3 passed, 34 deselected.

This closes only the ASR-batch emotion propagation gap. It does not prove
subjective tone acceptance, browser or Jabra microphone behavior, paid provider
execution, production readiness, or that voice work is now the active
persona-dream critical path.

### Ask / Browser Review

A four-seat `$ask` review was requested for WebGPT, WebClaude, WebKimi, and
WebGrok against the current persona-dream state:

```text
/tmp/persona-dream-ask-review-20260726T1305Z/ask-runs/persona-dream-status-review-20260726T1305Z-r2
```

Receipt status:

- DAG receipt: `tau-receipts/dag-receipt.json`
- Overall DAG status: `BLOCKED` / `NODE_BLOCKED`
- `handler-webkimi`: `PASS`
- `handler-webclaude`: `BLOCKED`, `browser_tab_read_timeout`
- `handler-webgpt`: `ERROR`, `prompt_too_large_or_stalled`
- `handler-webgrok`: `ERROR`, `prompt_too_large_or_stalled`

Treat the Kimi output as advisory only. The four-seat review did not complete
and is not proof of project status.

## Current Broken / Brittle State

`skills/persona-dream/sanity.sh` was rerun for this handoff and exits 1:

```text
/tmp/persona-dream-handoff-20260726T161744Z/persona-dream-sanity.txt
```

The failing hard gate is the Tau-only model-routing boundary:

```text
Tau-only routing boundary check [FAIL]
hard_violations=1
skills/persona-dream/local/webgpt_reviews/20260721T-pctom-state-review/ask-artifacts/persona-dream-pctom-state-review-20260721/workers/ask_tau_roundtable_worker.py:46
  parser.add_argument("--scillm-base-url", default="http://127.0.0.1:4001")
skills/persona-dream/local/webgpt_reviews/20260721T-pctom-state-review/ask-artifacts/persona-dream-pctom-state-review-20260721/workers/ask_tau_roundtable_worker.py:876
  f"{base_url}/v1/chat/completions"
```

The sanity log also includes expected negative-control fixture failures for
provider eligibility and contact-sheet sidecars before the final strict routing
failure. The terminal blocker for full green is the unsanctioned direct Scillm
route in a historical local WebGPT review artifact.

Other known gaps:

- The repo main worktree does not contain `scripts/check_mock_evidence_claims.py`,
  so that CI-style evidence wording checker could not be run here.
- `README.md` has internal status drift: early/current-state prose says Phase 16
  is live-proven for a machine-decidable slice, while the later pipeline table
  still says Phase 16 is not implemented as a closed proof.
- README and project knowledge include media, Chatterbox, journal, personality,
  and provider narratives that are useful context but can easily be mistaken for
  the active immutable critical path. `GOAL.md` should control when claims
  conflict.
- The current qualified revision in `SKILL.md` is
  `rev_successor_943b01ecd9a3`; earlier revisions and provider returns are
  historical unless explicitly used as evidence with their receipt boundaries.

## What Is Working

- The PCTOM-R objective is explicitly written in `GOAL.md` and narrows the
  current critical path away from provider/video/dashboard work.
- `GOAL.md` now records the weighted-emotion Chatterbox ASR batch lane as
  supporting evidence without reactivating the media runtime as the controlling
  goal.
- The ASR batch receipt is valid JSON and records live, non-mocked endpoint
  evidence for weighted `voice_delivery` surviving accepted ASR candidate
  generation.
- `skills/handoff/run.sh` is available in this checkout and exits 0.
- Issue `#1009` is closed with a committed `GOAL.md` supporting-lane record.

## Not Proven

- End-to-end completion of Persona Dream across all research ambitions.
- Paid provider video execution as current critical path.
- Full Phase 01-16 live media runtime execution under current artifacts.
- Human subjective acceptance of the dream video.
- Semantic dream quality or psychological/personality value beyond the receipt
  scopes recorded in `GOAL.md` and `PROJECT_KNOWLEDGE.md`.
- Browser/Jabra microphone behavior or production Chatterbox voice readiness.
- Successful four-seat Ask consensus review.
- Full `persona-dream/sanity.sh` green status on main.

## Recommended Next Steps

1. Repair or quarantine the historical local WebGPT review artifact that directly
   references `http://127.0.0.1:4001`, then rerun `skills/persona-dream/sanity.sh`
   and preserve the new log/receipt.

2. Reconcile README status drift. The minimum repair is to update the Phase 16
   table row and current-state proof boundary so it agrees with `GOAL.md`:
   PCTOM-R controls, Phase 16/media-spine claims are bounded, and voice/provider
   lanes remain supporting unless reactivated.

3. If continuing PCTOM-R hardening, rerun or refresh the exact `GOAL.md`
   coverage/success/objective audit receipts into a durable, non-`/tmp` report
   directory, then update `PROJECT_KNOWLEDGE.md` only with command outputs and
   receipt hashes.

4. If continuing Chatterbox integration, run a broader live matrix that includes
   no-emotion regression, emotion-on cache/idempotence behavior, browser route
   evidence, and microphone/Jabra input only when the user-facing claim requires
   it. Keep those as supporting voice-lane receipts.

5. Treat `$ask` browser review as degraded until the transport issues are fixed.
   Do not use partial Kimi review or stale WebGPT artifacts as proof authority.

## Key Files

```text
skills/persona-dream/GOAL.md
skills/persona-dream/SKILL.md
skills/persona-dream/README.md
skills/persona-dream/PROJECT_KNOWLEDGE.md
skills/persona-dream/sanity.sh
skills/persona-dream/local/HANDOFF-emotion-voice.md
skills/persona-dream/reports/goal_v5/emotion_proof/asr_batch/RECEIPT.json
skills/persona-dream/local/webgpt_reviews/20260721T-pctom-state-review/ask-artifacts/persona-dream-pctom-state-review-20260721/workers/ask_tau_roundtable_worker.py
```

## Claim Boundary For Successor Agent

Use this phrasing:

```text
PCTOM-R remains the active immutable Persona Dream objective. The 2026-07-26
voice work is supporting Chatterbox integration evidence: a live, non-mocked
ASR batch receipt proves weighted voice_delivery reaches the accepted
chatterbox_base ASR candidate with WER 0.0. Full persona-dream sanity is not
green because a historical local WebGPT review artifact violates the Tau-only
Scillm routing boundary.
```

Do not say:

```text
persona-dream is complete
the immutable goal is fully achieved by the ASR batch proof
WebGPT/WebClaude/WebGrok reviewed and accepted the current status
provider/video work is the current critical path
Phase 01-16 media runtime is fully live-proven by the PCTOM-R receipts
```
