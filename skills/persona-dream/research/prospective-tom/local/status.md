# Status

Status: ACCEPTED

Artifact: PCTOM-R Gate 3 counterfactual branch invariant checker.

Candidate:

```text
scripts/check_counterfactual_branches.py
schemas/counterfactual_intervention.v1.schema.json
schemas/counterfactual_branch_bundle.v1.schema.json
fixtures/gate3/positive/branches_ok/*
fixtures/gate3/negative/*/counterfactual_branch_bundle.json
```

Inspection result:

```text
1 positive Gate 3 branch bundle passed
2 branches checked
1 factual branch
1 counterfactual branch
1 intervention
4 resolved source evidence refs
2 BDI distribution refs
6 targeted negative bundles failed closed
0 live calls
0 memory writes
0 provider calls
```

Reason accepted:

The artifact mechanically checks the requested Gate 3 research-lane chain:

```text
Gate 1 social episode
-> visible evidence refs
-> sealed factual/counterfactual ToM distributions
-> factual branch
-> synthetic counterfactual do() branch
-> no canonical memory write
```

Can be used by:

- a Tau text-call trial runner;
- a future condition runner for M/R/D/CD;
- a future seal/reveal scoring checker.

Next legal move:

Implement Gate 4 sealed prediction commitments that consume Gate 3 branches and
prove predictions are hash-bound before outcome reveal.
