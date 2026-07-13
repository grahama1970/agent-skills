# Battle V14 Durable Memory Proof

This bundle archives the fresh non-mocked `battle-004-adaptive-memory-v14-r6`
run. Its authority chain is:

```text
retained V13 selection and Judge evidence
-> Battle memory promotion receipts
-> live Memory /upsert
-> live Memory /recall
-> team-isolated Tau/SciLLM handoffs
-> provider memory-use acknowledgements
-> Docker compile/review/handoff
-> Judge
```

The top-level receipt is `adaptive-memory-canary-receipt.json`. `SHA256SUMS`
binds every archived file. Verify from the repository root with:

```bash
sha256sum -c skills/battle/local/battle-004-adaptive-memory-v14/SHA256SUMS
```

Evidence summary:

```text
mocked=false
live=true
memory promotions=2 PASS
memory writes=2 PASS
memory recalls=2 PASS
provider use acknowledgements=2 PASS
Docker artifact pipelines=2 PASS
Judge pairs=1 PASS
Judge verdict=BLUE_SUCCESS
```

This proves bounded durable write, later recall, demonstrated provider use, and
execution of the resulting artifacts. It does not prove memory-service ACLs,
performance improvement, Red exploit success, or population-scale learning.
