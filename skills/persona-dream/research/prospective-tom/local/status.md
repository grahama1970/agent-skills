# Status

Status: ACCEPTED

Artifact: PCTOM-R Gate 2 ToM belief-distribution invariant checker.

Candidate:

```text
scripts/check_tom_belief_distributions.py
schemas/tom_belief_distribution.v1.schema.json
schemas/tom_belief_distribution_bundle.v1.schema.json
fixtures/gate2/positive/distributions_ok/tom_belief_distribution_bundle.json
fixtures/gate2/negative/*/tom_belief_distribution_bundle.json
```

Inspection result:

```text
1 positive ToM distribution bundle passed
3 distributions checked
2 supported hypotheses matched Gate 1 labels
1 unsupported hypothesis abstained with UNKNOWN certainty
7 targeted negative bundles failed closed
0 live calls
0 memory writes
0 provider calls
```

Reason accepted:

The artifact mechanically checks the requested Gate 2 research-lane chain:

```text
Gate 1 social episode
-> visible evidence refs
-> first-/second-order ToM labels
-> sealed probability distributions
-> no canonical memory write
```

Can be used by:

- a Tau text-call trial runner;
- a future condition runner for M/R/D/CD;
- a future seal/reveal scoring checker.

Next legal move:

Implement Gate 3 counterfactual branch contracts and ensure counterfactual
branches remain marked synthetic before any condition runner persists them.
