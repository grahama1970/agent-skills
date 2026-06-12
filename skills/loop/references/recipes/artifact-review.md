# Artifact Review Recipe

Use this recipe when the artifact is not code: a prompt contract, evidence case,
test plan, report section, extraction fixture, or similar bounded output.

## Prompt shape

```text
$loop produce <artifact> at <path>.

Use explorer to inspect source material and acceptance criteria.
Use coder as the producer to create or revise only the requested artifact.
Use code-reviewer as a fresh read-only verifier against the criteria.

Repair until verifier returns PASS or 3 attempts are used.
```

## Node sequence

```text
explorer(read_only) -> coder(write) -> code-reviewer(read_only)
```

The `coder -> code-reviewer` edge may repeat until verifier PASS, BLOCKED, or
max attempts.

## Concurrency

Default execution is sequential. Optional read-only preflight fanout may be used
only when it directly improves inspection coverage for the same artifact.

## Verifier rule

The verifier must review the actual artifact file and any deterministic check
outputs. A producer self-assessment is not a PASS.

## Receipt type

Use the existing loop receipt unless the project defines a narrow specialized
receipt for the artifact type. Do not introduce a generic DAG receipt for this
recipe.
