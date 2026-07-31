# Issue 1065 Live Memory Lineage Proof

Ticket: <https://github.com/grahama1970/agent-skills/issues/1065>

## Commands

```bash
cd skills/battle
uv run --project . python -m pytest \
  tests/test_adaptive_lineage_engine.py \
  tests/test_adaptive_lineage_memory.py \
  tests/test_adaptive_lineage_verified_primitives.py \
  tests/test_adaptive_lineage_oracles.py -q
```

Result: `25 passed in 0.14s`.

```bash
./skills/battle/run.sh prove-adaptive-lineage-live-memory \
  --out /home/graham/workspace/experiments/agent-skills-issue1049-20260728/skills/battle/local/issue-1065-live-memory-proof \
  --run-id issue-1065-live-20260728T1718 \
  --timeout-s 90 \
  --population-size 2 \
  --recall-attempts 8 \
  --recall-sleep-s 5
```

Result: `status=PASS`, `mocked=false`, `live=true`.

## Primary Receipts

- Summary: `skills/battle/local/issue-1065-live-memory-proof/proof-summary.json`
- Summary SHA-256: `42e78a9f91f8be5cce3432ccce65d29e35ddc6be9cd98f2d5d1852c647fd59ae`
- Memory health: `skills/battle/local/issue-1065-live-memory-proof/memory-health.json`
- Memory health SHA-256: `9bc431732f20156b7c005c5a3860c3e41c1c857392da25847ad21eb461eaa89f`

## Evidence Summary

- Live Memory daemon: `http://127.0.0.1:8601`, collection `battle_lineage_graph`.
- Docker image: `python:3.12-slim`.
- Red and Blue each ran generation 1 and generation 2 receipts.
- Red survivor store ack: `stored=true`, key `battle-lineage:issue-1065-live-20260728T1718:issue-1065-lineage:red:g0001:survivor:4a658aa02324efa501743158`.
- Blue survivor store ack: `stored=true`, key `battle-lineage:issue-1065-live-20260728T1718:issue-1065-lineage:blue:g0001:survivor:693f00df7e0917622fdf6789`.
- Red upsert ack: `inserted=1`, `errors=[]`.
- Blue upsert ack: `inserted=1`, `errors=[]`.
- Red next-generation recall found the owning Red survivor on attempt 2.
- Blue next-generation recall found the owning Blue survivor on attempt 2.
- Negative controls: `red_leaked_to_blue=[]`, `blue_leaked_to_red=[]`.

The proof summary records Memory's noisy daemon recalls and the adapter's fail-closed quarantine of forbidden returned items in `dropped_forbidden_item_ids`; those documents did not enter the generation context.
