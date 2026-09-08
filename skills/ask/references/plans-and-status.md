# Ask: Edited Native Plans And Run Status Projection

Read before using `team-plan` with a plan file, or `status --run <dir> --projection`.

## Edited native plans: current CLI boundary

`team-plan` also accepts an edited `ask.project_plan.v1` file. The positional
request must exactly match its `goal`; execution never silently substitutes a
new goal from the file.

```bash
./run.sh team-plan "The exact goal in plan.json" --plan-file plan.json --out /absolute/output
./run.sh team-plan "The exact goal in plan.json" --plan-file plan.json --out /absolute/output --execute --live --watch
```

The complete proposal (target, deliverables, team, execution, workstreams, and
unresolved fields) passes strict Pydantic validation before routing or writing
artifacts. Invalid input returns `INVALID_PLAN` with machine-readable
`validation_errors` (`type`, `loc`, `ctx`), not an interview request. A genuinely
unresolved, well-typed proposal remains interview input and cannot compile.
For file-reading work, declare `allowed_tools` explicitly (currently `read`, `ls`, `grep`, `find`
through Tau's native CLI), `allowed_paths`, and `cwd` or `target.workspace`.
A scoped workstream that requires tool-effect evidence but declares no tools is
refused before execution. Paths alone do not grant tools. Native write/edit/bash
are not provided by this path; a backend role or successful text turn is not
proof of source authoring.

The compiler emits `tau.agent_requirement.v1`, a canonical generic-DAG goal,
and explicit tool/cwd/budget fields. `independent_reviewer` requests the native
profile capability role `review`. Presets are proposals; Tau's live profile
selection decides eligibility and may reject an incompatible preset. No silent
profile fallback is requested.

Production `run_plan_spec` submits the frozen spec through `tau run`; execution
and the viewer use Tau's own interpreter, not imports into Ask's Python runtime.
It no longer substitutes a tool-less executor. Injected executors remain for explicit
SDK tests, not CLI proof. Native `run-receipt.json`, SQLite tool events, and
`execution-summary.json` are retained. `--watch` serves Tau's own read-only
viewer during the run; its state API and the native current-state file provide
progress. Open an existing native run with Tau's viewer after execution.

Retained slice proof: `fixtures/agentic_eval_native_plan_cli.json`. It proves
read-only native execution, not all #1220 routes, source authoring, a classifier
stage, or watchdog canary closure.

## One Status Shape For Every Run

```bash
cd skills/ask
./run.sh status --run <run-dir> --projection          # human readable
./run.sh status --run <run-dir> --projection --json   # ask.run_projection.v1
```

One normalized read model over the run's own artifacts, so a roundtable, a
compete run, a browser lane and a scillm-only DAG all answer "what happened?"
the same way.

**Absence is reported, never dropped.** Every node in the frozen DAG appears
even when it produced nothing — that node is the failure worth seeing, not a
row to omit. Across the current 1695-run corpus the projection surfaces 1290
nodes that never created a worker directory and 37 that left output behind
with no receipt; all of them would otherwise be invisible.

Node `stage` is a ladder, not a boolean, because each rung names a different
real failure:

| stage | meaning |
| --- | --- |
| `COMPILED` | in the DAG, nothing else observed |
| `DISPATCHED` | a worker directory exists |
| `ACKNOWLEDGED` | terminal receipt, but not `ok` |
| `CANDIDATE` | output exists that nothing admitted as evidence |
| `SETTLED` | terminal receipt with admitted evidence |

A provider response, pane text, or a zero exit code is never completion
authority on its own: `CANDIDATE` exists precisely so an unadmitted answer
cannot read as success. Generation is read-only and deterministic, so it is
safe on a live run or in a watch loop.

Not yet unified: the legacy `status --run` path reads a different artifact
family and still has its own shape.

