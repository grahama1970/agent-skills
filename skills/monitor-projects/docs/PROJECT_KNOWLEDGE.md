# monitor-projects — project knowledge

**As of 2026-08-11.** Current state, not proof.

## Purpose

Nightly cron review of **the skills amended during the day** via a five-seat concurrent
roundtable (`webgpt`, `webclaude`, `webkimi`, `webgrok`, `webgemini`), with the attributed
synthesis stored in `/memory` so the human and the project agent can recall and discuss it.

The unit of review is the **skill directory** (`skills/<name>/`), never agent-skills as one
project — agent-skills is a collection of skills. Distinct from `/monitor-skills` (drift
sync and gap scan) and `/monitor-skill-health` (best-practice violations): those answer
*"is the catalog consistent?"*; this one asks *"is what changed today any good, and what
should we do about it tomorrow?"*

## Current state

| Item | State |
| --- | --- |
| Cron `monitor-projects-nightly` (`30 2 * * *`, enabled) | **REGISTERED BUT HAS NEVER RUN** — see Blocker 1 |
| Live `--execute` roundtable (5 browser seats) | `NOT_ESTABLISHED` — never executed end to end |
| `/memory` read-back of a real roundtable receipt | `NOT_ESTABLISHED` — no live receipt exists |
| `sanity.sh` | PASS — positive, negative, noise, packet-shape, safety gates |
| `nightly --dry-run` | PASS — receipt `reports/monitor-projects/20260807T115114Z/` (9 skills discovered, 362-line packet) |
| `/ask tau-dag` compile of the real packet | PASS — `ask.tau_dag_cli_result.v1`, `status: READY`, `topology: concurrent`, all 5 handlers |
| `project-taxonomy ci` wired into the packet | Wired; `ci` green as of 2026-08-09 |
| Overall readiness | **`NOT_READY`** — the skill has never done its job once |

## Blockers

### 1. The cron cannot fire (verified root cause, 2026-08-11)

The scheduler daemon started **04:15:29** on 2026-08-07; the job was registered
**07:54:20** the same day, 3.5 hours later. The daemon loads its job table at startup and
has **no `reload` command** — only `stop`/`start`. The job is therefore present in
`~/.pi/scheduler/jobs.json` (enabled, valid `cron`) but **absent from the daemon's live
schedule**: `episodic-archiver`, sharing the same `30 2 * * *` slot, is listed in upcoming
runs and monitor-projects is not. Four nights passed with zero executions and no error,
because a job the daemon never loaded cannot fail.

This is a **scheduler-wide defect, not a monitor-projects defect**: any job registered
after daemon start is silently inert. Two other jobs have never run, but both are
explicitly disabled — monitor-projects is the only enabled one that is invisible.

Fix requires restarting the daemon (26 jobs). Not taken unilaterally; awaiting operator
decision. Verify afterwards by confirming the job appears in `scheduler status` upcoming
runs — **not** by re-reading `jobs.json`, which already looks correct and is what made
this invisible for four days.

### 2. Eval signal is a near-tautology

Catalog-wide, **273 of 359** `agentic_eval.json` cases are `bash ../sanity.sh`. So a sweep
that feeds this roundtable would report skills as healthy on the strength of re-running
their own sanity script. Do not let roundtable packets present that as independent
evidence.

### 3. `ops-workstation` context source is broken

`skills/ops-workstation/run.sh` exits 1 with no arguments. The packet records it as
`NOT_ESTABLISHED` rather than omitting it, which is correct behaviour — but the host-health
context is missing from every packet until that skill is fixed.

## Design rules that must not regress

- **Equal context.** One shared packet, byte-identical for all five seats, concurrent
  topology. Never give a seat extra context because its transport is easier.
- **A missing seat is `NEEDS_ATTENTION`, never silent consensus.** `synthesize()` marks any
  seat without a response artifact; it must never infer agreement from absence.
- **No direct ArangoDB or Qdrant access.** All persistence goes through the memory daemon
  (`POST /store`). `from arango import ArangoClient` is forbidden.
- **A `/store` 200 is not proof.** `stored_verified` is set only after `/memory recall`
  surfaces the document. This rule exists because `/store` once returned
  `{"stored": true}` for a document it never wrote.
- **Seat responses are advisory reviewer evidence, not local proof.** Executable slices
  still require deterministic local verification before closure.
- **Dry-run performs no `/store` and passes no `--execute`.** Asserted by `sanity.sh`.

## Composition assumptions

| Skill | Assumption |
| --- | --- |
| `/ask` | `tau-dag ... --topology concurrent` compiles the packet into a Tau DAG; browser transport is Tau/Surf's problem, not ours |
| `/memory` | `project_roundtables` collection accepts the full receipt; the tagged `lessons` summary is what actually guarantees hybrid recall |
| `/project-taxonomy` | `run.sh ci` is the discipline/domain/portfolio gate embedded in the packet |
| `/project-state`, `/brave-search`, `/ops-workstation` | Context sources; each failure is recorded as `NOT_ESTABLISHED`, never silently dropped |
| `/scheduler` | Owns cron registration — see Blocker 1 |
| `/agentic-evals` | Declared in `composes:` but **not yet exercised by any code path in this skill** |

## Known gaps

- `project_roundtables` is not registered in the memory repo's ArangoSearch view, so the
  full receipt is not directly BM25-searchable. Recall works today only through the tagged
  `lessons` summary, which links the receipt by key.
- The five-seat live path has never run, so per-seat failure modes (stale tab, rate limit,
  unrecoverable seat) are untested in this skill. `/ask`'s own release gate covers the
  transport; this skill's handling of a partial panel is unproven.
- `agentic-evals` appears in `composes:` without a corresponding call site.
- No `.ask/browser-oracles.yaml` committed for this skill, though it drives five browser
  reviewers.

## Defect history

| Date | Defect | Caught by |
| --- | --- | --- |
| 2026-08-11 | Cron registered but never scheduled (daemon predates registration, no reload) | Reading daemon start time + upcoming-runs list; `jobs.json` alone looked healthy |
| 2026-08-09 | Packet claimed a `project-taxonomy check` that had drifted to `ci` | Wiring review |
| 2026-08-07 | `ops-workstation` context source exits 1 | First dry run — recorded as `NOT_ESTABLISHED` |
