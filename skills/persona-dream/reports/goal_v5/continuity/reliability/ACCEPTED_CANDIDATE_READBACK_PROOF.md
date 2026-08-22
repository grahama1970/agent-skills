# soak35 Chatterbox ASR drift: root cause and repair (#1489)

## Root cause

`session_mood_chatterbox_live.render_turn` compared `answer_text` against
`chunks[0].asr_verification.candidates[0]` — the *first* candidate in the
payload, not the candidate the service accepted.

Chatterbox renders up to `asr_max_candidates` variants and accepts the first
that clears its own gate, leaving rejected variants in the response. Every
`BLOCKED_CHATTERBOX_ASR_TEXT_DRIFT` in every recorded campaign was a rejected
sibling variant being read back instead of the delivered audio.

Verified directly from the archived live payload
`soak35_repaired_measured_pace/cycle_017/chatterbox_live/turn_001_response.json`:

```
chunk 0  ok True  accepted_candidate_index 2  accepted_variant cooler_penalty  candidate_count 2
  candidate_index 1  stage_default    gate ok False  wer 0.3077  'The boundary is clear, the facts remain the same.'
  candidate_index 2  cooler_penalty   gate ok True   wer 0.0     'The answer is unchanged. The boundary is clear. The facts remain the same.'
```

Cycle 033 is identical. Cycle 007's drift is at `turn_002`, same shape.

## Change

`skills/persona-dream/scripts/session_mood_chatterbox_live.py`

- New `accepted_candidate(verification)` resolves the candidate matching
  `accepted_candidate_index`, and raises
  `BLOCKED_CHATTERBOX_ASR_ACCEPTED_CANDIDATE_MISSING` if the service reports an
  index it did not return.
- New `collect_accepted_asr(response)` returns the accepted transcript, gate,
  variant, and audio path for every chunk, and raises
  `BLOCKED_CHATTERBOX_ASR_CHUNKS_MISSING` on an empty payload.
- `render_turn` now gates on every chunk's accepted gate and exact-matches the
  joined accepted transcript against `answer_text`.
- `asr_accepted_candidates` is recorded in the receipt so the compared render is
  auditable after the fact; the drift error now names the accepted candidates.

Answer invariance is not weakened. The comparison is still exact under
`_normalize_text`, `asr_max_wer` stays `0.0`, and the gate check is now stricter
(every chunk, not just the first). What changed is *which* render is compared:
the one that was delivered.

## Validation

Deterministic replay of the fixed selector over all 212 archived live response
payloads under `reports/goal_v5/continuity/reliability/soak35*`:

```
replayed 212 archived live responses, drift now 0
```

Zero payloads had an *accepted* candidate that drifted — the defect was entirely
client-side readback. The 8 previously-flagged turns (soak35 017/024,
soak35_presoak_short_answer 001/002/003, soak35_repaired_measured_pace
007/017/033) all had an exact, `wer 0.0` accepted transcript.

Required proof:

```
skills/agentic-evals/run.sh run skills/persona-dream/fixtures/agentic_eval.json \
  --case session-mood-delivery-contract-tests \
  --output /tmp/persona-dream-session-mood-agentic-eval.json --report-only
```

Result: 3 trials, all `PASS`, `18 passed` per trial, exit 0.

```
uv run --project skills/persona-dream pytest \
  skills/persona-dream/tests/test_live_chain_receipt.py \
  skills/persona-dream/tests/test_session_mood_binding.py \
  skills/persona-dream/tests/test_session_mood_chatterbox_live.py \
  skills/persona-dream/tests/test_live_chain_reliability.py -q
```

Result: `26 passed`.

## Proof boundary

The replay above is deterministic over *real* live payloads captured from
Chatterbox `/synthesize-batch` during the 20260822 campaigns — not fixtures and
not mocks — but it is a replay, not a fresh render. A fresh live 35-cycle
campaign is recorded separately under
`soak35_accepted_candidate_readback/AGGREGATE_RECEIPT.json`.
