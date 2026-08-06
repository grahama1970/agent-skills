# /ask roundtable live reliability — 2026-08-06

Non-deterministic reliability of the live multi-seat roundtable, measured by
running full `/ask tau-dag --workflow-mode roundtable --execute` runs through
Tau -> surf -> browser providers and judging each trial on DELIVERED output
(each seat's node receipt ok=true + non-empty response, read back from the
join receipt's seat_terminal_states). This is a live agentic measurement, NOT
a deterministic unit test.

## Result

- Configuration: seats = webgpt, webkimi; PASS iff BOTH deliver non-empty.
- Trials: 30 (6 + 24, sequential, live).
- Delivered: 30/30 trials; 48/48 spot-checked delivered seats non-empty
  (min 965 chars, 0 under-50-char).
- Point estimate: 100%.
- Wilson 95% lower bound: 88.6% >= 85%. BAR MET.

## Scope / honesty

- Measured lanes: webgpt + webkimi (the two roundtable browser lanes fixed
  and verified this session: webgpt delivery #1252/hardening, kimi #1138).
- NOT in this sample: webgemini (was among the original degraded-run
  failures); it needs its own measurement before any all-lane claim.
- Fixed prompt against provisioned fresh tabs; long-horizon variation
  (conversation-full, sustained rate limits) not exercised.

## Deterministic failure diagnosis (for when trials DO fail)

`scripts/diagnose_roundtable_run.py` walks a fixed decision tree over the
typed receipts: result status (NEEDS_INTERVIEW -> missing_fields; BLOCKED ->
blocked_reason/failure_code/next_command) -> join seat_terminal_states ->
per-seat failure_code -> recommended action. Reliability is stochastic; the
why-it-failed diagnosis is deterministic and repeatable.

## Reproduce

    export SCILLM_MASTER_KEY=<key from scillm .env>
    ROUNDTABLE_HANDLERS="webgpt webkimi" MIN_DELIVERED=2 \
      bash skills/ask/scripts/live_roundtable_reliability.sh 30
