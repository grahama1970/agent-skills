---
name: project-dream
description: Build and gate shadow project-memory synthesis candidates from frozen evidence packets.
disciplines: [memory-governance, backend-python, agentic-evaluation]
---

# project-dream

`project-dream` turns one frozen `project_dream_evidence_packet.v1` into shadow-only project-memory candidates and validates them deterministically before any staging attempt.

## Commands

```bash
./run.sh synthesize --packet packet.json --model opencode-go/model-id --output candidate.json --command-spec command.json --json
./run.sh validate-candidate --packet packet.json --candidate candidate.json --output validation.json --json
./run.sh stage-candidate --candidate candidate.json --validation validation.json --json
```

## Boundaries

- `synthesize` requires one packet, one explicit resolved provider/model id, and an injectable command spec. It runs without a shell, records prompt/input/raw-output hashes, and marks the run `exclude_from_learning=true`.
- `validate-candidate` is LLM-free and fail-closed. It rejects unresolved or hash-mismatched evidence, authority inversions, cross-project refs, self-citation, secret-like output, stale machine evidence, mutation-budget excess, direct database/project-file mutation requests, and model attempts to emit active memory.
- `stage-candidate` only calls the `memory` skill wrapper: `project-memory stage --packet ... --json`. If that wrapper is unavailable or changes the active head, staging is blocked.

Default mode is shadow-only. This skill never promotes memory, rewrites project files, or calls Graph Memory, ArangoDB, Qdrant, Git, or network services directly.
