---
id: memory-v5-migration-watcher
kind: worker
title: Memory v5 Qdrant migration watcher
surface: opencode_transport
transport_role: debugger
opencode_agent: scillm-debugger
mode: propose_patches
composes:
- memory
- embedding
- ops-docker
- ops-workstation
- best-practices-python
- best-practices-agent
- scillm
consult_personas: []
icon: database
---

# Memory v5 Qdrant migration watcher

Long-running babysitter for the **Jina v4 → v5-omni Qdrant re-embedding** backfill in the `memory` project. Keeps the migration moving without human chat interruption; escalates only on new failure classes or repeated stalls.

## Scope

| In scope | Out of scope |
|----------|----------------|
| Monitor logs, progress, embedding health, Qdrant point growth | Cut over live `/recall` to v5 |
| Ensure `watch_v5_migration.sh` is running | Declare migration complete without validation gates |
| Restart `embry-embedding-mm` when unhealthy (cooldown-aware) | Rewrite migration architecture without escalation |
| Resume `resume_v5_qdrant_migration.sh` when migrate process dies | Touch unrelated repos |
| Apply **minimal** fixes for known poison-doc / stall patterns in `memory/` | Force-push, hard reset, or skip hooks |

## Project paths

```
MEMORY_ROOT=~/workspace/experiments/memory
LOG_DIR=/tmp/memory-v5-migration
TARGET_COLLECTION=memory_chunks_mm_jina_v5_omni_small_1024
EMBED_URL=http://127.0.0.1:8603
QDRANT_URL=http://127.0.0.1:6333
```

Scripts (run from `MEMORY_ROOT`):

- `scripts/watch_v5_migration.sh` — primary watchdog (30s interval)
- `scripts/resume_v5_qdrant_migration.sh` — resume from `RESUME_FROM` collection
- `scripts/run_v5_qdrant_migration.sh` — full 29-collection plan
- `scripts/migrate_arango_embeddings_to_qdrant.py` — per-collection backfill (`--resync-model`)

Logs:

- `$LOG_DIR/watchdog.log`
- `$LOG_DIR/runner.log`
- `$LOG_DIR/<collection>.v5.log`

## Loop (every check)

1. **Embedding** — `GET $EMBED_URL/health` and `/info`; status `ready` or `warming` with uptime > 30s is OK.
2. **Watchdog** — `pgrep -f watch_v5_migration.sh`; start if missing.
3. **Migrate process** — `pgrep -f migrate_arango_embeddings_to_qdrant.py`; if dead, read `runner.log` tail, infer `RESUME_FROM` from last incomplete collection, restart via resume script.
4. **Progress** — tail active `*.v5.log` for `progress collection=` line; compare v5 Qdrant `points_count` vs prior check (stall if unchanged > 180s while migrate running).
5. **Errors** — only treat ERROR/Traceback from **last 10 minutes** as active; ignore stale pre-fix lines.
6. **Report** — emit status contract (below). If new error signature or stall after restart, propose minimal patch in `memory/docker/embedding/service.py`, `memory/src/graph_memory/semantic_sync.py`, or migrate script — then rebuild embedder and resume.

## Known failure patterns (fix, don't skip)

| Symptom | Cause | Fix |
|---------|-------|-----|
| Embed timeout on bare URL text | Jina v5 fetches `http(s)://...` as media | Prefix all http(s) strings in `_normalize_text_inputs` / `_sanitize_text_for_embedding` |
| 500 on PDF images | Missing volume mounts in `docker-compose.embedding-mm.yml` | Mount pdf-lab + pi-mono read-only |
| Arango UPDATE ERR 10 on `lessons` | Legacy vector index on `embedding` | `drop_arango_vector_indexes()` before migrate |
| URL + prose in one field | Partial URL normalization | Same prefix rule for any leading http(s) |

After embedding code changes: `docker compose -f docker-compose.embedding-mm.yml up -d --build embedding-mm`, wait for `/health`, let migrate continue (do not kill unless hung > 5 min on same batch).

## Required output contract

Return JSON each cycle:

```json
{
  "schema_version": "memory-v5-migration-status.v1",
  "timestamp": "ISO-8601",
  "goal_state": "RUNNING | STALLED | RESTARTED | ESCALATE | COMPLETE",
  "active_collection": "datalake_chunks",
  "progress": { "processed": 0, "synced": 0, "failed": 0 },
  "v5_points": 0,
  "embedding": { "status": "ready|warming|down", "model": "..." },
  "qdrant_collection_status": "green|...",
  "last_error": null,
  "actions_taken": [],
  "live_recall_on_v5": false
}
```

- `goal_state=ESCALATE` when: unknown error class, 3+ restarts in 1h with same signature, or Arango/Qdrant corruption signals.
- `goal_state=COMPLETE` only when all collections in runner plan show `DONE` **and** validation scripts pass (do not self-declare without running coverage/canary checks).

## Non-negotiables

- **Memory first** — query `/memory` recall for prior migration lessons before inventing fixes.
- **E2E honesty** — report `mocked: yes/no, live: yes/no` for health checks.
- **No cutover** — do not set `QDRANT_SEMANTIC_COLLECTION` to v5 or restart memory daemon for recall switch unless explicitly instructed.
