---
name: ops-arango
description: >
  Manage ArangoDB operations including backups with automatic retention,
  health checks, embedding gap detection, duplicate detection, and integrity verification.
  Works with local or containerized ArangoDB.
triggers:
  - backup arangodb
  - dump arango
  - create database backup
  - arango dump
  - backup memory database
  - arango ops
  - check database health
  - flag embedding arrays stored in Arango (contract violation)
  - detect duplicates
  - database maintenance
  - cleanup orphans
  - verify integrity
allowed-tools: Bash
metadata:
  short-description: ArangoDB operations, backups, and maintenance

provides:
  - ops-arango
composes:
  - memory
  - scheduler
  - task-monitor
disciplines:
  - observability-operations
  - memory-knowledge
---

> STOP. READ THIS ENTIRE SKILL.MD BEFORE CALLING ANY ENDPOINT.

# Arango Ops

Reliable ArangoDB operations: backups, health checks, and maintenance.

## Commands

```bash
# Create dump (Local 'arangodump' binary must be in PATH)
./run.sh dump

# Create dump from Docker Container
CONTAINER=arangodb ./run.sh dump

# Run all health checks
./run.sh check

# Find docs violating the no-embeddings-in-Arango contract
./run.sh embeddings

# Detect duplicate lessons
./run.sh duplicates --report

# Find orphaned edges
./run.sh orphans --fix

# Verify referential integrity
./run.sh integrity

# Collection statistics
./run.sh stats

# Full maintenance cycle
./run.sh full --fix
```

## Health Checks

| Check | Description |
|-------|-------------|
| `embeddings` | Find docs that VIOLATE the vector contract by holding embedding arrays in Arango (Qdrant is the only vector store) |
| `duplicates` | Detect lessons with similar titles/content |
| `orphans` | Find edges pointing to deleted documents |
| `integrity` | Verify all foreign keys resolve |
| `stats` | Collection sizes and document counts |

## Output Format

All commands support `--json` for machine-readable output:

```bash
./run.sh check --json
```

```json
{
  "status": "healthy|warning|critical",
  "checks": {
    "embeddings": {"violations": 0, "total": 1234},
    "duplicates": {"found": 5, "clusters": 2},
    "orphans": {"edges": 0},
    "integrity": {"errors": 0}
  },
  "recommendations": []
}
```

## Backup Output Location

Backups saved to: `/mnt/storage12tb/backups/arangodb/<timestamp>/`

## Restore Guidance

`ops-arango` currently automates dumps and health checks. For restores, use
`arangorestore` directly and keep progress output enabled.

```bash
arangorestore \
  --progress true \
  --log.level info \
  --server.endpoint tcp://127.0.0.1:8529 \
  --server.username root \
  --server.password "$ARANGO_PASS" \
  --server.database memory \
  --input-directory /path/to/dump \
  --overwrite true
```

Notes:
- `--progress` is enabled by default, but pass it explicitly for long restores so
  operators know progress visibility was intentional.
- Use `--log.level info` when running through `docker exec`, wrappers, or
  automation so collection-level progress is easier to recover from logs.
- If a restore must be resumed, prefer ArangoDB's native restore flow and
  continue from the same dump rather than switching to bespoke import logic mid-run.

## Features

- **Explicit Mode**: Set `CONTAINER` env var to use Docker. Default is local binary.
- **Integrity Check**: Verifies `manifest.json` existence after dump.
- **Safe Retention**: Keeps last N backups automatically (default 7).
- **Embedding Contract**: Flags docs holding embedding arrays in Arango. Arango must NEVER store embeddings — over a certain dataset size the community edition shuts down (paid tier required); Qdrant owns all vectors, Arango holds pointer metadata only. `--fix` is refused; migration belongs to the memory repo's migrate_arango_embeddings_to_qdrant.py.
- **Orphan Cleanup**: Removes edges pointing to deleted documents.
- **Duplicate Detection**: Finds lessons with identical titles.

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `ARANGO_URL` | `http://127.0.0.1:8529` | ArangoDB endpoint |
| `ARANGO_DB` | `memory` | Database name |
| `ARANGO_USER` | `root` | Username |
| `ARANGO_PASS` | - | Password |
| `CONTAINER` | - | **Required for Docker dump**. Container name. |
| `RETENTION_N` | `7` | Number of backups to keep |
| `DRY_RUN` | `0` | Set to `1` for preview mode |

## Batch Operations & Performance

### Bulk Updates

For large-scale updates (10K+ documents), use batch AQL instead of individual calls:

```python
# WRONG: 222K individual HTTP requests (3.3/s = 18 hours)
for qra in qras:
    http.post('/create-evidence-case', json={'question': qra['question']})

# RIGHT: Batch endpoint with ThreadPoolExecutor (50 req/batch, 32 workers)
http.post('/create-evidence-case-batch', json={
    'items': [{'question': q['question'], 'source_id': q.get('source_id') or ''} for q in batch],
    'max_workers': 32
})
```

### Bulk AQL Updates

For direct database updates without HTTP overhead:

```python
# Single document update
db.aql.execute('UPDATE {_key: @key} WITH {field: @val} IN collection', bind_vars={...})

# BETTER: Bulk update (100 docs per query)
aql = '''
FOR item IN @updates
  UPDATE {_key: item.key} WITH {field: item.val} IN collection
  RETURN 1
'''
db.aql.execute(aql, bind_vars={'updates': [{'key': k, 'val': v} for k, v in batch]})
```

### Performance Bottlenecks

| Symptom | Cause | Fix |
|---------|-------|-----|
| 3-5 req/s via HTTP | Single-threaded daemon | Use batch endpoint with `max_workers` |
| AQL taking 10s+ | Full collection scan | Add ArangoSearch View index |
| Memory spikes | Large result sets | Use cursor pagination with `_key > @last_key` |
| Slow backfill | Individual updates | Batch 50-100 docs per AQL UPDATE |

## Scheduling

Add to your project's services.yaml for automated maintenance:

```yaml
scheduled:
  db-maintenance-daily:
    description: "Daily database health check"
    command: ".pi/skills/ops-arango/run.sh check --json"
    schedule: "0 1 * * *"  # 1am daily
    enabled: true

  db-maintenance-weekly:
    description: "Weekly full maintenance with fixes"
    command: ".pi/skills/ops-arango/run.sh full --fix"
    schedule: "0 0 * * 0"  # Midnight Sunday
    enabled: true

  db-backup-daily:
    description: "Daily ArangoDB backup"
    command: ".pi/skills/ops-arango/run.sh dump"
    schedule: "0 3 * * *"  # 3am daily
    enabled: true
```
