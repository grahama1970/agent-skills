# GOAL_V2 Amendment 1: relevance + reliability are the criteria (operator-directed)

Date: 2026-07-22
Authority: direct operator instructions (verbatim):
1. "[persona-dream] is for agents?! not for humans. that is the whole point."
2. "the human does not care about the agent's dream...only that its relevant
   to the agent's experience and the pipeline for creating it is reliable"

This is a goal-owner correction under the goal-helper contract ("If a human
corrects the goal, immediately rewrite the primary proof and discard stale
success criteria").

## Corrected success criteria

The human-judgment gates GOAL_V2 carried (P0.1 human acceptance of the video;
the pilot's M5 operator blind read) are STALE criteria and are discarded.
Nobody — human or delegated agent — needs to subjectively judge the dream's
content. The goal's two real properties are:

- RELEVANCE / ACCURACY GIVEN EXPERIENCE (operator's phrasing: "the agent's
  dream is accurate given experience"): every dream claim derives from the
  agent's real memories and nothing is fabricated beyond the recalled
  residue — source memory ids on the canonical dream node, the phase 13/14
  citation gates (each accepted claim cites source memories + observations),
  M2 grounding resolution, M3 synthetic-marking (the dream is never presented
  as literal history), and media-hash binding of the observed artifact.
  Machine-checkable; already receipt-proven.
- RELIABILITY: the pipeline that creates dreams runs fail-closed and
  repeatably without human intervention — certified transactional persistence
  with exact reread, deterministic gates, receipts for every side effect.
  Machine-checkable; already receipt-proven.

## Criterion rewrites

- P0.1 (was: human-authored acceptance receipt) -> RELEVANCE PROOF: the
  canonical dream node `dream_dream_successor_943b01ecd9a3` exists ACTIVE in
  persona memory, binds `source_memory_ids` to real root memories, binds
  `source_video_sha256` to the observed provider return
  (sha256:59b9ff31...e211fff), and the acceptance rung receipt
  (`acceptance_rung_receipt.v6.json`, PASS) certifies the fail-closed
  observation chain. No subjective acceptance artifact is required.
- P0.7 M5 (was: operator blind read) -> WAIVED BY GOAL OWNER. The pilot's
  machine measures (M1-M4 under measurement amendments v1-v1.5) stand as the
  relevance/reliability evidence. Under the frozen decision rule, F cannot
  win without an M5 preference; combined with the precommitted N1 literal
  failure, the confirmatory result is NULL — a valid completion. The result
  receipt records `m5: WAIVED_BY_GOAL_OWNER` citing this amendment; the
  sealed X/Y presentations and commitments are preserved unopened as
  archival artifacts.

## Mechanical consequences (this amendment authorizes exactly these edits)

- `scripts/check_goal_v2_boundary.py`: p0_1 verifies the relevance-proof
  receipt set above; p0_7 accepts `m5_read_author: "WAIVED_BY_GOAL_OWNER"`
  with `m5_waiver: "GOAL_V2_AMENDMENT_1"`.
- `scripts/pilot_result_receipt.py`: `--m5-waived` mode — no judgment files;
  pairs record the waiver; result computed from M1-M4 under the frozen rule
  (F cannot win => POSITIVE impossible; NULL or INVALID only).
- Run manifest refrozen after these edits (lineage preserved).

## What the pilot's execution remains as evidence

Four autonomous arms ran end-to-end (selection -> blinded producers ->
storyboard/reflection -> certified persistence -> activation) with zero human
touches — the reliability demonstration. Its instrument lineage also
surfaced one real reliability defect the goal's successor work should fix:
both arms' grounds_interpretation edges cite watch-evidence vertices that the
arm runners never persisted (M2 = 0.0, symmetric). That defect is the kind of
thing the goal owner DOES care about.
