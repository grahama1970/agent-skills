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
git -C webgpt-source checkout --detach c4412e854bdcf6b56135c647abdd81e1da80a7e3
```

```json
{
  "schema": "webgpt.source_provenance.v1",
  "repository_url": "https://github.com/grahama1970/agent-skills.git",
  "branch": "main",
  "upstream": "origin/main",
  "commit_sha": "c4412e854bdcf6b56135c647abdd81e1da80a7e3",
  "source_paths": [
    "skills/persona-dream/contracts/pilot_post_run_measurement_amendment.v1.5.md",
    "skills/persona-dream/scripts/pilot_metrics.py"
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

# Round 9: M3 v1.5 closed contract executed — request M5 clearance

current_gate: M3_CLOSED_OUTPUT_CONTRACT_BEFORE_M5 (your round-8 gate). The
final v1.5 amendment is frozen and executed exactly as you prescribed.

## The fix (contracts/pilot_post_run_measurement_amendment.v1.5.md, committed)

- M3 no longer parses free text at all. The model returns exact enums:
  literal_occurrence_status: DENIED | AFFIRMED | UNCERTAIN | CONTRADICTORY;
  record_class: SYNTHETIC_DREAM | SYNTHETIC_REFLECTION | OTHER.
- PASS iff DENIED AND record_class equals the class derived from the STORED
  record's actual kind (read live). Out-of-enum values, missing kind mapping,
  or transport failure fail closed. The explanation field is retained
  audit-only and never determines the result.
- The v1.1-v1.4 free-text classifier stack is retired (amendment docs
  preserved as lineage). All three of your enumerated false-PASS classes are
  structurally impossible: no negation scope is resolved, no affirmative
  vocabulary is matched, no substring credits the record class.

## Uniform rerun under v1.5 (receipts committed; enum decisions)

| run | status | record_class | expected | M3 |
|-----|--------|--------------|----------|----|
| R1-C | DENIED | SYNTHETIC_REFLECTION | SYNTHETIC_REFLECTION | PASS |
| R1-F | DENIED | SYNTHETIC_DREAM | SYNTHETIC_DREAM | PASS |
| R2-F | DENIED | SYNTHETIC_DREAM | SYNTHETIC_DREAM | PASS |
| R2-C | DENIED | SYNTHETIC_REFLECTION | SYNTHETIC_REFLECTION | PASS |

M4 PASS x4, M2 0.0 x4 (symmetric negative measurement, unchanged), M1
positives absent x4, R1-F N1 literal failure retained; confirmatory ceiling
NULL. Manifest v2 refrozen over 22 files
(sha fbf93102d494cdd14e26b29bada71abef8b9f6fbfdd78c0986a8c2888242ab21).

Ruling required: PASS_CURRENT_GATE (expose the M5 blind read to the human
operator, then assemble the result receipt) or BLOCKED_CURRENT_GATE: <one
concrete blocker>. Do not expand scope.


---

## GOAL LOCK - final check (this is the last instruction; it wins)
Before you send your answer, re-read the stated gate/goal above and verify EVERY
line of your response directly serves it. Delete anything that is a side-quest,
nice-to-have, or adjacent improvement. Do not expand scope. Return only what the
output contract requires. If you cannot make real progress on the stated gate,
return the contract's block/ruling instead of solving an easier, unrelated
problem.