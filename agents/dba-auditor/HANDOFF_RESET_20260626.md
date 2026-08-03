# Handoff Report: Dewey DBA Auditor Reset

**Timestamp**: 2026-06-26T06:44:47-04:00  
**Active Agent**: Codex  
**Scope**: `/home/graham/workspace/experiments/agent-skills/agents/dba-auditor` and `/home/graham/workspace/experiments/memory`

## 1. Project Overview

- **Ecosystem**: Python, ArangoDB, Qdrant, Docker services, agent-skill runtime.
- **Core Purpose**: Dewey is intended to be the DBA repair subagent for `$monitor-sparta`, not the monitor itself.
- **Supervisor Skill**: `$monitor-sparta` exposes SPARTA corpus/QRA health lanes and must remain read-only by default.
- **Dewey Role**: perform bounded, rollback-backed, proof-producing DBA repairs one deterministic gap slice per invocation.

## 2. Required Skill Contracts Already Read

The following skill files were read from disk during the handoff/bundle work:

| Skill | Path | Lines | SHA-256 |
|---|---:|---:|---|
| handoff | `/home/graham/workspace/experiments/agent-skills/skills/handoff/SKILL.md` | 88 | `083b4de1f9740c04f507ca328bfef8ebc785192b8560ef91094e31c869e53af5` |
| clipboard | `/home/graham/workspace/experiments/agent-skills/skills/clipboard/SKILL.md` | 91 | `942cfbd9acf2647a4f9286eaa5a5e69ed0b2f0c859438b6e290bca27d96afbb4` |
| monitor-sparta | `/home/graham/workspace/experiments/agent-skills/skills/monitor-sparta/SKILL.md` | 400 | `6ee020255f7554b0055428687ea4b5dfe477999aaa1d6f3d9011aa7c120c73a5` |
| embedding | `/home/graham/workspace/experiments/agent-skills/skills/embedding/SKILL.md` | 570 | `27e53ddd2fc015c526419d8a4ce038a1098b09bdb4a03b0775ad8640ba6b8919` |
| create-qras | `/home/graham/workspace/experiments/agent-skills/skills/create-qras/SKILL.md` | 525 | `e9ada6e74eac65e2c59b30909794352b374517bdaf44c957d05bec4593474744` |
| memory | `/home/graham/workspace/experiments/agent-skills/skills/memory/SKILL.md` | 1208 | `57fd1a9a3f28624102cc4ba9504087c300a75968325963049d130e3d6af32989` |

The next agent should still re-read any named skill before acting if the user mentions it again.

## 3. Current State

### Bundle For WebGPT

A WebGPT create-architecture request bundle was created and copied to the desktop clipboard as a file MIME item:

- Zip: `/tmp/dewey-webgpt-architecture-bundle-20260626T104000Z.zip`
- SHA-256: `7c06e69ea4f304af7dc9582f5c161cf610a7258c4f29d8c881980e71f5465a77`
- Zip file count: `47`
- Clipboard verification: `TARGET=text/uri-list`, `URI=file:///tmp/dewey-webgpt-architecture-bundle-20260626T104000Z.zip`, `OWNER_PID=3669095`

Bundle contents intentionally include:

- full `SKILL.md` contracts for `monitor-sparta`, `embedding`, `create-qras`, and `memory`
- `agents/dba-auditor` source/docs/tests/fixtures
- `WEBGPT_REQUEST.md`
- `MANIFEST.json`

Bundle contents intentionally exclude:

- `agents/dba-auditor/webgpt-engagement/`
- `evidence/`
- `__pycache__/`
- `.pyc`
- `.zip`
- `.sha256`
- proof/health/generated artifacts

### Dewey Implementation State

Dewey is **not proven ready** as a cron-safe autonomous repair subagent.

Known implementation surface in this agent directory:

- `AGENTS.md`
- `GOAL_DEWEY.md`
- `HANDOFF_DEWEY.md`
- `PROJECT_KNOWLEDGE.md`
- `SELF_IMPROVEMENT_LOOP.md`
- `persona.yaml`
- `scripts/dewey_overnight_run.py`
- `scripts/dewey_nightly_cron.sh`
- `scripts/db_repair_session.py`
- `scripts/prompt_reviewer_receipt.py`
- `tests/test_dewey_monitor_sparta_nightly.py`
- `tests/test_dewey_prompt_reviewer_qra_gate.py`
- `tests/test_db_repair_session.py`
- `tests/test_dewey_r3_monitor_sparta_diagnostics.py`

Known implementation surface touched in memory repo during the prior work:

- `scripts/validation/_health_checks.py`
- `scripts/validation/monitor_sparta.py`
- `scripts/validation/sparta_repair_manifests.py`
- `scripts/migrate_arango_embeddings_to_qdrant.py`
- `src/graph_memory/semantic_sync.py`
- `src/graph_memory/service/app/_core.py`
- `tests/health/test_monitor_sparta_prevention_checks.py`
- `tests/health/test_monitor_sparta_repair_cycle_helpers.py`

Git diff stat for the main Dewey/memory files at handoff time:

```text
 scripts/validation/_health_checks.py               |  774 +++++++-
 scripts/validation/monitor_sparta.py               | 2002 +++++++++++++++++++-
 scripts/validation/sparta_repair_manifests.py      |  407 +++-
 src/graph_memory/semantic_sync.py                  |  334 +++-
 src/graph_memory/service/app/_core.py              |  254 ++-
 .../test_monitor_sparta_prevention_checks.py       |   75 +-
 6 files changed, 3660 insertions(+), 186 deletions(-)
```

The worktree is very dirty with many unrelated changes. Do not revert unrelated files.

## 4. What Is Working Or Partially Working

- The WebGPT architecture request bundle exists and is on clipboard.
- The bundle now includes `agents/dba-auditor` source/docs/tests/fixtures and excludes generated artifacts.
- Focused unit tests previously reported `20 passed, 43 warnings` for:
  - `tests/health/test_monitor_sparta_prevention_checks.py::test_inline_embedding_policy_fails_on_inline_arrays`
  - `tests/health/test_monitor_sparta_repair_cycle_helpers.py`
- Direct repair command artifact previously reported:
  - `sparta_qra_canonical processed=273`
  - `synced=273`
  - `dropped=273`
  - `pending=0`
- That direct repair output is a tool artifact only. It is not independent proof of the final DB invariant.

## 5. What Is Broken Or Unproven

- Dewey wrapper behavior is not proven cron-safe.
- Dewey has not proven it can select the exact failing `$monitor-sparta` lane/collection and repair one slice cleanly.
- The prior `monitor_sparta.py repair-cycle` path was too broad and opaque; it ran baseline health and produced a metadata artifact for `sparta_controls` while the known failing records were in `sparta_qra_canonical`.
- Independent post-repair Arango count was not run after the direct `273` repair artifact because the user paused the goal.
- No completion/green/fixed claim is justified.
- Prompt-reviewer policy must be enforced only for QRA generation/prompt/schema repairs, not for plain embedding cleanup.
- Dewey must split source embedding coverage into separate instances/lanes:
  - misplaced inline embeddings in Arango
  - missing Qdrant embeddings
  - Qdrant pointer metadata reconciliation
- Missing Qdrant embeddings must be repaired in batches/microbatches, not one embedding at a time.
- ArangoDB must never receive vector arrays.
- Database backups must not run every Dewey cycle; backup at most once per day unless explicitly requested.

## 6. Correct Dewey Mental Model

`$monitor-sparta` is the supervisor. Dewey is a DBA repair subagent under monitor-sparta lanes.

Required Dewey lane split:

1. **Arango Inline Vector Cleanup**
   - one read/count AQL over SPARTA collections
   - one guarded AQL strip when docs are already synced to Qdrant
   - one post-count AQL
   - receipt with exact AQL, counts, affected rows, terminal state

2. **Missing Qdrant Embedding Backfill**
   - query missing/stale Qdrant semantic coverage
   - page Arango docs by stable key
   - embed in GPU-safe microbatches
   - bulk upsert Qdrant
   - bulk update Arango pointer metadata only
   - rollback just-created Qdrant points if Arango metadata update fails

3. **Qdrant Pointer Metadata Reconciliation**
   - detect Qdrant points that exist without Arango pointer metadata
   - update Arango metadata only
   - do not embed
   - do not write vector arrays

4. **QRA Generation Gap Repair**
   - build concrete `/create-qras` manifest and prompt-review bundle
   - prompt-reviewer is required before QRA generation
   - use `/create-qras review`, dry-run, canary write, then larger batch only after proof
   - use scillm batch pool contract for corpus repair

5. **Source/Text/QRA Coverage Manifests**
   - observe gaps and write review-required manifests
   - do not synthesize source text
   - treat placeholder/stub text as unsupported evidence

6. **Health/State/Terminal Receipt**
   - every Dewey invocation writes durable receipt with before/after counts, commands, artifact paths, `mocked`, `live`, terminal status, and next lane.

## 7. Immediate Next Steps For New Agent

1. Do not mutate the database first.
2. Inspect `/tmp/dewey-webgpt-architecture-bundle-20260626T104000Z.zip` if WebGPT handoff is the next action.
3. If asked to send to WebGPT, use the real `$ask` or `$surf` skill contract after reading its `SKILL.md`; do not invent a substitute.
4. If asked to continue implementation locally, start with read-only checks only:

```bash
cd /home/graham/workspace/experiments/memory
PYTHONPYCACHEPREFIX=/tmp/dewey-pycache-check python3 - <<'PY'
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path('src').resolve()))
from graph_memory.arango_client import get_db
fields = ['embedding','embeddings','embedding_visual','embedding_2','embedding_multimodal','vector','vectors','dense_vector','text_vector','image_vector']
collections = ['sparta_controls','sparta_qra','sparta_qra_canonical','sparta_qra_relationship','sparta_url_knowledge']
db=get_db(); rows=[]
for coll in collections:
    result=list(db.aql.execute('''
    FOR d IN @@coll
      LET inline_fields = (FOR field IN @fields FILTER IS_ARRAY(d[field]) AND LENGTH(d[field]) > 0 RETURN field)
      FILTER LENGTH(inline_fields) > 0
      COLLECT synced = (d.qdrant_point_id != null AND d.semantic_sync_state == "synced") WITH COUNT INTO count
      RETURN {synced: synced, count: count}
    ''', bind_vars={'@coll': coll, 'fields': fields}))
    rows.append({'collection': coll, 'inline_counts': result})
print(json.dumps(rows, indent=2, sort_keys=True))
PY
```

5. Do not claim completion from the direct repair artifact. If the count query shows zero inline vectors, report only that the read-only count output is zero at that time.
6. If the count query shows remaining inline vectors, do not run a broad Dewey wrapper. Use a narrow lane:
   - if synced: guarded strip AQL
   - if unsynced: missing-Qdrant backfill lane first
7. Patch Dewey around explicit lanes and receipts, not one broad repair-cycle blob.

## 8. Commands/Artifacts From This Handoff

Handoff facts command:

```bash
.pi/skills/handoff/run.sh
```

Clipboard command:

```bash
/home/graham/workspace/experiments/agent-skills/skills/clipboard/run.sh file /tmp/dewey-webgpt-architecture-bundle-20260626T104000Z.zip
```

Clipboard verified:

```text
OK clipboard file copy verified
TARGET=text/uri-list
URI=file:///tmp/dewey-webgpt-architecture-bundle-20260626T104000Z.zip
OWNER_PID=3669095
TARGETS:
TARGETS
text/uri-list
```

## 9. Human Constraints To Preserve

- Be concise and operational.
- No vague status.
- No closure language without deterministic proof.
- No database backup per run.
- Never write vectors to ArangoDB.
- Do not force the human to infer state from prose.
- If paused, stop.
- If creating bundles, include source code required for review and exclude generated artifacts unless explicitly requested.

## 10. Cron/Subagent Course Correction From Brave Search

The user asked for external course correction on cron subagents after this failure. `$brave-search` was used on 2026-06-26 with these queries:

- `cron job idempotent worker lock file single instance best practices`
- `designing reliable cron workers idempotency retries observability`
- `database migration job idempotent batches progress checkpoint rollback best practices`

Raw result themes that matter for Dewey:

- Cron jobs must assume overlap can happen and must use a single-instance guard such as `flock`, `run-one`, or equivalent lock semantics.
- Jobs should be bounded and report when runtime exceeds the expected window.
- Reliable workers are built around idempotency, retry-safe operations, durable state, and dead-letter/operator states for unrecoverable failures.
- Database repair/migration batches must be idempotent so a partial failure followed by retry does not corrupt already-processed rows.
- Observability is not optional: every run needs progress, history, and failure diagnostics that identify the current batch/item.

Sources returned by Brave:

- `GitHub - pushcx/lockrun`: https://github.com/pushcx/lockrun
- `Cron Job Best Practices for Production Systems`: https://www.cronwizard.com/best-practices
- `Prevent duplicate cron jobs running - Server Fault`: https://serverfault.com/questions/82857/prevent-duplicate-cron-jobs-running
- `How to prevent duplicate cron jobs from running - Cronitor`: https://cronitor.io/guides/how-to-prevent-duplicate-cron-executions
- `Temporal error handling in distributed systems`: https://temporal.io/blog/error-handling-in-distributed-systems
- `Temporal durable event sourcing/idempotent execution`: https://temporal.io/blog/temporal-replaces-state-machines-for-distributed-applications
- `Database Migration Strategies: Safe Schema Changes`: https://www.intelligentgraphicandcode.com/development/database-migrations

Concrete Dewey correction:

1. Cron should invoke one Dewey worker with a non-overlap lock and a fixed maximum runtime.
2. Dewey should claim one monitor issue/slice using a durable run id and lane id.
3. The selected lane must be idempotent and retry-safe.
4. The lane must checkpoint batch progress by stable key or item id.
5. Every mutation must be guarded by before/after queries and written receipt fields.
6. Transient failures should retry within the lane budget.
7. Unrecoverable failures should exit into `OPERATOR_REQUIRED` or `BLOCKED_TRANSIENT_SERVICE`, not spin.
8. The next cron run should resume from durable state or select the next issue; it must not start a broad full-health repair loop by default.
