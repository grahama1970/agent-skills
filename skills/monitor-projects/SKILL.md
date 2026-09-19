---
name: monitor-projects
description: >
  Project Watchdog-composed nightly refresh of registered project knowledge
  plus a roundtable review of every skill amended during the day. Discovers
  project commits and amended skills from git history, builds an equal-context packet
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
  - registered-project-memory-refresh
composes:
  - ask
  - memory
  - project-state
  - project-taxonomy
  - brave-search
  - ops-workstation
  - project-watchdog
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

Nightly, composed by the single `$project-watchdog` cron, refresh source-backed
Q&A for every registered project with new commits, then review **the skills amended during the day** —
not the whole agent-skills project (agent-skills is a collection of skills;
the unit of review is the skill directory) — via a five-seat concurrent
roundtable, then store the result in `/memory` for later recall.

## Pipeline (one `nightly` run)

1. **Refresh registered projects** — validates Project Watchdog's registry,
   deduplicates shared Git roots, fetches `origin/main`, and selects commits
   after each repository's independent `project_qa_last_sha` watermark. Each
   commit becomes a deterministic `project_activity` evidence row plus a
   source-backed question/answer in Memory's governed `project_memory_versions`
   lifecycle. The skill stages and promotes through `/project-memory/*`, then
   reads back the exact active head before advancing that project's watermark.
   It never writes a parallel literal `project_memory` collection, bypasses the
   lifecycle authority, or stores vector arrays in ArangoDB.
2. **Discover amended skills** — fetches, then selects skills whose `skills/<name>/` paths
   were touched since the **last reviewed commit** (`<watermark>..HEAD`).
   The watermark lives at `~/.local/state/monitor-projects/watermark.json`
   (override with `MONITOR_PROJECTS_WATERMARK`) and advances **only after a
   run that both succeeded and stored** — so a failed or missed night
   re-scans the same range instead of losing it. `--since` is the first-run
   fallback only; a wall-clock window cannot resume, and a missed night would
   silently skip everything in the gap while its receipt still looked
   complete. An unknown watermark falls back to the window rather than
   selecting nothing. No amendments → `no_changes` receipt, exit 0.
3. **Context** — build the shared packet from:
   - `/project-state report --json --cached` (project readiness evidence),
   - `/ops-workstation` quick health (host context),
   - `/brave-search web` for each amended skill's load-bearing topic
     (capped, external evidence per `/best-practices-roundtable`).
4. **Roundtable** — one `/ask` compile+execute, per
   `/best-practices-roundtable` (equal context, concurrent topology, no
   privileged seat):

   ```bash
   skills/ask/run.sh tau-dag "<shared packet>" \
     --repo local/agent-skills --target monitor-projects-<date> \
     --handler webgpt --handler webclaude --handler webkimi \
     --handler webgrok --handler webgemini \
     --topology concurrent --execute --poll-timeout-seconds 3600 --json
   ```

5. **Synthesize** — per-seat status (responded / blocked / stale tab /
   timed out), common ground, attributed dissent, executable slices. A
   missing seat is `NEEDS_ATTENTION`, never silent consensus.
6. **Store** — via the memory daemon only (NEVER direct ArangoDB):
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
./run.sh register                 # install centralized Project Watchdog cron; remove legacy job
```

## Cron

`./run.sh register` removes the legacy `monitor-projects-nightly` scheduler job
and installs Project Watchdog's single `*/15` cron. After the ticket tick has
run and released its work, Project Watchdog launches `monitor-projects nightly`
at most once per local day after 02:30 under a separate maintenance lock. Ticket
selection and leases never wait for the roundtable.

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
- `nightly --dry-run` proves discovery, context assembly, and packet shape,
  and never advances the watermark (asserted by `sanity.sh`).
  It does not prove live browser transport; only an `--execute` run with
  validated receipts (`validate_live_browser_workflow.py`) proves that.

## Eval posture

`sanity.sh` runs behavioral gates over committed fixtures: positive control
(amended-skill discovery on a synthetic git repo), watermark controls (range
selects the right commit, a watermark at HEAD selects nothing, an unknown
watermark falls back), negative control (no
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
