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
