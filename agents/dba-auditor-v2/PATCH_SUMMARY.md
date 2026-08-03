# Patch summary

This patch replaces Dewey's broad overnight repair-cycle control model with a queue-driven one-issue DBA worker.

## Core correction

Old bad invariant:

```text
All automatic repair attempts route through monitor_sparta.py repair-cycle only.
```

New invariant:

```text
All automatic Dewey repairs claim one monitor-sparta repair issue and run exactly one bounded DBA lane with deterministic receipt/proof artifacts.
```

## Lanes implemented

- `inline_embedding_policy`
- `qdrant_pointer_metadata`
- `missing_qdrant_embeddings`
- `source_text_qra_coverage`
- `qra_coverage_per_control`

## Ownership boundary

- monitor-sparta reports/queues issues.
- Dewey claims one issue and orchestrates one lane.
- memory-owned scripts/endpoints perform ArangoDB/Qdrant mutation primitives.
- cron does not contain hidden AQL or direct Qdrant writes.
