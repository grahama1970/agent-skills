# Persona-dream local proof ladder: agent guidance

## Canonical name

Call this script the **persona-dream local serial proof runner** or **local DAG-shaped smoke runner**.

Do **not** call it `ScillmDagHarness`, Dreamer orchestration, or an end-to-end persona-dream harness. The runner validates a small graph and executes graph nodes one at a time in deterministic topological order.

## Required claim language

| Rung | A passing run supports | It does not support |
|---|---|---|
| `fixture` | Local scheduler wiring, event writing, state writing | Persona-dream or `$scillm` claims |
| `scillm-one` | One loopback HTTP request and one exact parsed-JSON contract sample | Deterministic model generation, provider readiness, network isolation |
| `scillm-two-concurrent` | Exactly two client requests released together, one receipt per item, and overlapping client request intervals | DAG-node concurrency or server-side parallelism |
| `real-gates` | Only the selected real gate receipts on the named run root | Panel, WebGPT, Kling, voice, Dreamer, or provider readiness unless separately executed and evidenced |
| `scillm-one-plus-real-gates` | The union of the preceding one-call and selected-gate claims | Any broader orchestration claim |

## Network wording

A `$scillm` rung performs a **real local service call**. Use these receipt meanings:

- `local_scillm_call_authorized: true`
- `external_provider_call_authorized: false`
- `paid_call_authorized: false`
- `network_isolation_proven: false`

“Not authorized” is policy metadata. It is not proof of network isolation. The script restricts the configured `$scillm` endpoint to loopback and disables HTTPX environment-proxy use, but it does not sandbox every subprocess network path.

## Run order

```bash
# 1. Reconfirm the one-call transport contract.
export SCILLM_API_KEY=<local-proxy-token>  # only if the local proxy requires it
.venv/bin/python scripts/medium_loop_dag_smoke.py \
  --rung scillm-one \
  --stream-json

# 2. Next rung: exactly two concurrent client calls, no real gates.
.venv/bin/python scripts/medium_loop_dag_smoke.py \
  --rung scillm-two-concurrent \
  --stream-json

# 3. Cheap real gates, separately.
.venv/bin/python scripts/medium_loop_dag_smoke.py \
  --rung real-gates \
  --stream-json
```

Do not add `--include-panel-repair` or `--include-voice-clone` to either `$scillm`-only rung.

## Evidence checklist for the two-call rung

The run is usable only when all of these are true:

1. `proof-summary.json` has `status: PASS` and rung `scillm-two-concurrent`.
2. `scillm-two-concurrent-probe-receipt.json` has `call_count: 2`.
3. Both item statuses are `PASS`.
4. Two distinct item receipt files exist.
5. `client_request_intervals_overlap` is `true` and overlap is positive.
6. The endpoint is loopback and the model is the intended model.
7. No gate, panel, WebGPT, voice, or Kling node appears in `graph.yaml`.

## Review rule

Quote the `proof_scope`, `claims.proves`, and `claims.does_not_prove` fields from the run summary in every handoff. Never infer a broader claim from a green terminal status.
