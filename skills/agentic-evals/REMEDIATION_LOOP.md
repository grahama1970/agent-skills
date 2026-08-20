# Agentic-Evals Remediation Loop (standard) — v2

Status: DESIGN (contract-first; implementation follows operator approval).
Owner: `agentic-evals` skill. Consumers: any project with an
`agentic-evals` fixture and a category-dependency map.

v2 folds in the WebGPT review of v1
(`reviews/remediation-loop-20260820/…-1fb095dd8c1f/node-artifacts/handler-webgpt/response.md`):
five blocking amendments (integrated-full-run close gate, reviewer tampering
veto, stable category identity, validated active-DAG mutation plan, and
fingerprint-based termination), the self-modification privilege boundary, and a
required `phart-dag-chart` visualization on every failing run.

## Purpose

Standardize, once and for every project, the closed loop that turns eval
failures into fixes without human ticket-shuffling:

```
run ALL evals to completion (campaign-frozen inputs)
  -> render the category DAG (phart-dag-chart) + validate acyclicity
  -> categorize the COMPLETE failure set into stable root-cause categories
  -> plan the ticket + depends-on mutations, validate the plan, apply atomically
  -> project-watchdog dispatches routable (unblocked) tickets concurrently
  -> per ticket: Tau sequential DAG fixes -> reviewer admissibility -> category-green
  -> integrate -> re-run the FULL suite on the merged head -> fresh re-categorize
  -> stop when zero categories remain, or a fingerprint blocker fires
```

Today this exists only as a memory-repo one-off
(`experiments/memory/scripts/validation/probe_failure_triage.py`: category
registry + one-ticket-per-category, idempotent on label, but no depends-on, no
loop, no visualization). This standard lifts that into the shared skill and adds
the missing pieces.

## Required visualization on failure (composes `phart-dag-chart`)

**On any run whose readiness is not `READY`, a category-DAG visualization is
MANDATORY — the loop fails closed without it.** After categorization, the loop:

1. emits the **active** category graph as ask/scillm DAG JSON — nodes = active
   failed categories, edges = `depends_on` restricted to active categories,
   each node annotated `routable` | `blocked:upstream` | `patch_candidate` |
   `category_green` | `integrated` | `closed`;
2. pipes it through `phart-dag-chart`, which **validates** the DAG (resolvable
   nodes, no self-edge, acyclicity) and **renders** the PHART ASCII chart;
3. treats a phart validation error as the amendment-4 gate firing: **no
   `ticket block` mutation may be applied** while the active DAG is invalid.

So phart-dag-chart does double duty: the operator-visible failure picture
(which categories failed, what blocks what, what is being fixed concurrently)
AND the acyclicity/plan-validity gate. The rendered chart is written to the run
directory each iteration (`category-dag.iter-N.txt`) as campaign evidence.

## Non-negotiable ordering rules

1. **Ticket only after a COMPLETE eval pass.** A defect *class* is visible only
   once every failure belonging to it has been seen (160 cases -> 7 categories
   in the memory campaign). One-ticket-per-case floods the fixer with racing
   patches for one bug. The sole exception is an **incident/abort path**: if the
   run cannot complete because of infrastructure corruption, destructive
   behavior, credential leakage, or runaway cost, abort and surface ONE
   campaign-level blocker — not a case defect ticket, and it does not weaken
   this rule.
2. **Categorize before ticketing AND before drawing depends-on edges.** Edges
   are defined over categories shown to exist in THIS run.
3. **Re-categorize from scratch every iteration.** A landed fix reshapes the
   failure surface (collapses categories, unmasks hidden ones). Consume the
   exact completed report of that iteration, never "latest report".
4. **Closure is earned by the INTEGRATED full suite, not a category-only run
   and not a reviewer's opinion** (amendment 1, below).

## The closure state machine (amendment 1)

Three facts are progressively stronger and MUST stay distinct; conflating them
is the main race and oracle-gaming risk:

```
OBSERVED -> TICKETED -> ROUTABLE/BLOCKED -> PATCH_CANDIDATE
  -> REVIEW_ADMISSIBLE -> CATEGORY_GREEN -> INTEGRATED
  -> FULL_RUN_RECONCILED -> CLOSED
```

- **CATEGORY_GREEN** = the category's close slice re-runs green. This is a *fast
  local check*, not closure. A category fix can green its own subset while
  regressing another category or gaming the category boundary.
- **INTEGRATED** = the patch has landed on the shared/merged head with other
  concurrently-closed patches.
- **FULL_RUN_RECONCILED** = a COMPLETE fixture run on the integrated head, freshly
  categorized, shows the category is **absent** from the failure set and no
  forbidden regression appeared. Only this closes the ticket, with an
  `agent_skills.ticket_closure_evidence.v1` receipt naming BOTH proof scopes
  (the full project suite AND the category slice — stated explicitly, never
  satisfied by category-scoped commands alone).

Any failure after CATEGORY_GREEN returns the category to active/reopened, or
supersedes it per fresh categorization. The outer full pass is the authoritative
convergence oracle; local category runs only buy cheap iteration.

### The category close slice

`--only-category <id>` must not naively select cases carrying one `category`
field — `supports_claims`/`seams` are many-to-many. A category's close slice is
a **conservative closure set**: its owned cases PLUS the required seam/claim
contract tests and retained regressions it touches. If a safe slice cannot be
constructed, category-local green is only a fast check and the full fixture is
the gate.

## Reviewer admissibility with tampering veto (amendment 2)

Per ticket, a **Tau sequential DAG** (`ask tau-dag --topology sequential`,
creator-reviewer loops go to Tau, never hand-simulated):

- **gpt-5.5-high** (creator, first) — diagnoses the category from clustered
  failures and writes the patch.
- **fable-5-low** (reviewer, last) — returns `VERDICT: PASS/FAIL`. PASS is a
  cheap admissibility filter, NOT correctness authority. **A reviewer FAIL has
  veto power that blocks closure even when the local eval is green**, and its
  job is specifically to catch tampering with protected surfaces.

Closure requires `review_admissible AND integrated-full-run green`. The reviewer
must FAIL any patch that modifies **protected surfaces** inside a remediation
ticket: fixture expectations, case/category ownership, category maps, readiness
logic, the runner/oracles, evidence-class requirements, proof commands, or test
exclusions. Such changes are prohibited within a remediation ticket and must
escalate to a separate eval-contract-change path.

Immutable goal is written to preserve the contract, not just to green a subset:
> "Remove the category defect WITHOUT weakening eval fixtures, oracles, category
> maps, or proof commands, and without introducing new full-suite failures. The
> integrated full-suite re-run is the arbiter."

## Stable category identity + reconcile lifecycle (amendment 3)

The GitHub label is presentation/routing metadata and can be renamed, split, or
merged. Durable identity is a separate immutable key:

```json
{
  "schema": "agentic_evals.category_map.v1",
  "repo": "grahama1970/graph-memory-operator",
  "map_version": "1",
  "categories": {
    "entity-resolution": {
      "category_id": "agentic-evals:graph-memory-operator:entity-resolution",
      "label": "eval-cat-entity-resolution",
      "defect": "control/persona/skill identifiers do not resolve to canonical nodes",
      "expected": "every in-corpus identifier resolves; only truly-absent ones unresolved",
      "supports_claims": ["memory.intent.entity_grounded"],
      "seams": ["intent.entity_extraction"],
      "depends_on": [
        {"category_id": "…", "rationale": "why the edge exists"}
      ]
    }
  }
}
```

`category_id` (namespaced, immutable) is the machine dedupe key and rides in
ticket metadata; `label` is the human tag. Reconcile lifecycle each iteration:

- **persists** — append the new full-run receipt/fingerprint to the same ticket;
  never duplicate.
- **disappears while ticket open** — do NOT auto-close on mere absence after a
  concurrent patch. Mark `candidate-resolved` / superseded-by-run; require the
  FULL_RUN_RECONCILED gate; if absence is confirmed at campaign reconciliation,
  close with evidence noting resolution may be indirect.
- **new category appears** — file it this iteration after categorization, then
  recompute the active DAG before dispatch.
- **split** — keep the old ticket as superseded/historical; create/reconcile the
  new `category_id`s; never mutate one ticket into two meanings.
- **merge** — pick one canonical surviving `category_id`; mark others
  superseded/absorbed with links; never silently repurpose identities.

Categorization is **total and unambiguous**: unclassified failure, ambiguous
classification, unknown category, registry/report version mismatch, or a
failure assigned to mutually-exclusive owners (unless multi-category ownership is
explicitly modeled) are all HARD errors — automated remediation is unsafe if any
observed failure escapes the taxonomy. Registry mappings are deterministic hints;
report-level failure-signature evidence may refine them, with ambiguity
represented explicitly, never arbitrarily assigned.

## Validated active-DAG mutation plan (amendment 4)

Before any `ticket` / `ticket block` GitHub mutation, compute the COMPLETE plan
and validate it; apply atomically/idempotently only if the whole plan is valid.
Validate the **active induced graph** and the registry:

1. every dependency target exists in the registry;
2. no self-edge;
3. DAG acyclicity (enforced by `phart-dag-chart` validation);
4. `category_id`s and dedupe keys unique;
5. edges refer only to compatible repo/project scope (v1 is **same-repo-only**);
6. active downstream/upstream tickets resolve unambiguously;
7. **wire edges only to CURRENTLY-ACTIVE categories** — never materialize a
   registry edge to a category absent from this run, or the downstream ticket is
   permanently starved behind a category with no active ticket;
8. every edge carries a `rationale`; **sparse is the default** — independence
   unless an edge is justified, because a bad edge turns conservatism into
   starvation.

Fail-hard on dependency-plan invalidity or campaign inconsistency: do not
partially file/block and then discover a cycle. Produce and validate the
reconciliation plan before mutating GitHub state.

## Termination: fingerprints, freezing, budgets (amendment 5)

**Campaign-frozen inputs.** Each iteration records: repo, base SHA, evaluated
SHA, fixture hash, `category_map` hash + `map_version`, runner version/hash,
dependency/environment lock hash, evidence class, and campaign ID.
Categorization and reconciliation consume the exact completed report for that
frozen generation.

**Two fingerprints — never one.** A single hash that folds in `evaluated SHA`
cannot recognize a semantically identical failure state across successive
integrated commits: `A,B@SHA1 -> A,B@SHA2` would not read as an exact repeat, and
`A@SHA1 -> B@SHA2 -> A@SHA3` would not read as an `A -> B -> A` cycle — defeating
the whole detector. So compute BOTH, for different jobs:

- **semantic failure-state fingerprint** = `{active category_ids, per-category
  canonical failing-case signatures, map_version}` — **SHA-free**. This is what
  oscillation and no-progress detection operate on, so repetition and period-N
  are recognized regardless of which integrated head produced them.
- **generation/provenance fingerprint** = semantic fingerprint + evaluated SHA +
  frozen-input hashes (fixture/runner/map/env lock, campaign ID). This is what
  receipts and auditability record, so every detection is traceable to an exact
  generation.

Each full run computes both and keeps transition history keyed on the SEMANTIC
fingerprint. Stop and surface a `non-convergent`/`oscillation` blocker (with the
involved tickets, commits, provenance fingerprints, and receipts) on:

- exact semantic-state repetition (`A,B -> A,B`, any SHAs);
- period-N semantic cycles (`A -> B -> A`, any SHAs);
- category/ticket reopen counts over cap;
- failure/category count not improving over K integrated attempts;
- one ticket's landed change repeatedly correlating with another category
  reappearing.

**Monotonic-progress budget** (beyond MAX iterations + per-ticket retry caps):
terminate/escalate when the same SEMANTIC fingerprint repeats, no reduction in
the failure signature across N accepted patches, dependency graph churns too
often, no routable work exists while failures remain, no integrated-head
advancement occurs for a bounded number of dispatch cycles, or eval/report
nondeterminism exceeds the multi-trial policy. These separate "hard defect" from
orchestration thrash.

**Outer wait is on campaign progress, not `all tickets closed`.** Unblock the
loop on any of: terminal ticket state, category disappearance confirmed by a
full run, an explicit standing blocker, lease timeout/stall, or retry
exhaustion. Naive `wait_for_all_closures` deadlocks when a category vanishes but
its ticket lingers or watchdog receipts stop arriving.

## Concurrency / integration hazard (amendment 1 corollary)

Independent tickets A and B dispatched from SHA S close against S+A and S+B, but
the branch becomes S+A+B — neither local proof establishes combined
correctness. Category-local verification only *qualifies a patch for
integration*; an integrated-head FULL run is mandatory before campaign
completion and before definitive closure. The standard does not assume a
specific integration model (serial shared branch, PR merge, isolated worktree),
but in every model the integrated-head full-suite proof is required.

**Stale-work guard.** Before creator execution and before applying a patch,
compare the ticket's originating campaign/run generation with current head +
failure state. If the category no longer reproduces, terminate the work item as
stale and hand it back to reconciliation — do not force a speculative fix.

## Self-modification privilege boundary

A consumer eval failure MUST NOT allow its remediation ticket to modify
`/agentic-evals`, `/ticket`, `/project-watchdog`, the category schema, or shared
Tau orchestration. One project otherwise "repairs" itself by weakening the
common infrastructure every repo depends on. Changes to shared mechanisms
require a separate upstream ticket/campaign. (Enforced by the amendment-2
reviewer veto on protected surfaces, extended to the shared machinery.)

## What the skill adds (implementation scope, post-approval)

1. `run --only-category <id>` — run a category's conservative close slice.
2. `categorize <report> --map <category_map>` — total/unambiguous assignment of
   the complete failure set to stable `category_id`s; any escape is a hard error.
3. `category-dag <report> --map <category_map>` — emit the active category graph
   as ask/scillm DAG JSON and render+validate it via `phart-dag-chart`
   (mandatory on failure; writes `category-dag.iter-N.txt`).
4. `remediate <fixture> --map <category_map> --apply` — the outer loop:
   run -> visualize+validate -> categorize -> planned atomic ticket+block ->
   await campaign progress -> integrate -> full re-run -> re-categorize;
   fingerprint/budget bounded; campaign-frozen.
5. `category_map.v1` schema + validator (stable ids, active-only edges, no
   cycles, per-edge rationale, same-repo-only).

Shared machinery lives here; each project supplies only its
`fixtures/agentic_eval.json` and its `category_map.v1`. The memory repo is the
first consumer; `probe_failure_triage.py` is retired into this once it lands.

## Boundaries / proof

- This doc is the CONTRACT. No orchestrator code is written until the operator
  approves this v2.
- `/ticket`, `/project-watchdog`, `/ask tau-dag`, `phart-dag-chart`, and
  `ticket_closure_evidence.v1` are existing, unchanged mechanisms this composes —
  it invents no parallel ticketing, dispatch, closure, or charting system.
- Open items the reviewer flagged for the implementer to pin: (1) the exact
  integration model (serial/PR/worktree); (2) the literal two proof scopes in
  `ticket_closure_evidence.v1` for a remediation close; (3) "apply atomically"
  needs a defined rollback/compensation path since GitHub has no true
  multi-operation transaction — the implementation must prove externally-atomic
  behavior or fail-safe compensation before claiming conformance; (4) taxonomy
  evolution (any `category_map` change) is itself a protected surface, so a
  split/merge/rename must PAUSE the campaign or start a new frozen generation
  through the eval-contract-change path, never mutate mid-campaign.

## Review trail

- v1 reviewed by WebGPT (`reviews/remediation-loop-20260820/…-1fb095dd8c1f`):
  architecture sound, 5 blocking amendments.
- v2 folds in all 5 + phart visualization. Re-reviewed by WebGPT
  (`reviews/remediation-loop-20260820/…-ac80ab4b9b9b`): amendments 1-4 CLOSED;
  amendment 5 reopened on a real defect (single SHA-bearing fingerprint can't
  detect cross-commit oscillation).
- v2.1 (this revision) splits the fingerprint into a SHA-free **semantic**
  fingerprint (oscillation/no-progress detection) and a SHA-bearing
  **provenance** fingerprint (receipts/audit), closing amendment 5. WebGPT's
  reported state-machine inconsistency and amendment-4 text corruption were
  verified to be browser-transport artifacts in the received copy, not defects
  in this source (single canonical state machine; amendment 4 intact).
