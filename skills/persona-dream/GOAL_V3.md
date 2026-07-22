# GOAL_V3 (immutable): the dream loop is a reliable autonomous affect engine

Chartered: 2026-07-22, from the operator's directive "proceed with 1, 2 and 3"
+ "don't stop until the immutable goal has been met", under the purpose
statement recorded in GOAL_V2_AMENDMENT_1.md / PROJECT_KNOWLEDGE.md: dreams
are Embry's affect engine — accurate given her experience, produced by a
reliable unattended pipeline, feeding conversational tone and emotional-tag
weights to her chatterbox voice.

## Primary proof

`python3 scripts/check_goal_v3_boundary.py --json` exits 0 with
`PASS_GOAL_V3_BOUNDARY`, validating on disk (hash-bound receipts) the three
criteria below. All receipts are produced by live runs through the real path
— no fixtures, no mocks, agent-authored throughout.

## Completion criteria

- V3.1 DREAM->VOICE WEIGHTS: `scripts/dream_voice_weights.py` derives a
  deterministic voice-weight profile (per-chunk tone/pace tags + synthesis
  params) from an ACTIVE canonical dream node read live from the store (ToM
  state types + accepted interpretations + emotional_intensity), and renders
  it through the live chatterbox `/synthesize` route. Receipt
  (`voice_weights/<dream>/dream_voice_weights_receipt.v1.json`) binds dream
  node key -> profile sha -> rendered WAV sha; WAV is ffprobe-valid nonzero
  audio.
- V3.2 CITATION CLOSURE (reliability): the certified persist layer fails
  closed on edge-endpoint closure — every edge in a write set must reference
  endpoints that are in the write set or already stored; loop runners
  materialize watch-evidence vertices via the standard
  `build_watch_evidence_vertices`. Proof: the V3.3 cycle's persisted dream
  reaches strict claim-citation resolution fraction == 1.0 (the measure that
  read 0.0 for all four pilot arms), AND a negative unit-of-the-real-layer
  probe shows persist_canonical blocks a write set with a dangling edge.
- V3.3 AUTONOMOUS CYCLE: `scripts/autonomous_dream_cycle.py` runs ONE full
  unattended cycle end-to-end: select the next unused person-anchored residue
  cluster (biographical recency + seeded hash; skip clusters already consumed
  by ACTIVE dream nodes) -> generate content-matched instruments AT SELECTION
  TIME (positive recall probes derived from the selected roots; negative
  control verified absent from root content BEFORE the dream exists) ->
  compose dream + ArcFace-gated storyboard frames (reference-image prompts)
  -> VLM observation -> phases 13/14 (unmodified gates) -> persist with V3.2
  closure -> activate -> evaluate (grounding 1.0, closed-enum distinction
  DENIED + correct class, anchors byte-unchanged) -> V3.1 voice weights from
  the NEW dream -> `autonomous_cycle_receipt.v1.json` with status
  `PASS_AUTONOMOUS_CYCLE`.

## Allowed scope

- skills/persona-dream scripts/receipts/contracts; chatterbox /synthesize
  transport; GMO store via the certified persist layer; standard image lane
  (gpt-image-2 via the established scillm path); Tau text/VLM adapters.

## Forbidden drift

- No paid provider VIDEO calls. No modification of the completed GOAL_V2
  pilot bundles or their receipts. No weakening of ArcFace 0.421, the
  phase 13/14 gates, or the certified transaction layer's reread rules.
  No human-judgment gates (per GOAL_V2_AMENDMENT_1).

## Retry/stop rule

- Two focused attempts per blocker; then a blocker report with the failed
  command, output, artifacts, hypothesis, one next action.
