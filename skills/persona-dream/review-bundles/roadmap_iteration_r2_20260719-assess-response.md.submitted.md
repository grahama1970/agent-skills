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
git -C webgpt-source checkout --detach 224d3c1c530af670ae5fa23bd30a7f7b9f89181b
```

```json
{
  "schema": "webgpt.source_provenance.v1",
  "repository_url": "https://github.com/grahama1970/agent-skills.git",
  "branch": "main",
  "upstream": "origin/main",
  "commit_sha": "224d3c1c530af670ae5fa23bd30a7f7b9f89181b",
  "source_paths": [
    "skills/persona-dream/review-bundles/roadmap_iteration_r2_20260719.md",
    "skills/persona-dream/ROADMAP.md",
    "skills/persona-dream/README.md",
    "skills/persona-dream/PROJECT_KNOWLEDGE.md",
    "skills/persona-dream/CURRENT_STATE.md"
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

# WebGPT roadmap iteration round 2

## current_gate

ROADMAP_R2_VALIDITY_FIRST_ORDERING — your round-1 gate: authority coherence,
measurement validity, v2-derived cognition, and the final unproven acceptance
item ahead of the confirmatory pilot; public reproducible execution ahead of
repeatability.

## One blocking question

ROADMAP.md r2 (declared source) applies your full round-1 revision. Does it
satisfy the gate? End with PLAN_REVISED (list deltas) or PLAN_STABLE.

## What changed since round 1 (all pushed)

1. ROADMAP rewritten to your exact P0/P1/P2 ordering: human acceptance first
   (hash-bound to the exact active return, parallel-capable); active-authority
   convergence second; routing semantics, GMO deployment pin, v2-derived
   13-16 rerun, and the voice lane all BEFORE the pilot; pilot last in P0.
   P1: temporal identity, clean-room envelope, dream CLI, GMO commit-lifecycle
   endpoints, second same-persona run with the immutable intervention ledger
   (serial path, concurrency struck), then second persona. P2: multimodal
   Watch points, conditional ablation, parked optimizations.
2. The authority contradiction you found is fixed: the CURRENT_STATE
   generator's pilot-protocol authority now points at protocol v2
   (v1 superseded pre-run); CURRENT_STATE regenerated and drift-check green.
   (Full lineage convergence — one non-superseded chain — remains roadmap
   item P0.2, as you prescribed, since it requires the 13-16 rerun.)

## Grounding sources (declared, pushed)

ROADMAP.md, README.md, PROJECT_KNOWLEDGE.md, CURRENT_STATE.md.

## Constraints (unchanged)

Cheap pilot precedes full ablation; no paid calls implied; human-owned items
stay human-owned; ordering judged by risk-reduction-per-effort toward the
README's ten-item acceptance boundary.

## Acceptance gates

DIAGNOSIS with per-item verdicts on r2, then exactly one signal line:
PLAN_REVISED (with deltas) or PLAN_STABLE.

## Forbidden adjacent scope

No code, no re-litigation of closed gates, no paid calls.


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

<<<WEBGPT_DONE:20260719T195924Z:fcbf9e13>>>

Do not print anything after that marker.
