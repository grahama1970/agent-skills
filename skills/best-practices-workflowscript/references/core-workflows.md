# Core workflowScript router (full contract)

Modeled on `$ask`'s named modes. A project agent **calls a core mode by name**
after reading this file; it authors a new workflowScript only when no core mode
fits. Two design rules make the set flexible and modular within the runtime:

1. **The sandbox forbids shared JS imports** (no `require`, no fs in a
   workflowScript). So reuse lives in **shared child scripts** (Layer 1) that
   gate children invoke — not in shared `.js` modules.
2. **Each core mode is a thin skeleton** (Layer 2): `config-gate → preflight →
   bounded loop → gates → named terminal states`. The logic lives in Layer-1
   scripts; the `.js` just wires gates. Amend behavior by editing the **config**,
   not the JS.

## Language boundary: JS skeleton, Python/Typer work

The two layers use different languages, and this is fixed by the runtime, not by
preference:

| Layer | Language | Why |
|---|---|---|
| **L2: workflowScript** (gates, `runs.run`/`runs.all` fanout, terminal states) | **JavaScript, mandatory** | the `subagent` runtime executes a JS statement body; `runs`/`emit` are JS-only globals, and the script cannot shell out or import |
| **L1: shared child scripts** (preflight, config-gate, grade, harvest, checkers) | **Python + Typer + Loguru + uv** per `$best-practices-python` (or bash for tiny glue) | gate children have bash; these are real, unit-testable CLIs and the right home for all substantive logic |

Consequences:

- Do **not** try to make a workflowScript a Typer CLI or shell out to a Python
  orchestrator — the runtime forbids it. Keep the JS skeleton thin.
- Put every substantive, testable piece in an **L1 Python Typer script** that
  follows `$best-practices-python` (functions-first, Loguru, module docstring,
  a non-mocked sanity check). The workflow's gate child calls it by bash.
- An L1 script that becomes a **shared core component** (reused by ≥2 workflows,
  e.g. preflight or config-gate) must be Typer-structured and testable. A
  one-off campaign script may stay plain, but graduate it to Typer when it is
  promoted into the core set.

Selection is by reading the router table in `SKILL.md`. `$jev` may only screen a
2–3-way tie over enumerated modes, abstaining to the human; it is never the
authority.

---

## `preflight`

- **Use when:** any round consumes API models or web seats — run this first.
- **Config:** model-list env vars (override defaults).
- **Terminal states:** one structured availability report (no loop).
- **Call:** `bash ~/.pi/agent/workflows/model-preflight.sh --timeout 90`
- **Compose it, do not reimplement it.** This is the shared Layer-1 preflight;
  a workflow that inlines its own provider check is duplicating and must switch
  to composing this script (see the `spacetrail-learn` reference example).
- **Example + diagram:** `model-preflight.workflow.js` / `model-preflight.diagram.md`.

## `bounded-loop-gate`

- **Use when:** you have config-gated work that runs in bounded waves, is graded
  against a deterministic answer key or checker, attributes failures, and pauses
  at an orchestrator/human gate each wave.
- **Config:** `<repo>/.pi/<name>.json` — caps (`max_waves`, `seeds_per_wave`),
  win/target thresholds, gate policy, model + fallbacks, script paths. **Amend
  the run by editing this file, never the JS.**
- **Skeleton:** `gate-config → preflight (compose model-preflight.sh) → per-wave
  fanout → grade (deterministic) → attribute → orchestrator gate → next wave`.
- **Terminal states (name them all in the header):** a `*_found` success, a
  `blocked_human` orchestrator/expert gate, `iteration_cap_reached`,
  `no_provider_capacity`, and a `*_bug_found` when a systematic defect blocks
  progress.
- **Reference example + diagram:** `spacetrail-learn.workflow.js` /
  `spacetrail-learn.diagram.md` — plays a game through the `$memory` pipeline,
  grades against a corpus answer key, harvests candidates, gates to a human.

## `roundtable`

- **Use when:** N seats deliberate on an identical shared packet and you want a
  synthesized answer with attributed dissent.
- **Config:** handler list + immutable goal (required).
- **Terminal states:** consensus / degraded (usable survivors) / quorum-refused.
- **Call:** `$ask tau-dag "<task>" --dag-template roundtable --topology
  concurrent --execute --json` for browser/API seats; `$roundtable` generates a
  pi-native local-fanout script.
- **Rule:** always `--topology concurrent`, identical packet to every seat.

## `compete`

- **Use when:** you want isolated candidate solutions/designs and the
  orchestrator will judge against local evidence and **harvest/mix the best**
  (feature harvesting), not just crown one winner.
- **Config:** handlers, `--criterion`, immutable goal.
- **Terminal states:** compete scorecard + winner-continuation request.
- **Call:** `$ask compete "<isolated task>" --handler <a> --handler <b>
  --criterion <c> --execute --json`.
- **Rule:** candidates are isolated (never see each other). The criterion guides
  seats; the **project agent judges against deterministic local evidence** and
  composes the result. A model does not pick the winner.

## `clean-room`

- **Use when:** you need N isolated reviews of one bundle with no cross-talk.
- **Config:** target bundle.
- **Terminal states:** per-seat review outputs.
- **Call:** `$roundtable` (pi-native clean-room) or `$ask` review modes.

## `creator-reviewer`

- **Use when:** a build step must be gated by a reviewer verdict before it
  counts.
- **Config:** creator handler, reviewer handler, immutable goal.
- **Terminal states:** pass / fail (reviewer verdict required).
- **Call:** `$ask tau-dag "<creator task then reviewer verdict>" --dag-template
  creator-reviewer --topology sequential --execute --json`.
- **Rule:** `PASS` is reviewer evidence only; local closure still needs
  deterministic local proof.

## `immutable-goal-mvp-loop`

- **Use when:** a goal-locked implementation/debugging loop must make bounded MVP
  progress, stop thrashing, and escalate through `$brave-search` and `$ask` when
  blocked.
- **Config:** `dag_id`, `goal_id`, `goal_hash`, `immutable_goal`, `target_repo`,
  `target`.
- **Terminal states:** shipped-with-proof / escalated.
- **Call:** `$dag-templates materialize immutable-goal-mvp-loop --set ...` (see
  `dag-templates/REGISTRY.md`).

---

## Adding a new core mode

Only after the mandatory Authoring flow (interview → preflight design → write →
validate → `$create-architecture` diagram → dry-run gates). Then add a row to
the `SKILL.md` router table and a section here. A one-off workflow that will not
be reused does **not** belong in the router — keep the core set small and
legible, exactly like `$ask`'s mode list.
