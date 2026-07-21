# Status

Status: ACCEPTED

Artifact: PCTOM-R Gate 1 deterministic social episode corpus.

Candidate:

```text
scripts/build_social_episode_corpus.py
scripts/check_social_episode_corpus.py
fixtures/gate1/development/social_episode_corpus.v1.json
schemas/social_episode.v1.schema.json
```

Inspection result:

```text
12 development episodes built
4 scenario families represented
3 episodes per family
12 first-order ToM labels
12 second-order ToM labels
1 negative mutation failed closed
0 live calls
0 memory writes
0 provider calls
```

Reason accepted:

The artifact mechanically checks the requested Gate 1 research-lane chain:

```text
hidden world state
-> deterministic counterpart policy
-> actual next action
-> first-order ToM label
-> second-order ToM label
```

Can be used by:

- a Tau text-call trial runner;
- a future condition runner for M/R/D/CD;
- a future seal/reveal scoring checker.

Next legal move:

Implement the Gate 2 distribution invariant checker that consumes a social
episode and rejects unsupported or malformed ToM belief distributions before
any condition runner exists.
