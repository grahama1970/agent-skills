## GOAL LOCK - read first, obey throughout
Work on ONLY the single current gate / goal stated in this request. You are
FORBIDDEN from drifting into easier, adjacent, or tangential work - no unrelated
refactors, renames, new tooling, extra features, unrequested tests, or broader
architecture - none of which close the stated gate. If the stated gate is
unclear, out of scope, or blocked, say so and stop; do NOT substitute a
different, easier problem to look productive.

## Authoritative source provenance
Use the pushed repository state below as the only source of truth. Clone it and check out the exact detached commit before inspecting the declared paths.

```bash
git clone --filter=blob:none https://github.com/grahama1970/agent-skills.git webgpt-source
git -C webgpt-source checkout --detach f9ede98d95dd10f264053d1a00ead3e368f91a1f
```

```json
{
  "schema": "webgpt.source_provenance.v1",
  "repository_url": "https://github.com/grahama1970/agent-skills.git",
  "branch": "battle-adaptive-lineage-goal",
  "upstream": "origin/battle-adaptive-lineage-goal",
  "commit_sha": "f9ede98d95dd10f264053d1a00ead3e368f91a1f",
  "source_paths": [
    "skills/watch/scripts/track_yolo_bytetrack.py",
    "skills/watch/scripts/run_realtime_identity_memory_loop.py",
    "skills/watch/scripts/storage.py",
    "skills/watch/docs/architecture/watch_realtime_character_tracking_contract.md"
  ],
  "proof_cwd": "skills/webgpt"
}
```

## Research directive
Before answering, use your own web search to research current, authoritative
sources for this problem, and cite the source URLs you relied on. The bundle may
also include a "## Research context" section the project agent gathered via
brave-search; treat it as a starting point, not a limit.

## Output contract: ASSESS
Diagnose where the project agent is blocked or spiraling. Do NOT write code.
Return, in order:
- DIAGNOSIS: <root cause of the block or spiral>
- EVIDENCE: <what in the bundle/research supports it>
- CURRENT_GATE: <the one gate that must be closed next>
- NEXT_STEP: <single concrete action>
End with exactly one ruling line:
PASS_CURRENT_GATE | BLOCKED_CURRENT_GATE: <one concrete blocker> | REJECTED_SCOPE_EXPANSION

---

# Watch Skill — Streaming-Readiness Assessment (Round 2 of 3)

current_gate: P0_SLICE_VALIDATION — your Round 1 ruling (same conversation)
was BLOCKED_CURRENT_GATE on SOURCE_SESSION_PROVENANCE_REPLAY_P0, with this
next step: modify `skills/watch/scripts/track_yolo_bytetrack.py` and
`skills/watch/scripts/run_realtime_identity_memory_loop.py`, add
`skills/watch/tests/test_watch_source_session_replay.py`; append-only event
journal (session id, sequence, source hash, source PTS/frame offset, window
bounds, frame/crop hash); kill/restart; replay must yield identical
observation IDs; one injected PTS/window mismatch must be rejected before any
Memory or Qdrant write.

This round rules on whether that P0 slice is right-sized and correctly
sequenced against the project's other outstanding debt. Do NOT produce code
or a full task plan. DIAGNOSIS + one ruling.

stop condition: DIAGNOSIS + classification table + one ruling.
forbidden adjacent scope: RTSP/drone implementation detail, UI redesign,
memory schema redesign, Orpheus.

## Questions to answer inside the DIAGNOSIS

1. Right-sizing: is the P0 slice above achievable as ONE bounded slice, or
   does it hide multiple gates (journal format vs replay determinism vs
   mismatch rejection)? If it must split, name the smallest first cut.
2. Journal placement: should the journal be written by the tracker adapter
   (`track_yolo_bytetrack.py`), by the persistence loop
   (`run_realtime_identity_memory_loop.py`), or as a separate module both
   compose? Watch's contract says frames/clips/etc. are immutable and
   corrections are overlays/cases — does the journal count as source evidence
   (immutable) or derived observation (correctable)?
3. Observation ID determinism: the persistence loop currently derives point
   ids/keys from overlay ids (uuid5 namespace). What must the ID be derived
   from so restart replay is provably identical (and collides on divergence)?
4. Sequencing of outstanding non-streaming debt — classify each as
   PREREQUISITE (blocks P0), PARALLEL (independent), or DEFERRED:
   a. Row-7 human Marcus keyframes need timestamp re-anchoring (case-flagged).
   b. Rows ingested before the stale-clip cache fix are suspect until re-run.
   c. Qdrant crop collection contains codex-live-* smoke-test debris; tests
      write to the live collection.
   d. Durable Memory/Qdrant outbox/retry hardening (not started).
   e. Live-browser handoff-stop breadth (only one Qdrant-conflict browser
      proof; broad coverage is receipt/projection level).
   f. ux-lab still lazy-imports its legacy Watch UI copy.
5. The live proof for P0: is "kill -9 mid-run, restart, byte-identical
   observation set, injected mismatch rejected pre-write" sufficient, or must
   the proof also include a UI consumption receipt (contract requires live
   overlay consumption eventually — is that THIS gate or the next)?

## Required deliverable

DIAGNOSIS covering the five questions, a classification table for 4a-4f,
then exactly one ruling for the P0 slice definition:
PASS_CURRENT_GATE (slice is right-sized; proceed),
BLOCKED_CURRENT_GATE: <what must change in the slice definition>, or
REJECTED_SCOPE_EXPANSION.


---

## GOAL LOCK - final check (this is the last instruction; it wins)
Before you send your answer, re-read the stated gate/goal above and verify EVERY
line of your response directly serves it. Delete anything that is a side-quest,
nice-to-have, or adjacent improvement. Do not expand scope. Return only what the
output contract requires. If you cannot make real progress on the stated gate,
return the contract's block/ruling instead of solving an easier, unrelated
problem.