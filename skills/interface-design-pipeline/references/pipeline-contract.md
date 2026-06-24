# Interface pipeline contract

## 1. Phase ownership

| Phase | Owner | Required output | Gate |
|---|---|---|---|
| Brief/recall | project agent + memory | `brief.md` | user job and rejection criteria are observable |
| Research | `github-search`, `brave-search` | raw lane receipts + normalized packet | at least one successful lane from each required source |
| Reference adjudication | `interface-researcher` | `reference-selection.json` | provenance, patterns to keep/reject, no-clone boundary |
| Mockup tournament | `interface-designer` + `interface-reviewer` + `$loop` | HTML/CSS candidates + loop receipts | deterministic checks and reviewer PASS |
| Mockup selection | `interface-adjudicator` | `adjudication.json` | identical rubric; one winner or explicit hybrid plan |
| Component inventory | `interface-researcher` | `component-inventory.json` | existing components and justified gaps are evidenced |
| Implementation tournament | designer/reviewer loops in disposable worktrees | code, checks, screenshots, interaction and reuse receipts | all hard gates pass |
| Final adjudication | `interface-adjudicator` | final `adjudication.json` | one winner/hybrid or `NEEDS_CHANGES` |
| Promotion | human | signed gate decision | no automatic merge or push |

## 2. Research evidence

Every normalized reference retains source lane, URL, title, raw response path,
license when known, and notes. The heuristic rank is only triage. The researcher
must state:

- which interaction/layout patterns are reusable;
- which product-specific chrome must not be copied;
- whether code reuse is license-compatible or visual-reference-only;
- which required user states the reference demonstrates;
- what evidence is missing.

A screenshot of a commercial product may influence spacing, hierarchy, density,
or interaction qualities. It is not a template or component source.

## 3. Mockup rubric (100 points)

- user job and first-viewport decision: 20
- hierarchy and progressive disclosure: 15
- required state coverage: 15
- interaction/keyboard/accessibility affordances: 15
- domain rules and anti-dashboard gate: 15
- feasibility with the declared component stack: 10
- visual coherence and polish: 5
- reference provenance/no-clone explanation: 5

Hard failures: missing HTML, missing required state, no keyboard focus treatment,
remote opaque dependencies, copied product chrome, invented operational truth,
reviewer edits, missing receipt, or deterministic check failure.

## 4. Implementation rubric (100 points)

- selected mockup fidelity from fresh screenshots: 20
- existing component reuse and justified gaps: 15
- React/state/component architecture: 15
- interaction semantics, qids, keyboard, and accessibility: 15
- deterministic tests and failure states: 15
- responsive behavior and inspector/drawer transitions: 10
- D3 correctness and accessibility when applicable: 5
- visual polish without token drift: 5

A D3 score is marked not-applicable when the selected interface has no data
visualization. It must not be replaced with arbitrary chart work.

## 5. Reviewer receipt

Outside `$loop`, reviewers write:

```json
{
  "schema": "interface_design_pipeline.review.v1",
  "phase": "reference_adjudication",
  "verdict": "PASS",
  "score": 91,
  "candidate_id": "optional",
  "winner": "optional",
  "hard_failures": [],
  "findings": ["..."],
  "missing_evidence": [],
  "repair_instructions": ["..."],
  "artifacts_reviewed": ["..."]
}
```

Inside `$loop`, `interface-reviewer` follows the loop adapter's strict output:

```json
{"verdict":"PASS|NEEDS_CHANGES|BLOCKED","findings":["..."]}
```

The richer evidence stays in phase artifacts; the loop harness remains the truth
source for each repair transaction.

## 6. Concurrency and isolation

- GitHub and Brave lanes run concurrently with independent raw receipts.
- Mockup competitors run concurrently; attempts inside one candidate are serial.
- Implementation competitors run concurrently only in separate disposable
  worktrees. Attempts inside one worktree are serial.
- Reviewers and adjudicators are read-only.
- No candidate reads another candidate's draft before the adjudication phase.

## 7. Promotion decisions

The human gate supports only:

- `PROMOTE_WINNER`
- `PROMOTE_HYBRID` with an explicit merge plan and a new validation round
- `RETURN_TO_MOCKUPS`
- `RETURN_TO_IMPLEMENTATION`
- `REJECT_ALL`

A recommendation is not promotion. A PASS does not imply merge, push, deploy, or
approval unless that action has a separate receipt.
