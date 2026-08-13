# Proof For agent-skills#1397

Ticket: https://github.com/grahama1970/agent-skills/issues/1397

## Change

Ask browser-provider selection now treats a provider as unusable when its
availability probe reports a degraded state with a recovery packet that sets
`auto_retry_allowed: false`.

This prevents the #1397 failure mode where WebGPT had:

- `provider_limited: false`
- `probe_degraded: true`
- `failure_code: browser_provider_probe_timeout`
- `auto_retry_allowed: false`

but was still selected, so Tau dispatched toward WebGPT and no handler artifacts
were produced.

## Deterministic Tests

Command:

```bash
uv run --project skills/ask python -m pytest -q \
  skills/ask/tests/test_browser_provider_selection_probe_state.py \
  skills/ask/tests/test_tau_dag.py \
  -k 'browser_provider_selection or browser_availability'
```

Result:

```text
16 passed, 81 deselected in 4.27s
```

Mock-evidence claim checker:

```bash
python3 scripts/check_mock_evidence_claims.py
```

Result:

```text
OK: checked 623 test file(s); no mock+proof claim violations
```

## Live Non-Mocked Ask/WebGPT Proof

Command:

```bash
cd skills/ask
./run.sh tau-dag "Create a comprehensive Battle agentic-evals suite specification from the attached context. Return the requested structured headings and sentinel." \
  --repo grahama1970/agent-skills \
  --target battle-comprehensive-agentic-evals-ticket-1397-proof \
  --immutable-goal "Produce a comprehensive Battle agentic-evals suite specification covering Arena creators, Red, Blue, Judge, selection, adaptive lineage, replay, memory claims, V16 fail-closed gates, negative/adversarial controls, fixture schemas, validator interfaces, and first implementation slices without claiming local proof." \
  --dag-template single-call \
  --handler webgpt \
  --attach-file /tmp/battle-comprehensive-agentic-evals-webgpt-20260813/battle-comprehensive-agentic-evals-request.md \
  --execute \
  --browser-tab-lifecycle fresh-keep \
  --run-output-root /mnt/storage12tb/skills/ask/outputs/ticket-1397-live-proof-20260813 \
  --poll-timeout-seconds 120 \
  --browser-lock-timeout 900 \
  --json
```

Result:

- process exit code: `4`
- top-level status: `NEEDS_ATTENTION`
- live: `true`
- mocked: `false`
- provider_live: `false`
- removed_seats: `["webgpt"]`
- execution status: `NEEDS_ATTENTION`
- execution failure_code: `browser_provider_probe_timeout`
- execution no_tau_execution: `true`

Run directory:

`/mnt/storage12tb/skills/ask/outputs/ticket-1397-live-proof-20260813/ask-tau-create-a-comprehensive-battle-ag-b33f13da4a09`

Artifact inventory summary:

```text
file_count 11
browser-provider-availability.json True 95424
browser-provider-selection.json True 2093
provider-gate.json True 375
selection_status BLOCKED
selection_failure_code browser_provider_probe_timeout
selection_removed_handlers ['webgpt']
selection_active_handlers []
selection_unusable_providers {'webgpt': 'browser_provider_probe_timeout'}
handler_artifact_dirs []
```

## What This Proves

- Ask no longer dispatches into a WebGPT provider whose availability probe is
  degraded and explicitly not retryable.
- The caller receives a terminal Ask result with `NEEDS_ATTENTION`,
  `browser-provider-selection.json`, `failure_code`, `removed_seats`, and
  `no_tau_execution: true`.
- No WebGPT handler node was launched in the live proof; there were no handler
  artifact directories.

## What This Does Not Prove

- It does not prove WebGPT prompt submission works.
- It does not prove the Battle eval-suite response was obtained.
- It does not repair stale unrelated WebGPT submit processes; it prevents this
  Ask path from silently dispatching into the degraded lane.
