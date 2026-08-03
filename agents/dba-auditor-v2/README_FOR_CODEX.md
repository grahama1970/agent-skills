# Dewey dba-auditor final code bundle

This bundle contains complete repo-relative code for the corrected Dewey subagent.
It is not another architecture-only handoff.

## Non-negotiable invariant

One cron activation must do at most one repair issue:

```text
cron -> dewey_issue_worker.py run -> claim one monitor-sparta queue issue -> run one Dewey-owned lane -> write receipt.json -> update queue -> exit
```

Do **not** reintroduce a broad loop around `monitor_sparta.py repair-cycle`.
`repair-cycle` is intentionally forbidden inside the lane runner and checked in tests.

## Files to copy

Copy these files repo-relative:

```text
agent-skills/agents/dba-auditor/scripts/dewey_repair_queue.py
agent-skills/agents/dba-auditor/scripts/dewey_lane_runner.py
agent-skills/agents/dba-auditor/scripts/dewey_issue_worker.py
agent-skills/agents/dba-auditor/scripts/dewey_overnight_run.py
agent-skills/agents/dba-auditor/scripts/dewey_nightly_cron.sh
agent-skills/agents/dba-auditor/tests/test_dewey_repair_queue.py
agent-skills/agents/dba-auditor/tests/test_dewey_lane_runner.py
agent-skills/agents/dba-auditor/tests/test_dewey_issue_worker.py
memory/scripts/validation/monitor_sparta_repair_queue.py
```

## What each file does

- `dewey_repair_queue.py`: append-only JSONL queue contract and deterministic issue claiming.
- `dewey_lane_runner.py`: dispatches exactly one Dewey-owned DBA lane; forbidden from `repair-cycle`.
- `dewey_issue_worker.py`: cron entrypoint; claim one issue, run one lane, write receipt, update queue.
- `dewey_overnight_run.py`: compatibility wrapper; delegates to the one-issue worker.
- `dewey_nightly_cron.sh`: cron-safe lock/log wrapper around the one-issue worker.
- `monitor_sparta_repair_queue.py`: monitor/memory helper that converts health JSON into durable repair queue entries.

## Expected queue path

Default:

```text
/mnt/storage12tb/media/agents/shared/monitor-sparta/repair_queue.jsonl
```

Override with:

```bash
export MONITOR_SPARTA_STATE_DIR=/path/to/monitor-sparta
export DEWEY_REPAIR_QUEUE=/path/to/repair_queue.jsonl
```

## Smoke tests

From `agent-skills/agents/dba-auditor`:

```bash
python3 -m pytest tests/test_dewey_repair_queue.py tests/test_dewey_lane_runner.py tests/test_dewey_issue_worker.py -q
python3 -m py_compile scripts/dewey_repair_queue.py scripts/dewey_lane_runner.py scripts/dewey_issue_worker.py scripts/dewey_overnight_run.py
```

This bundle was sanity-tested in isolation with:

```text
5 passed in 0.20s
```

## Manual queue build from health JSON

From the memory repo:

```bash
python3 scripts/validation/monitor_sparta_repair_queue.py enqueue \
  artifacts/latest_monitor_health.json \
  --queue /mnt/storage12tb/media/agents/shared/monitor-sparta/repair_queue.jsonl \
  --limit 200
```

Dewey can also bootstrap from read-only `monitor_sparta.py health --json` when the queue has no READY issue. That fallback is detection-only; it does not call `health --fix`.

## Manual Dewey dry run

```bash
python3 agent-skills/agents/dba-auditor/scripts/dewey_issue_worker.py run \
  --run-id dewey-smoke \
  --run-root /tmp/dewey-runs \
  --queue /tmp/repair_queue.jsonl \
  --memory-repo-root /home/graham/workspace/experiments/memory \
  --agent-skills-root /home/graham/workspace/experiments/agent-skills \
  --no-bootstrap \
  --json
```

## Apply mode

Cron apply mode is enabled unless `DEWEY_DRY_RUN=1` is set. The worker still refuses mutation if the claimed queue issue has `mutation_allowed=false`.

```bash
DEWEY_DRY_RUN=0 agent-skills/agents/dba-auditor/scripts/dewey_nightly_cron.sh
```

## QRA generation lane

`qra_coverage_per_control` is fail-closed unless the issue includes:

```json
{
  "requires_prompt_reviewer": true,
  "prompt_reviewer_receipt": "/path/to/receipt.json",
  "slice": {
    "manifest_path": "/path/to/create-qras-manifest.json",
    "limit": 1,
    "bucket": "gated_runnable"
  }
}
```

The lane runs create-qras review, dry-run, then canary only in apply mode. It does not synthesize a prompt-review receipt.

## Acceptance bar

A port is acceptable only when:

1. Unit tests above pass.
2. `receipt.json` is written for every worker invocation.
3. Receipt has `ran_more_than_one_lane=false`.
4. Receipt has `ran_repair_cycle=false`.
5. Queue issue status becomes `DONE`, `DRY_RUN_DONE`, `READY_RETRY`, `OPERATOR_REQUIRED`, or `FAILED_NEEDS_REVIEW`.
6. No inline `embedding`, `vector`, or related vector fields appear in Dewey artifacts.
