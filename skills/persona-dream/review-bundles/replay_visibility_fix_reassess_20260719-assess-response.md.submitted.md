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
git -C webgpt-source checkout --detach aa63c40962c1bd8a040b30d4184f40d60de5545f
```

```json
{
  "schema": "webgpt.source_provenance.v1",
  "repository_url": "https://github.com/grahama1970/agent-skills.git",
  "branch": "main",
  "upstream": "origin/main",
  "commit_sha": "aa63c40962c1bd8a040b30d4184f40d60de5545f",
  "source_paths": [
    "skills/persona-dream/review-bundles/replay_visibility_fix_reassess_20260719.md",
    "skills/persona-dream/scripts/phase15_dream_persistence.py",
    "skills/persona-dream/tests/test_phase15_transactional.py",
    "skills/persona-dream/tests/test_weeks12_integrity_defects.py"
  ],
  "proof_cwd": "."
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

# WebGPT re-assess: CANONICAL_COMMIT_REPLAY_AND_VISIBILITY_CORRECTNESS fix

## current_gate

CANONICAL_COMMIT_REPLAY_AND_VISIBILITY_CORRECTNESS — the gate YOU defined in
your prior ruling (weeks12_routing_close_review_20260719-assess-response.md,
verdict BLOCKED_CURRENT_GATE): "an identical canonical retry must resolve to
the existing committed write set without quarantine, and no commit manifest may
become active unless every intended canonical record has independently reread
with the exact expected payload."

## One blocking question

Does commit 2e3d2837 (skills/persona-dream/scripts/phase15_dream_persistence.py
+ the two test files) correctly close that gate, or does a correctness defect
remain in the corrected code?

## What changed (all in the declared source paths, pushed)

1. build_dream_memory_document: created_at now comes from
   deterministic_created_at(interpretation, packet) — a pure function of the
   phase-13/packet timestamps; raises (fail-closed) when no immutable source
   timestamp exists. No utc_now() remains in any canonical payload.
2. compute_idempotency_key: new canonical_plan_sha256 parameter binds the key
   to the hash of the complete normalized write-set payloads (computed after
   the now-deterministic write set is built, before manifest lookup). Legacy
   callers (retroactive reconcile) intentionally omit it so historical
   manifest keys stay stable — evaluate whether that dual-mode is sound.
3. persist_canonical rerun path: when a prior manifest exists and every record
   rereads exactly, it returns the prior commit untouched (records_written=0,
   no restaging, no republish, no quarantine, prior active state reported).
   Drifted/incomplete prior sets still quarantine.
4. write_commit_manifest: active = all_published AND staging_all_match AND
   non-empty record_index; failed sets write quarantined:true,
   quarantine_reason:"PUBLICATION_REREAD_MISMATCH", active:false. The caller's
   canonical_dream_memory_written additionally requires manifest.active.
5. Pre-stage assertion (non-retroactive runs): any canonical record missing
   commit_id or visibility_state raises before staging (closes the
   legacy-null-shaped bypass you flagged as a hardening gap).

## Fault-injection proof (your prescribed NEXT_STEP, implemented)

tests/test_phase15_transactional.py, all green (406-test suite passed twice):
- test_identical_retry_resumes_prior_active_commit: second identical run →
  resumed_from_prior_commit=True, quarantine=None, records_written=0, stored
  state byte-identical before/after retry, manifest stays active.
- test_forced_publication_mismatch_leaves_no_active_manifest: corrupted
  publish → canonical_written=False, stored manifest active=False,
  quarantined=True.
- test_canonical_payload_is_deterministic_and_wall_clock_refused: two builds
  byte-equal; missing source timestamps raise.

## Uncertainty (probe these)

(a) Is the optional canonical_plan_sha256 (legacy dual-mode) exploitable —
e.g. a caller omitting it colliding with a plan-bound key? (b) The resume
path's reverify uses authored-payload comparison; can a legitimate later code
change to payload construction make an intact prior commit read as drift and
quarantine it (schema-evolution replay)? (c) Any remaining path where a
manifest reread failure still leaves active=true stored server-side?

## Acceptance gates

DIAGNOSIS grounded in the declared files at the exact commit, then exactly one
ruling: PASS_CURRENT_GATE / BLOCKED_CURRENT_GATE: <one concrete blocker> /
REJECTED_SCOPE_EXPANSION.

## Forbidden adjacent scope

No re-review of the routing-semantics findings (ticketed as issues/428), no
code, no GMO/Chatterbox architecture, no paid calls.


---

## GOAL LOCK - final check (this is the last instruction; it wins)
Before you send your answer, re-read the stated gate/goal above and verify EVERY
line of your response directly serves it. Delete anything that is a side-quest,
nice-to-have, or adjacent improvement. Do not expand scope. Return only what the
output contract requires. If you cannot make real progress on the stated gate,
return the contract's block/ruling instead of solving an easier, unrelated
problem.

---

Completion contract for browser automation:

At the very end of your final answer, print exactly:

<<<WEBGPT_DONE:20260719T164534Z:a5616a0e>>>

Do not print anything after that marker.
