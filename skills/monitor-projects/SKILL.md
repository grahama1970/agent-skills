---
name: monitor-projects
description: >
  Nightly cron roundtable review of every skill amended during the day.
  Discovers amended skills from git history, builds an equal-context packet
  from /project-state, /ops-workstation, and /brave-search, convenes a
  five-seat browser roundtable (webgpt, webclaude, webkimi, webgrok,
  webgemini) through /ask tau-dag, and stores the attributed synthesis in
  /memory (ArangoDB `project_roundtables` + lessons with Qdrant semantic
  sync) so the human and project agent can recall and discuss it.
triggers:
  - monitor projects
  - nightly roundtable
  - review amended skills
  - what changed today roundtable
  - project review roundtable
  - recall last roundtable
metadata:
  short-description: Nightly roundtable review of amended skills, stored in /memory
runtime_self_improvement: basic
provides:
  - nightly-skill-review
  - roundtable-receipts
  - amended-skill-discovery
composes:
  - ask
  - memory
  - project-state
  - project-taxonomy
  - brave-search
  - ops-workstation
  - scheduler
  - agentic-evals
complies:
  - best-practices-skills
  - best-practices-python
  - best-practices-arangodb
  - best-practices-roundtable
taxonomy:
  - observability
  - review
  - deliberation
  - self-improvement
disciplines:
  - observability-operations
  - agentic-orchestration
  - evaluation-quality
---

# Monitor Projects

Nightly, on a scheduler cron, review **the skills amended during the day** —
not the whole agent-skills project (agent-skills is a collection of skills;
the unit of review is the skill directory) — via a five-seat concurrent
roundtable, then store the result in `/memory` for later recall.

## Pipeline (one `nightly` run)

1. **Discover** — `git log --since` over `skills/<name>/` paths in the
   canonical checkout finds skills amended in the last 24h. No amendments →
   store a `no_changes` receipt and exit 0.
2. **Context** — build the shared packet from:
   - `/project-state report --json --cached` (project readiness evidence),
   - `/ops-workstation` quick health (host context),
   - `/brave-search web` for each amended skill's load-bearing topic
     (capped, external evidence per `/best-practices-roundtable`).
3. **Roundtable** — one `/ask` compile+execute, per
   `/best-practices-roundtable` (equal context, concurrent topology, no
   privileged seat):

   ```bash
   skills/ask/run.sh tau-dag "<shared packet>" \
     --repo local/agent-skills --target monitor-projects-<date> \
     --handler webgpt --handler webclaude --handler webkimi \
     --handler webgrok --handler webgemini \
     --topology concurrent --execute --poll-timeout-seconds 3600 --json
   ```

4. **Synthesize** — per-seat status (responded / blocked / stale tab /
   timed out), common ground, attributed dissent, executable slices. A
   missing seat is `NEEDS_ATTENTION`, never silent consensus.
5. **Store** — via the memory daemon only (NEVER direct ArangoDB):
   - full receipt → `POST /store` `collection: project_roundtables`
     (searchable via `/memory recall`; the memory repo registers this
     collection in the ArangoSearch view per `arango-recall-all-collections`);
   - compact summary → `POST /store` to `lessons` (default collection) with
     tags `["monitor-projects", "roundtable", <date>, <skills...>]`, which
     gets Qdrant semantic sync + dedup, guaranteeing hybrid recall.
   - **Read-back verification**: the run only reports `stored` after
     `/memory recall` returns the document. A `/store` 200 is not proof.

## Commands

```bash
cd skills/monitor-projects

./run.sh discover --json          # amended skills in last 24h (no side effects)
./run.sh nightly                  # full pipeline (discover→context→roundtable→store)
./run.sh nightly --dry-run        # everything except --execute and /store
./run.sh last                     # recall the most recent roundtable from /memory
./run.sh discuss "<question>"     # recall roundtable receipts relevant to a question
./run.sh register                 # register the nightly cron with /scheduler
```

## Cron

`./run.sh register` runs:

```bash
skills/scheduler/run.sh register \
  --name monitor-projects-nightly \
  --cron "30 2 * * *" \
  --command "skills/monitor-projects/run.sh nightly"
```

02:30 sits before the 03:00–04:15 monitor-taxonomy/monitor-skills window.

## Retrieval and discussion

Both the human and the project agent retrieve results the same way:

```bash
./run.sh last                                  # newest receipt, rendered
skills/memory/run.sh recall --q "monitor-projects roundtable <topic>" --brief
```

Every stored document carries `schema: monitor_projects.roundtable.v1`,
`date`, `skills_reviewed`, `seat_status`, `common_ground`,
`attributed_dissent`, `executable_slices`, and the ask run directory path so
receipts can be re-read in full.

## Proof boundaries

- Seat responses are **advisory reviewer evidence**, not local proof.
  Executable slices still require deterministic local verification by the
  project agent before closure.
- `nightly --dry-run` proves discovery, context assembly, and packet shape.
  It does not prove live browser transport; only an `--execute` run with
  validated receipts (`validate_live_browser_workflow.py`) proves that.

## Eval posture

`sanity.sh` runs behavioral gates over committed fixtures: positive control
(amended-skill discovery on a synthetic git repo), negative control (no
amendments → `no_changes`), packet-shape assertion (every seat receives the
identical packet; all five handlers present), and safety boundary (dry-run
performs no `/store` and no `--execute`). Live roundtable transport is
covered by /ask's own release gate, not duplicated here.

## Common Mistakes

### WRONG: reviewing agent-skills as one project
The unit is the amended skill directory, `skills/<name>/`.

### WRONG: writing to ArangoDB or Qdrant directly
```python
from arango import ArangoClient  # forbidden
```
### RIGHT: memory daemon only
```python
client.post("http://127.0.0.1:8601/store", json={"document": {...}, "collection": "project_roundtables"})
```

### WRONG: trusting /store's 200 response
### RIGHT: read back via `/memory recall` before reporting `stored`.

### WRONG: giving one seat extra context because its transport is easier
### RIGHT: one shared packet, identical for all five seats, concurrent topology.
