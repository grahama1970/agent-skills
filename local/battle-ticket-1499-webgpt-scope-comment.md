# Scope update from Battle gap review

WebGPT reviewed the local Battle immutable-goal gap analysis in Ask run
`one-shot-oneshot-3728fa94-webgpt`.

Ask receipt:

```text
/mnt/storage12tb/skills/ask/outputs/.ask_artifacts/tau-dag-runs/one-shot-oneshot-3728fa94-webgpt/node-artifacts/handler-webgpt/node-receipt.json
```

The review says this ticket should own the whole backend closure family, not
only copying a recovered qualification JSON into a durable path.

Expanded required outcome for this issue:

- execute the current backend from parent generation through evaluation,
  child derivation, child execution, and lineage selection;
- produce one atomic durable bundle with `run_id`, schema, code commit, command,
  receipt identities, ordered hashes, and a no-fallback assertion;
- prove at least one feedback-caused, non-noop child change;
- prove same-run lineage integrity and deterministic replay;
- reject modified receipt, missing lineage edge, duplicate receipt identity,
  schema mismatch, reordered sequence where order matters, and bundle assembly
  from different run IDs;
- regenerate `CURRENT_STATUS.json` from the accepted bundle;
- preserve recovered `battle-004` evidence as a regression fixture, not as the
  current closure artifact.

Plain status: this is the main backend blocker for the Battle immutable goal.
Closing this issue requires causal adaptive-generation proof, not only durable
receipt persistence.
