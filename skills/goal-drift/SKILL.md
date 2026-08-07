---
name: goal-drift
description: >
  Read-only goal-drift auditor. Holds each project's immutable goal as a typed record
  derived only from real human prompts, inspects what the project actually produced
  (tickets first, then artifacts, commits, and absences), and labels every action
  SERVES_GOAL, SUPPORTS_INDIRECTLY, DECLARED_DRIFT, UNTICKETED_WORK, SCOPE_DRIFT or
  MISSING_EXPECTED with a reason. Runs nightly on cron and reports; it
  never edits, commits, fixes, or reprioritises. Use when asked whether work is on track,
  whether an agent drifted, to register or read a project's immutable goal, or to run the
  goal-drift check.
allowed-tools:
  - Bash
  - Read
triggers:
  - goal drift
  - did we drift
  - am I on track
  - scope drift
  - check goal drift
  - drift verdict
  - is this work serving the goal
  - register immutable goal
  - what is the immutable goal
  - why did we drift
metadata:
  short-description: Read-only goal-vs-actions drift audit on a nightly cron
  author: Graham
  version: "0.1.0"
  inspired-by: "nicobailon/pi-subagents watchdog scope-drift (README verified 2026-08-02)"
runtime_self_improvement: basic

provides:
  - goal-registry
  - goal-drift-detection
  - scope-drift-report
composes:
  - ticket
  - tau
  - memory
  - goal-helper
  - scheduler
  - task-monitor
complies:
  - best-practices-skills
  - best-practices-python
  - best-practices-arangodb
taxonomy:
  - operations
  - validation
  - precision
  - resilience
  - human-in-the-loop
disciplines:
  - evaluation-quality
  - observability-operations
---

# goal-drift

**Read-only.** Observes and reports. It cannot edit files, commit, or reprioritise. A
drift detector that can also act becomes one more lane to drift into.

## Related skills, easily confused

| Skill | Axis |
|---|---|
| `/goal-helper` | **authors** a goal: proof command, completion criteria, retry limits |
| `/project-drift` | **knowledge** drift: does transcript evidence stale-date `PROJECT_KNOWLEDGE.md`? |
| **`goal-drift`** | **goal** drift: does the work still serve the registered immutable goal? |

`/project-drift` asks *"is the documentation still true?"* This asks *"are we still doing the
right thing?"* Both are real; they fail independently. Documentation can be perfectly
accurate while the work wanders.

## Why it exists

An immutable goal written into a document does not prevent drift. Observed 2026-08-02: a
goal was recorded verbatim in a skill header, and the work still went to a compiler fix in
another repo, four unrelated documentation edits, and single-employer archaeology reported
as chat prose. Every step was defensible alone. None was the artifact the goal named. The
`PROJECT_KNOWLEDGE` claims stayed accurate throughout, so a knowledge-drift auditor would
have reported clean. Nobody noticed until the human asked.

The mechanism is ported from `nicobailon/pi-subagents`, whose watchdog keeps a
current-scope artifact from real user prompts and flags work that no longer serves it as
`scope-drift`. That project is a Pi extension (TypeScript), so the pattern is reimplemented
here rather than installed.

## The rule that makes it work

**Scope comes only from real human prompts.**

The agent's own intermediate goals, self-generated plans, and auto-follow steps are never
admitted as scope. Without this rule an agent invents a sub-goal, pursues it, and grades
itself compliant. pi-subagents makes the same exclusion: its watchdog auto-follow prompts
are explicitly not recorded as scope.

`register` stores `source: human_prompt` with the verbatim text. Anything marked
`agent_inferred` is **refused at registration**, not warned about.

## Commands

```bash
./run.sh register --project <name> --goal-file goal.txt   # human text only
./run.sh goal --project <name>                            # read the goal back
./run.sh check --project <name> --since 24h [--json]      # the audit
./run.sh schedule                                         # nightly cron
./sanity.sh                                               # behavioral gates
```

Nightly:

```bash
/scheduler add goal-drift --cron "0 6 * * *" --budget 5
```

06:00 deliberately — **after** nightly producers finish, so it grades a completed night
rather than one in progress.

## Evidence hierarchy — tickets first

| Rank | Evidence | Source | Why |
|---|---|---|---|
| 1 | **Tickets** | `/ticket` + `gh issue list` | declares intent **before** work starts |
| 2 | Artifacts | criterion `artifact_globs` | did the thing actually get produced? |
| 3 | Commits | `git log --since` | secondary; a commit citing **no** ticket is itself a signal |
| — | **Absence** | expected artifact never produced | the case a what-happened-only checker cannot see |

Tickets rank first because a ticket declares intent at filing time, so drift is catchable
the day it is declared rather than weeks later in commit forensics. A lease shows what is
being worked on *now*; attached proof is real acceptance evidence rather than a filename
guess. Verified: a ticket titled "Fix DAG reachability in tau compiler" against a
report-and-resume goal yields `DECLARED_DRIFT` with zero commits present.

**Absence remains the finding that matters most.** A night with twelve commits and zero
instances of the artifact the goal names *is* the drift case.

## Strict seam contracts

Every boundary-crossing artifact is validated at the producer with a typed
`@dataclass` + `validate()` (copy-safe, no pydantic). Exactly three outcomes: **pass,
self-heal-with-record, or raise** — never warn-and-continue. Validated artifacts carry a
`seam_validation` stamp so a reader can tell "validated" from "never checked".

Cross-field truth checks, because field presence alone does not catch a lying summary:

- `ON_GOAL` while findings contain drift markers → **refused**
- `NOT_ESTABLISHED` without a `GOAL_UNREGISTERED` finding → refused
- `indirect_share > indirect_cap` while claiming `ON_GOAL` → refused
- `read_only: false` → refused

The skill therefore cannot emit a verdict its own evidence contradicts.

## tau integration

The audit is handed to `/tau` as a skill node using **`tau.generic_dag_spec.v1`** — *not*
`tau.dag_contract.v1`, which tau skill nodes reject — with `tau.skill_work_order.v1` and
`tau.skill_dag_node.v1`. The node declares `read_only: true` and the work order's task text
carries "Never edit, commit, or reprioritise", so the constraint travels with the handoff.

**Goal identity is `goal_hash`**, canonical over the goal object the way tau hashes goals:

- hash covers goal **content**; `registered_at` is excluded, so re-registering identical
  text and criteria reproduces it
- change one word of the goal and the hash changes
- a revision carries the prior hash as **`goal.parent_goal_hash`** — traceable lineage, not
  a silent overwrite

"Immutable" stops being a promise in prose and becomes something a receipt can prove.

## Verdicts

| Verdict | Meaning |
|---|---|
| `SERVES_GOAL` | maps to an acceptance criterion |
| `SUPPORTS_INDIRECTLY` | plausible enabler — **capped**, see below |
| `SCOPE_DRIFT` | real work, no mapping to any criterion |
| `DECLARED_DRIFT` | a **ticket** declares work matching no criterion — caught at filing time |
| `UNTICKETED_WORK` | a commit cites no ticket and matches no criterion |
| `MISSING_EXPECTED` | a criterion produced nothing |
| `GOAL_UNREGISTERED` | no goal → report is `NOT_ESTABLISHED`, never "clean" |

Run verdict: `ON_GOAL`, `DRIFTED`, `NOT_ESTABLISHED`, or **`DEGRADED`** (an evidence source
failed; partial evidence can never read as on-goal).

`SERVES_GOAL` from a ticket requires **closed AND attached proof**. An on-criterion ticket
still open, or closed without proof, is `SUPPORTS_INDIRECTLY` and does **not** satisfy
absence — "in progress" is not done.

**`SUPPORTS_INDIRECTLY` is capped at 30% of actions.** Past the cap the run is `DRIFTED`,
because *"it was all necessary groundwork"* is precisely the story drift tells about
itself. Infrastructure that enables the goal is legitimate; infrastructure that replaces
producing the goal's artifact is not.

## Report contract

Leads with the verdict and the absences, never with the volume of work:

```
project: monitor-opportunities   window: 24h   verdict: DRIFTED
  MISSING_EXPECTED  daily interactive report   (0 produced, >=1 required)
  MISSING_EXPECTED  tailored resume variant    (0 produced)
  SCOPE_DRIFT       tau compiler fix           (no criterion references tau)
  SERVES_GOAL       ATS tenant discovery       -> criterion: discover opportunities
  indirect 42% exceeds cap 30% -> DRIFTED
```

An honest `DRIFTED` verdict is a **success** for this skill. It must never soften a verdict
because the work looked productive.

## Non-negotiables

- **No mutation.** `sanity.sh` asserts the runtime cannot write to a project tree and that
  no subcommand edits, commits, or reprioritises.
- **No self-certification.** `agent_inferred` goals are refused.
- **Absence is a finding.** Zero expected artifacts is `DRIFTED`, not silence.
- **No goal means `NOT_ESTABLISHED`** — never "on track by default".
- **Writes go through `/memory`**, never direct ArangoDB.

## References

- `references/verdict-contract.md` — verdict definitions and the indirect cap
- `fixtures/agentic_eval.json` — positive, negative, adversarial cases
