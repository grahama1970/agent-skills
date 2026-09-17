---
name: best-practices-workflowscript
description: >
  Authoring standard for pi-subagents workflowScripts: portable syntax, provider
  preflight, bounded loops with explicit terminal states, one-writer mutation,
  independent review gates, and honest failure reporting. Use when writing,
  reviewing, or standardizing any workflowScript or workflowScriptPath file, when
  a workflow needs an interview before authoring, or when adding a shared
  preflight or visual explainer to a workflow.
triggers:
  - workflowscript
  - workflow script
  - pi-subagents workflow
  - runs.run
  - workflowScriptPath
  - orchestration script
allowed-tools: Bash, Read, Edit, Write
metadata:
  short-description: Standard for robust pi-subagents workflowScripts
provides:
  - best-practices-workflowscript
composes:
  - pi-subagents
  - best-practices-skills
  - interview
  - create-architecture
  - agentic-evals
complies:
  - best-practices-skills
taxonomy:
  - validation
  - composition
disciplines:
  - agentic-orchestration
  - developer-tooling
---

# best-practices-workflowscript

A workflowScript is a long-lived operational asset, not a throwaway prompt. This
skill is the authoring standard so every workflowScript in the ecosystem is
robust, reliable, and consistent. It extends — does not duplicate — the
pi-subagents skill's own references (`skills/pi-subagents/references/*.md`,
especially `constraints-and-recipes.md`). When the two disagree, pi-subagents'
runtime constraints win; file an issue here.

## Core workflowScript router (call before you author)

Like `$ask`'s named modes (one-shot, roundtable, compete, clean-room,
creator-reviewer), the ecosystem has a small set of **named, config-driven core
workflowScripts**. A project agent selects one by **reading this table** — the
same way it reads `$ask`'s Mode Router — not by asking a model.

**Read this table first. If a core mode covers the need, call it — do not author
a new workflowScript.** Author a new one (through the mandatory Authoring flow
below) ONLY when no core mode fits, then add its row here. This is the
anti-bespoke / anti-duplication front door.

| Mode | Use when | Config (amend here, not the JS) | Terminal states | Call |
|---|---|---|---|---|
| `preflight` | check model/seat availability before a round | model-list env vars | one availability report | `bash ~/.pi/agent/workflows/model-preflight.sh --timeout 90` |
| `bounded-loop-gate` | config-gated work → grade → orchestrator gate, over bounded waves | `<repo>/.pi/<name>.json` | `*_found` / `blocked_human` / `iteration_cap_reached` / `*_bug_found` | reference example: `spacetrail-learn.workflow.js` |
| `roundtable` | N seats, identical shared packet, converge to synthesis | handlers + immutable goal | consensus / degraded | `$ask tau-dag "<task>" --dag-template roundtable --topology concurrent` (or `$roundtable` for pi-native) |
| `compete` | isolated candidates; orchestrator harvests/mixes the best | handlers, criterion, immutable goal | scorecard + winner | `$ask compete "<task>" --handler <a> --handler <b> --criterion <c>` |
| `clean-room` | isolated review bundle, seats never see each other | target bundle | per-seat review | `$roundtable` (pi-native) or `$ask` |
| `creator-reviewer` | sequential build → reviewer verdict gate | creator, reviewer, immutable goal | pass / fail | `$ask tau-dag "<task>" --dag-template creator-reviewer --topology sequential` |
| `immutable-goal-mvp-loop` | goal-locked bounded MVP with anti-thrash escalation | goal_id, goal_hash, target | shipped / escalated | `$dag-templates materialize immutable-goal-mvp-loop ...` |

Full per-mode contract (inputs, gates, canonical example + diagram, how to amend
by config): `references/core-workflows.md`.

**Selection is by reading the table** (deterministic, human-legible). If two
modes plausibly fit, that is the ONLY place a bounded `$jev` shortlist screen may
assist — over the enumerated candidates, abstaining to the human below
threshold. `$jev` never authors, amends, or is the selection authority; the
workflow running to its terminal state is the proof of a correct pick.

## Authoring flow (mandatory order)

1. **Interview first.** A new workflowScript requires an `$interview` pass
   before any code. Minimum answers (see `references/interview.md` for the full
   template): goal, terminal states, iteration/cap policy, models + fallbacks +
   web seats, mutation surface (which repo paths may change), failure policy,
   who/what owns landing and closure.
2. **Preflight design.** If the workflow consumes models or web seats, its first
   child runs the shared preflight:
   `bash /home/graham/.pi/agent/workflows/model-preflight.sh --timeout 90`.
   Degrade on dead providers (skip seats, reassign roles from survivors,
   disclose substitutions); never launch a round onto exhausted providers.
3. **Write the script** against the portable core below.
4. **Validate before launch**: `subagent({ action: "validate", workflowScriptPath })`
   AND `run.sh validate <file>` (this skill's linter).
5. **Visual explainer.** Every workflowScript ships with a diagram of its
   lanes/gates/terminal states produced through `$create-architecture` (contract
   in `references/visual-explainer.md`). The diagram is reviewed with the human
   at the interview, not after the first failure.
6. **Dry-run the gates.** First live launch should exercise the gate children
   read-only before any mutation lane runs.

## The portable core (hard rules)

Syntax the runtime rejects or that breaks portability across Node/Bun:

- **No nested `async function`, arrow functions, or method helpers.** Top-level
  `await`, plain `function name(){}` helpers that return `runs.run(...)`, `for`
  loops, and explicit `Promise` chains only.
- **No filesystem, shell, or host globals in the script.** Children have bash;
  the script does not. Config is read by a gate child from a repo file
  (convention: `<repo>/.pi/<workflow>.json`), never by the script itself.
- **Validate the exact text you will launch.** `action: "validate"` on the real
  `workflowScriptPath`/`workflowScript`; a script that validated in your head is
  not validated.
- **No repo-wide pathspecs, no `git add -A`, no stash/reset/branch switching in
  children.** Landing goes through `$gh-land` with explicit paths only.

## Code conventions (enforced by the linter)

Every workflowScript is self-contained: a reader of the file alone knows what
it does, how to launch it, what its terminal states mean, and where its
diagram lives. The header block is REQUIRED and linted:

```js
// <One-line purpose.>
// Config: <repo>/.pi/<name>.json (max_iterations, mode, focus, readiness_command).
// Terminal states: ready_to_share | blocked_human | iteration_cap_reached | no_provider_capacity.
// Diagram: <name>.diagram.md ($create-architecture) — lanes, gates, terminal states.
// Launch: subagent({ workflowScriptPath: '/home/graham/.pi/agent/workflows/<name>.workflow.js',
//                    cwd: <repo>, async: true, globalConcurrencyLimit: 1 })
```

Body conventions (reviewed, not linted):

- Structure order: schemas/constants → method notes → gates → loops → audit → return.
- Run keys `'<verb>-<target>'` (`gate-1`, `review-320-0`, `close-362`); schema
  constants `<noun>Schema`; shared strings defined once.
- No magic literals repeated; every terminal state named in the header appears
  verbatim in the code.
- Comments explain WHY (the failure a rule prevents), never narrate the code.
- Build multi-line child `task:` strings with template literals (backticks) and
  `${...}` interpolation, not `+` concatenation. Concatenated prompts are hard to
  edit and silently drop the space between fragments (`'...contract ' +` must
  hand-place the trailing space; a missed one corrupts the prompt). Template
  literals are portable and runtime-accepted — the portable-core ban on nested
  `async`/arrow/method helpers does not apply to them.

## Robustness rules (field-proven)

Each rule below was paid for by a real failure; do not relax them silently.

1. **Pin the repo.** Children must be told the exact `owner/name` and warned
   against lookalike repos (a scout twice queried `alejandro-ao/tau` →
   `huggingface/tau`, a different project, and returned confident nonsense).
2. **Compare against `origin/main`, never local HEAD.** Plumbing landing leaves
   local HEAD stale by design. Every review/publish child carries the CRIT note:
   use `git show/ls-tree/diff origin/main:PATH` + `merge-base --is-ancestor`.
3. **Untracked candidates are candidates.** A reviewer that only searches git
   objects will report "no candidate exists" while the work sits untracked in
   the working tree. Gate children check `git status --porcelain` first.
4. **Chunk every command.** Children wrap each command in `timeout 300`;
   set `toolTimeoutMs` on review children and keep per-run `timeoutMs` +
   `toolBudget: {hard: N}` bounded so a single stall cannot burn the run.
5. **Serial mutation, parallel reading.** `globalConcurrencyLimit: 1` for any
   workflow with writers; parallelize only read-only review/scout lanes.
6. **One writer per checkout; preserve unrelated dirty bytes.** No worktrees
   unless the workflow exists to isolate them.
7. **Structured verdicts, fail-closed.** Every gate/review child gets an
   `outputSchema` with a closed `verdict` enum; the script branches only on
   `structuredOutput`. Missing/invalid output is a blocker, never a default.
8. **Independent review before landing and again before closure.** Reviewer
   model family differs from the worker's where provider capacity allows;
   provider substitutions are disclosed in the run report, never silent.
9. **Per-item `try/catch`.** One ticket's infrastructure failure records
   `infrastructure_failure` and moves on; it never aborts the remaining queue.
10. **Bounded loops with explicit terminal states.** Iterating workflows state
    their cap source (config file), clamp it, and terminate only on named
    states — e.g. `ready_to_share`, `blocked_human` (with exact one-line human
    actions), `iteration_cap_reached`, `no_provider_capacity`. Never exit on an
    unlabeled condition.
11. **Honest terminal reporting.** No fabricated settlement, no closure without
    deterministic proof, no bypass of guarded lifecycle commands
    (`$ticket` close, worktree audits). `PASS` from a reviewer is evidence, not
    authority.
12. **Shared assets over copies.** Provider preflight, lifecycle templates, and
    method notes live in one shared file each (`~/.pi/agent/workflows/`) and are
    invoked by path; duplicating them per-workflow creates drift.

## Naming and layout

```text
~/.pi/agent/workflows/<name>.workflow.js      # the script (validated)
~/.pi/agent/workflows/<name>.diagram.md       # $create-architecture explainer
<repo>/.pi/<name>.json                        # per-repo config (caps, focus, readiness)
```

## Ecosystem

Consumes `$pi-subagents` (runtime contracts), `$interview` (authoring
requirements), `$create-architecture` (visual explainer), `$gh-land` +
`$ticket` (landing/closure inside workflows). Produces standardized
workflowScripts and the shared `model-preflight.sh` contract. Validate a skill
change with `skills/best-practices-skills/scripts/validate_skill.py`; validate a
workflowScript with this skill's linter plus `subagent action: "validate"`.

## References

- `references/core-workflows.md` — the Core workflowScript router in full: each
  named mode's inputs, gates, terminal states, canonical example + diagram, and
  how to amend it by config instead of editing the JS. Read this to CALL a core
  mode; read the Authoring flow only when none fits.
- `references/patterns.md` — annotated canonical patterns (gate/prepare/process
  loop, lifecycle lane, preflight wiring) and the failure each rule prevents.
- `references/interview.md` — the mandatory pre-authoring interview template.
- `references/visual-explainer.md` — the `$create-architecture` diagram contract.
- `scripts/validate-workflowscript.sh` — anti-pattern linter (run before every
  launch).
