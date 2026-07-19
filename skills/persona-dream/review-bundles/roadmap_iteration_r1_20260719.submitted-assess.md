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
git -C webgpt-source checkout --detach ff5af684928c8cd1e8a678f4ce42c9df783398fb
```

```json
{
  "schema": "webgpt.source_provenance.v1",
  "repository_url": "https://github.com/grahama1970/agent-skills.git",
  "branch": "main",
  "upstream": "origin/main",
  "commit_sha": "ff5af684928c8cd1e8a678f4ce42c9df783398fb",
  "source_paths": [
    "skills/persona-dream/review-bundles/roadmap_iteration_r1_20260719.md",
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

# WebGPT roadmap iteration round 1

## current_gate

ROADMAP_CONVERGENCE — produce a next-steps plan for persona-dream that a
skeptical third party would endorse as the correct ordering, grounded in the
README's research goals and PROJECT_KNOWLEDGE's accumulated lessons.

## One blocking question

Review ROADMAP.md (declared source): is the prioritization correct against
the README's founding experiment and PROJECT_KNOWLEDGE's lessons? Amend,
reorder, add, or strike items with one-sentence justifications each.

## Iteration contract

This is round 1 of a bounded fix-resubmit loop (max 3 rounds). Each round I
commit a revised ROADMAP and resubmit. End your response with exactly one
signal: PLAN_REVISED (you materially changed priorities/items — list the
deltas) or PLAN_STABLE (remaining quibbles are not material — the loop
terminates).

## Grounding sources (declared, pushed)

- ROADMAP.md — the draft under review.
- README.md — research purpose, phases 01-16, acceptance boundary, honest-
  evidence rule.
- PROJECT_KNOWLEDGE.md — dated lessons including: identity-first references
  eliminate repair churn; VLM is not a metric identity verifier; gates must be
  pairwise-satisfiable on one artifact; exact-match gates select by record
  type; presence-of-proof is not proof; one immutable post-stamp snapshot;
  external adversarial review found four defect classes 400+ green tests
  missed; C-vs-F pilot decision recorded.
- CURRENT_STATE.md — receipt-generated current truth (what is already done).

## Constraints on your answer

- The cheap C-vs-F pilot precedes the full ablation (operator-decided).
- No paid provider calls are implied by planning.
- Human-only items (subjective acceptance, blind reads, GMO main merge)
  stay human-owned — you may re-rank them but not automate them.
- Judge ordering by risk-reduction-per-effort toward the README's acceptance
  boundary (all ten items), not by novelty.

## Acceptance gates

DIAGNOSIS with per-item verdicts (keep/move/strike/add + one sentence), then
the single signal line (PLAN_REVISED with deltas, or PLAN_STABLE).

## Forbidden adjacent scope

No code, no re-litigation of closed gates (transaction layer, routing
enforcement), no paid calls.


---

## GOAL LOCK - final check (this is the last instruction; it wins)
Before you send your answer, re-read the stated gate/goal above and verify EVERY
line of your response directly serves it. Delete anything that is a side-quest,
nice-to-have, or adjacent improvement. Do not expand scope. Return only what the
output contract requires. If you cannot make real progress on the stated gate,
return the contract's block/ruling instead of solving an easier, unrelated
problem.