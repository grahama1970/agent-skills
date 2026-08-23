# Scope update from Battle gap review

WebGPT reviewed the local Battle immutable-goal gap analysis in Ask run
`one-shot-oneshot-3728fa94-webgpt`.

Ask receipt:

```text
/mnt/storage12tb/skills/ask/outputs/.ask_artifacts/tau-dag-runs/one-shot-oneshot-3728fa94-webgpt/node-artifacts/handler-webgpt/node-receipt.json
```

The review says this ticket should own objective replay acceptance, not only the
first-viewport `pause_after_round` banner.

Expanded required outcome for this issue:

- the adaptive-lineage Pixi route shows source run and bundle identity;
- the visible replay shows current round, parent/child relation, evaluation,
  feedback, material child change, and selection/outcome;
- `pause_after_round` is treated as `NOT_APPLICABLE` only when the fixture schema
  proves it is not required; otherwise missing backend data fails closed;
- malformed, tampered, hash-mismatched, missing, or wrong-run source bundles do
  not play and do not substitute stale data;
- fresh screenshots/video are inspected, not only DOM assertions;
- this issue runs after #1500 binds Pixi to the durable backend receipt from
  #1499.

Plain status: this is the usable replay-game blocker after backend receipt
binding. #1502 should not duplicate this work.
