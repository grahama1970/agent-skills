# Status

Status: ACCEPTED

Artifact: PCTOM-R Gate 0 lineage checker slice.

Candidate:

```text
contracts/prospective_tom_protocol.v1.md
schemas/*.v1.schema.json
scripts/check_prospective_tom_protocol.py
fixtures/gate0/positive/lineage_ok
fixtures/gate0/negative/*
```

Inspection result:

```text
1 positive fixture passed
4 negative fixtures failed closed
0 live calls
0 memory writes
0 provider calls
```

Reason accepted:

The artifact mechanically checks the requested Gate 0 research-lane chain:

```text
recall receipt
-> accepted source ID
-> normalized residue
-> dream branch
-> sealed ToM prediction
```

Can be used by:

- a later deterministic social-world simulator;
- a Tau text-call trial runner after it writes the same commitment contract;
- a future seal/reveal scoring checker.

Next legal move:

Implement the text-first social episode corpus builder as a separate artifact
under the same research namespace.
