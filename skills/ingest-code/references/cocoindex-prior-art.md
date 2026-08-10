# CocoIndex Prior Art Boundary

This note pins the bounded comparison used by
`skills/ingest-code/evals/cocoindex-incremental`.

## Pinned Dependency

- Package: `cocoindex`
- Version: `1.0.19`
- Wheel: `cocoindex-1.0.19-cp311-abi3-manylinux_2_28_x86_64.whl`
- Wheel SHA-256:
  `a7f3e398f5aef8fb6dfe032730dc2995ef46e6a0941511eab0e5845eee3a04ba`
- Installed package-code SHA-256 used by the offline fixture runner:
  `b7fc2e19d191f8490c0665f1e6419e8ec70333f0b6a9495333679130dc2e0897`

## Evaluation Boundary

CocoIndex is evaluated only as an internal scheduler/cache candidate. It is not
canonical Memory state, not a retrieval authority, and not a production
dependency of `ingest-code`.

The adapter may use `@coco.fn(memo=True)` and an isolated LMDB path to schedule
parsing work. It must emit the existing backend-neutral ingest-code code-graph
bundle shape and must not write ArangoDB, Qdrant, Memory, agent configuration,
or indexed source repositories.

The native arm remains the current file-component cache:

- source fingerprint
- transform fingerprint set
- serialized symbol components
- component hash
- accepted complete-bundle gate

The comparison is valid only when both arms run against copied fixtures, produce
complete bundles, preserve deletion semantics and idempotence, and emit
machine-readable receipts.
