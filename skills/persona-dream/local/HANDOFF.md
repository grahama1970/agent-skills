# Handoff Report: Persona Dream

**Timestamp:** 2026-07-27T08:03:06-04:00 / 20260727T120306Z
**Active agent:** Codex
**Repository:** `grahama1970/agent-skills`
**Target branch:** `main`
**Worktree used:** `/home/graham/workspace/experiments/agent-skills-persona-dream-next`
**Skill root:** `skills/persona-dream`
**Current local commit before this handoff:** `9c800aac157ad709ec3fe30d4ed479b173fab255`

## 2026-07-27 Superseding Operating Snapshot

The accepted reassessment changed the top-level hierarchy. `GOAL.md`,
`README.md`, `PROJECT_KNOWLEDGE.md`, and `SKILL.md` now align on:

1. Build Embry as a persistent persona whose explicitly synthetic dreams produce
   bounded, provenance-linked changes in self-narrative, arc state, session
   mood, and voice while preserving identity, factual competence, answer
   content, and synthetic-versus-literal boundaries.
2. Keep PCTOM-R as a research workstream under that goal, not the whole project
   identity.
3. Treat Kling, Watch, Memory persistence, Chatterbox voice expression, and Tau
   orchestration as supporting technology lanes with their own receipts and
   proof boundaries.

Machine-readable status was added:

```text
skills/persona-dream/CURRENT_STATUS.json
```

Fresh focused proof for the old sanity blocker:

```text
uv run --project skills/persona-dream pytest skills/persona-dream/tests/test_tau_routing_boundary.py -q
result: 7 passed

./skills/persona-dream/run.sh check-tau-routing-boundary --strict --json
result: PASS, hard_violations=0, temporary_debt=0, stale_allow_entries=0
```

The source repair quarantines generated archived Ask artifacts under
`skills/persona-dream/local/webgpt_reviews/**/ask-artifacts/**` from the
Tau-only runtime-source scan. It preserves the historical worker as evidence
but no longer counts it as live source. The poison fixture still proves that a
fresh direct SciLLM caller under normal source paths fails.

Full `skills/persona-dream/sanity.sh` was rerun after these documentation/status
edits and returned PASS:

```text
491 passed, 9 subtests passed
```

## Operating Model

`GOAL.md` is the active immutable-goal source for current work. The controlling
objective is Embry persistent-persona continuity. PCTOM-R remains critical
research infrastructure, but it is a workstream under the continuity goal.

Provider video, media-spine delivery, Chatterbox voice expression, subjective
dream quality, dashboards, and human-facing dream-content review are historical
or supporting lanes unless they are receipt-bound to the continuity chain. Do
not promote a voice, video, or PCTOM-R slice to completion of the full goal.

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
`GOAL.md`. The 2026-07-27 reassessment then changed the top-level active
immutable goal from PCTOM-R-only to Embry persistent-persona continuity, with
PCTOM-R retained as a research workstream.

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

The 2026-07-26 terminal sanity blocker was repaired in source. The historical
local WebGPT Ask worker remains on disk as evidence, but the Tau-only checker
now quarantines generated archived Ask artifact paths:

```text
skills/persona-dream/local/webgpt_reviews/**/ask-artifacts/**
```

Focused proof after the repair:

```text
uv run --project skills/persona-dream pytest skills/persona-dream/tests/test_tau_routing_boundary.py -q
7 passed

./skills/persona-dream/run.sh check-tau-routing-boundary --strict --json
PASS; hard_violations=0; temporary_debt=0; stale_allow_entries=0
```

Full `skills/persona-dream/sanity.sh` was rerun after the 2026-07-27
documentation/status edits and returned `491 passed, 9 subtests passed`.

Other known gaps:

- The continuity ledger exists as
  `reports/goal_v5/continuity/embry.continuity_state.v1.json`, but is not yet
  proven as authoritative live runtime state across a real conversation.
- The Chatterbox ASR batch receipt proves emotion transport and content
  preservation for one path, not perceived emotion, naturalness, speaker
  similarity, browser/microphone behavior, or stable Embry recognition.
- PCTOM-R machinery is strong, but the small live Tau planning slice does not
  show confidence-bounded counterfactual-dreaming advantage.
- Repeated full dream-pipeline reliability is not proven.
- The current qualified revision in `SKILL.md` is
  `rev_successor_943b01ecd9a3`; earlier revisions and provider returns are
  historical unless explicitly used as evidence with their receipt boundaries.

## What Is Working

- `GOAL.md`, `README.md`, `PROJECT_KNOWLEDGE.md`, and `SKILL.md` now agree on
  the Embry continuity hierarchy with PCTOM-R as a research workstream.
- `CURRENT_STATUS.json` records the controlling goal hash, current phase, latest
  voice proof, continuity artifact boundary, PCTOM-R counts, and active
  blockers.
- The ASR batch receipt is valid JSON and records live, non-mocked endpoint
  evidence for weighted `voice_delivery` surviving accepted ASR candidate
  generation.
- The Tau-only routing boundary focused proof is green with a poison fixture
  showing fresh direct SciLLM callers still fail.

## Not Proven

- End-to-end completion of the Embry continuity goal.
- Continuity ledger as the authoritative runtime state used across live
  conversations.
- Paid provider video execution as current critical path.
- Full Phase 01-16 live media runtime execution under current artifacts.
- Human subjective acceptance of the dream video.
- Semantic dream quality or psychological/personality value beyond the receipt
  scopes recorded in `GOAL.md` and `PROJECT_KNOWLEDGE.md`.
- Browser/Jabra microphone behavior or production Chatterbox voice readiness.
- Successful four-seat Ask consensus review.
- The full Embry continuity chain has not been proven live.

## Recommended Next Steps

1. Build the live continuity-chain receipt:
   `reports/goal_v5/continuity/live_chain/RECEIPT.json`.

2. If continuing PCTOM-R hardening, rerun or refresh the exact `GOAL.md`
   coverage/success/objective audit receipts into a durable, non-`/tmp` report
   directory, then update `PROJECT_KNOWLEDGE.md` only with command outputs and
   receipt hashes.

3. If continuing Chatterbox integration, run a broader live matrix that includes
   no-emotion regression, emotion-on cache/idempotence behavior, browser route
   evidence, and microphone/Jabra input only when the user-facing claim requires
   it. Keep those as supporting voice-lane receipts.

4. Treat `$ask` browser review as degraded until the transport issues are fixed.
   Do not use partial Kimi review or stale WebGPT artifacts as proof authority.

## Key Files

```text
skills/persona-dream/GOAL.md
skills/persona-dream/SKILL.md
skills/persona-dream/README.md
skills/persona-dream/PROJECT_KNOWLEDGE.md
skills/persona-dream/CURRENT_STATUS.json
skills/persona-dream/sanity.sh
skills/persona-dream/local/HANDOFF-emotion-voice.md
skills/persona-dream/reports/goal_v5/emotion_proof/asr_batch/RECEIPT.json
skills/persona-dream/local/webgpt_reviews/20260721T-pctom-state-review/ask-artifacts/persona-dream-pctom-state-review-20260721/workers/ask_tau_roundtable_worker.py
```

## Claim Boundary For Successor Agent

Use this phrasing:

```text
Embry persistent-persona continuity is the active immutable Persona Dream
objective. PCTOM-R is a research workstream under that goal. The 2026-07-26
voice work is supporting Chatterbox integration evidence: a live, non-mocked
ASR batch receipt proves weighted voice_delivery reaches the accepted
chatterbox_base ASR candidate with WER 0.0. The historical local WebGPT Ask
worker is quarantined as archived evidence for Tau-routing scans; fresh direct
SciLLM callers still fail the poison fixture.
```

Do not say:

```text
persona-dream is complete
the immutable goal is fully achieved by the ASR batch proof
WebGPT/WebClaude/WebGrok reviewed and accepted the current status
provider/video work is the current critical path
Phase 01-16 media runtime is fully live-proven by the PCTOM-R receipts
```
