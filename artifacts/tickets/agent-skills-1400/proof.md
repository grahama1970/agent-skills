# Ticket #1400 Proof

Issue: Ask WebGPT lane stalls in sentinel extraction after accepted Battle prompt

## Diagnosis

The Battle WebGPT request reached the real browser lane, selected `webgpt`, bound a
ChatGPT tab, and submitted the prompt. After the parent Ask run was interrupted,
the worker classified the terminal state as `missing_sentinel` and launched a
long `webgpt.extract` recovery command that could outlive the cancelled run.

Representative diagnostic artifacts:

- Run directory: `/mnt/storage12tb/skills/ask/outputs/battle-webgpt-diagnosis-20260813/ask-tau-create-a-comprehensive-battle-ag-bd0a1689a59d`
- Provider preflight: `/tmp/ask-browser-availability-webgpt-fresh-20260813.json`
- Browser lifecycle: `browser-tab-lifecycle.json`, tab `837389526`
- Inflight receipt: `node-artifacts/handler-webgpt/webgpt_inflight.json`
- Recovery packet after interruption: `node-artifacts/handler-webgpt/browser-recovery-packet.json`

## Fix

`skills/ask/scripts/tau_roundtable_worker.py` now classifies Surf/browser handler
return codes `143` and `-15` as `browser_handler_interrupted`, marks them
non-retryable, and skips in-run recovery with a reason that the recovery would
outlive the cancelled Ask run.

This is intentionally narrow: it prevents a cancelled run from being mislabeled
as a provider/sentinel defect and from spawning a stale extractor. It does not
claim that the original long Battle eval request now semantically completes.

## Deterministic Checks

```text
uv run --project skills/ask python -m pytest -q \
  skills/ask/tests/test_browser_failure_recovery.py::test_webgpt_unverified_clean_output_is_quarantined_not_tab_identity_retry \
  skills/ask/tests/test_browser_failure_recovery.py::test_interrupted_webgpt_submit_is_not_missing_sentinel \
  skills/ask/tests/test_tau_roundtable_sanity_eval.py::test_worker_lane_recovery_skips_interrupted_submit \
  skills/ask/tests/test_tau_roundtable_sanity_eval.py::test_worker_lane_recovery_never_retries_provider_refusal
Result: 4 passed in 0.81s

python3 -m py_compile skills/ask/scripts/tau_roundtable_worker.py
Result: exit 0

uv run --project skills/ask python -m pytest -q \
  skills/ask/tests/test_browser_failure_recovery.py \
  skills/ask/tests/test_tau_roundtable_sanity_eval.py \
  -k 'interrupted or lane_recovery or missing_sentinel or browser_handler_timeout or unverified_clean_output'
Result: 8 passed, 96 deselected in 1.10s

python3 scripts/check_mock_evidence_claims.py
Result: OK: checked 670 test file(s); no mock+proof claim violations

git diff --check -- \
  skills/ask/scripts/tau_roundtable_worker.py \
  skills/ask/tests/test_browser_failure_recovery.py \
  skills/ask/tests/test_tau_roundtable_sanity_eval.py
Result: exit 0
```

## Live Ask/WebGPT Smoke

Command:

```text
cd skills/ask
./run.sh tau-dag "Reply with exactly: TICKET_1400_WEBGPT_OK" \
  --repo grahama1970/agent-skills \
  --target ticket-1400-webgpt-live-smoke \
  --immutable-goal "Prove Ask WebGPT still completes a small live single-call with raw, clean, meta, and node receipt artifacts after interrupted-lane recovery handling changed." \
  --dag-template single-call \
  --handler webgpt \
  --execute \
  --browser-tab-lifecycle fresh-keep \
  --run-output-root /mnt/storage12tb/skills/ask/outputs/ticket-1400-live-proof-20260813 \
  --poll-timeout-seconds 180 \
  --browser-lock-timeout 900 \
  --json
```

Result:

- Run directory: `/mnt/storage12tb/skills/ask/outputs/ticket-1400-live-proof-20260813/ask-tau-reply-with-exactly-ticket-1400-w-3dde91b65654`
- DAG receipt: `tau-receipts/dag-receipt.json`
- DAG status: `PASS`
- DAG live: `true`
- DAG mocked: `false`
- Handler receipt: `node-artifacts/handler-webgpt/node-receipt.json`
- Handler status: `PASS`
- Handler live: `true`
- Handler mocked: `false`
- Handler provider live: `true`
- Transport: `$surf` `webgpt.submit`
- Submit status: `completed`
- Submit proof status: `response_proven`
- Submitted to ChatGPT: `true`
- Raw contains sentinel: `true`
- Clean contains sentinel: `false`
- Focus invariant: `true`
- Transport degraded: `false`
- Response path: `node-artifacts/handler-webgpt/response.md`
- Clean response includes `TICKET_1400_WEBGPT_OK`

## Evidence Boundary

- mocked: no for the live smoke; yes only for unit-level synthetic failure tests.
- live: yes for the Ask/WebGPT smoke through Surf and ChatGPT.
- proves: cancelled/interrupted browser handlers are classified as
  `browser_handler_interrupted`, do not auto-retry, and do not spawn an in-run
  extractor; the patched worker still completes a small live WebGPT call.
- does not prove: the original long Battle adaptive-lineage eval suite has been
  answered by WebGPT, nor that Battle itself is complete.
