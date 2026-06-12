# Read-Only Preflight Fanout Recipe

Use this recipe when one artifact needs independent read-only inspection before
a single producer or verifier step. This is bounded preflight, not a general DAG
runtime.

## Prompt shape

```text
$loop inspect <artifact objective> with two or three read-only explorers before producing the artifact.

Spawn the read-only explorers before waiting.
Wait for each explorer, save each receipt, and close each handle.
Join their findings into one bounded implementation or artifact task.
Do not claim true runtime overlap unless an explicit proof asks for it.
```

## Node sequence

```text
explorer-a(read_only) + explorer-b(read_only) -> join findings -> worker/write step -> verifier(read_only)
```

The fanout is allowed only for read-only nodes. The join is a parent-owned
summary of receipts, not a new scheduler.

## Concurrency

Read-only handles may be spawned before the first wait when the prompt asks for
it. Write-capable parallelism remains forbidden unless an outer orchestrator
provides isolated worktrees or disjoint output paths.

## Verifier rule

The joined findings are evidence, not approval. PASS still requires the final
fresh verifier receipt plus any deterministic checks required by the prompt.

## Receipt type

For ordinary artifact completion, use the existing loop receipt for the final
artifact. For the narrow handle-lifecycle proof only, use
`concurrency-proof.v1`.
