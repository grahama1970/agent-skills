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
git -C webgpt-source checkout --detach b9fc00d32afbc10948a5772aff706b91c21a0100
```

```json
{
  "schema": "webgpt.source_provenance.v1",
  "repository_url": "https://github.com/grahama1970/agent-skills.git",
  "branch": "main",
  "upstream": "origin/main",
  "commit_sha": "b9fc00d32afbc10948a5772aff706b91c21a0100",
  "source_paths": [
    "skills/persona-dream/contracts/pilot_post_run_measurement_amendment.v1.md",
    "skills/persona-dream/scripts/pilot_metrics.py",
    "skills/persona-dream/scripts/pilot_m5_normalize_claims.py"
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

# Round 4: confirm the post-run measurement amendment — request M5 clearance

current_gate: FREEZE_POST_RUN_MEASUREMENT_AMENDMENT_BEFORE_M5 (your round-3
gate). The single immutable amendment is frozen and executed; this round asks
you to verify it and clear the M5 blind read.

## What was frozen (contracts/pilot_post_run_measurement_amendment.v1.md, committed)

1. M2 now implements the frozen construct: per accepted claim — manifest-listed
   interpretation vertex whose payload hash is recomputed FROM THE STORE over
   the certified persist-snapshot's authored keyset (daemon indexing fields are
   outside the basis; the only permitted lifecycle change is the
   reread-verified pending->active activation) and must equal the manifest
   hash; every observation_ref grounds_interpretation edge and every
   source_memory_ref derived_from edge manifest-listed, stored, both endpoints
   stored. fraction = fully resolved claims / accepted claims.
2. M3: strict-JSON transport line added (question text unchanged); denial
   check = explicit negated-occurrence assertion (full negation-form coverage
   incl. contractions, unicode apostrophes, contrastive "rather than") with a
   per-sentence affirmation veto that ignores affirmations inside negated
   clauses.
3. M4: fail-closed type contract (edges by relationship_type are provenance;
   vertices need kind/schema; untyped records block; identity-class by
   collection+type only). Anchor byte-equality unchanged.
4. M5 redaction: deletion-only — every modality-trace match becomes the
   content-free marker "[modality detail redacted]"; spans+hashes receipted;
   the frozen leak gate remains final authority. (Verified live: your example
   phrase now becomes "The [modality detail redacted] supports reading the
   repeated woman as stable." — no fluent rewriting.)
5. N1 precommitment: the LITERAL failure is retained for R1-F. Under the
   frozen decision rule F cannot win; the confirmatory result ceiling is NULL.
   M5 is still collected. Any reading that sets N1 aside is labeled
   exploratory-only. No waiver, no replacement control.
6. Originals preserved unmodified (reports/pilot_c_vs_f/metrics_original_v1/
   including manifest v1); run manifest v2 freezes 17 files incl. the
   amendment; result receipt binds amendment + manifest v2 + lineage.

## Corrected-instrument results (uniform final rerun, receipts committed)

| run | M1 positives | N1 | M2 fraction | M3 | M4 |
|-----|--------------|----|-------------|----|----|
| R1-C | absent (top-20) | pass | 0.0 | PASS | PASS |
| R1-F | absent | FAIL (literal, precommitted) | 0.0 | PASS | PASS |
| R2-F | absent | pass | 0.0 | PASS | PASS |
| R2-C | absent | pass | 0.0 | PASS | PASS |

The M2 0.0 is a REAL, symmetric finding the corrected instrument exposed:
both arms' grounds_interpretation edges cite watch-evidence vertices that the
arm runners never persisted (watch_vertices=[] at persist). Hash-ownership
and derived_from resolution pass; the dangling observation endpoints fail
every claim in both arms identically. We report it as-is (no post-hoc
re-persist), noting it as a producer-machinery defect for any successor
protocol. M1 positive-probe absence is likewise symmetric (frozen dream-004
probes do not match the new content).

Under the frozen decision rule with these numbers the confirmatory result is
NULL regardless of M5 (N1 regression on R1-F; M2/M1 no-regression holds by
symmetry). M5 remains meaningful as the protocol's recorded blind read and
as exploratory evidence.

Ruling required: PASS_CURRENT_GATE (amendment verified; proceed to the human
M5 blind read and then the result receipt) or BLOCKED_CURRENT_GATE: <one
concrete blocker>. Do not expand scope.


---

## GOAL LOCK - final check (this is the last instruction; it wins)
Before you send your answer, re-read the stated gate/goal above and verify EVERY
line of your response directly serves it. Delete anything that is a side-quest,
nice-to-have, or adjacent improvement. Do not expand scope. Return only what the
output contract requires. If you cannot make real progress on the stated gate,
return the contract's block/ruling instead of solving an easier, unrelated
problem.