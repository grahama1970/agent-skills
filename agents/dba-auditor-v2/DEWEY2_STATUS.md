# Dewey2 Sidecar Status

`agents/dba-auditor-v2` is an isolated candidate DBA repair subagent. It is not
the active Dewey cron target until explicitly promoted.

Core invariant:

```text
cron -> dewey_issue_worker.py run -> claim one monitor-sparta queue issue ->
run one Dewey-owned lane -> write receipt.json -> update queue -> exit
```

Local adaptations from the WebGPT bundle:

- `source_text_qra_coverage` uses
  `/home/graham/workspace/experiments/memory/scripts/validation/source_text_qra_coverage.py`.
- `/create-qras` review/manifest calls are invoked through
  `uv run --project <create-qras-dir> ./run.sh ...` so the skill environment
  resolves dependencies such as `typer`.
- Monitor-side queue construction is owned by
  `/home/graham/workspace/experiments/memory/scripts/validation/monitor_sparta_repair_queue.py`.
  Dewey2 only claims, runs, and updates existing queue entries.
- Dewey2 rejects unsupported queue `schema_version` values and non-Dewey lanes.
- Command timeouts classify as `BLOCKED_TIMEOUT`, not generic transient service
  failures.

Live source-status proof on 2026-06-26:

- First isolated supervisor attempt
  `monitor-sparta-dewey-source-status-flow-20260626T213849Z` correctly refused
  mutation because the registry-materialized Dewey issue had
  `mutation_allowed=false`.
- Corrected isolated supervisor flow
  `monitor-sparta-dewey-source-status-flow-20260626T214037Z` dispatched Qbert,
  Ryan, then Dewey. Dewey claimed one `source_text_status_repair` issue and
  called the memory primitive
  `/home/graham/workspace/experiments/memory/scripts/validation/dewey_source_text_status_repair.py`.
- Receipt:
  `/mnt/storage12tb/skills/review-db/outputs/monitor-sparta-supervisor/dewey-runs/monitor-sparta-dewey-source-status-flow-20260626T214037Z-tick3-source_text_status_repair/receipt.json`
- Proof fields: `terminal_status=DONE`, `mutation_applied=true`,
  `before_count=2`, `changed_count=2`, `after_count=0`,
  `rollback_records=2`, `proof_ok=true`, `ran_repair_cycle=false`,
  `ran_more_than_one_lane=false`.
- Rollback manifest:
  `/mnt/storage12tb/skills/review-db/outputs/monitor-sparta-supervisor/dewey-runs/monitor-sparta-dewey-source-status-flow-20260626T214037Z-tick3-source_text_status_repair/source_text_status_repair/rollback.jsonl`.
- Independent source text scan after apply:
  `/mnt/storage12tb/skills/review-db/outputs/monitor-sparta-supervisor/monitor-sparta-dewey-source-status-flow-20260626T214037Z-independent-rescan/stdout.json`
  reported `control_text_missing_or_stub=0`; the remaining source-text target
  is `url__2651`, owned by Ryan.

Live URL text and embedding proof on 2026-06-26:

- Ryan/fetcher artifact for `url_id=2651`:
  `/mnt/storage12tb/skills/review-db/outputs/research-auditor/url-2651-fetch-20260626T214720Z/consumer_summary.json`
  fetched the Microsoft Learn archive URL and produced `89696` characters of
  extracted text.
- Dewey memory primitive:
  `/home/graham/workspace/experiments/memory/scripts/validation/dewey_url_text_backfill.py`.
- URL text backfill receipt:
  `/mnt/storage12tb/skills/review-db/outputs/dewey-sessions/url-2651-backfill-20260626T214720Z/apply_receipt.json`.
  Fields: `before_count=2`, `changed_count=16`, `after_count=0`,
  `chunk_count=15`, `rollback_records=1`, `proof_ok=true`,
  `ran_repair_cycle=false`.
- Qdrant embedding backfill receipt for the 15 changed `sparta_url_knowledge`
  chunks:
  `/mnt/storage12tb/skills/review-db/outputs/dewey-sessions/url-knowledge-missing-qdrant-20260626T215023Z/apply_receipt.json`.
  Fields: `before_count=15`, `changed_count=15`, `after_count=0`,
  `rollback_records=15`, `proof_ok=true`.
- Independent rescans:
  `/mnt/storage12tb/skills/review-db/outputs/monitor-sparta-supervisor/url-2651-final-independent-rescan-20260626T215051Z/source_text_qra_coverage.json`
  reported `control_text_missing_or_stub=0` and `url_text_missing_or_stub=0`.
  `/mnt/storage12tb/skills/review-db/outputs/dewey-sessions/url-knowledge-missing-qdrant-20260626T215023Z/after_rescan.json`
  reported `before_count=0`, `after_count=0` for
  `missing-qdrant-embeddings` on `sparta_url_knowledge`.

Do not point production cron directly at this directory. The active cron target
is the monitor-sparta supervisor/router, which may dispatch Dewey for
Dewey-owned lanes. Cron promotion for broader mutating lanes still requires
lane-specific proof receipts.
