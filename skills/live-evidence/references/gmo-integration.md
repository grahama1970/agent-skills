# Graph Memory Operator Integration

Live Evidence consumes Graph Memory Operator only through the supported Memory
service and sibling `memory/run.sh` CLI. It never imports ArangoDB or Qdrant
clients and never writes vectors independently.

## Live query path

1. `POST /intent` with the current finalized interviewer turn.
2. Use the returned `recall_profile` when it is a valid profile identifier.
3. Always retain `procedural_memory` and `temporal_project_state` as bounded
   fallback profiles.
4. `POST /recall` with the profile's explicit collection allowlist.
5. Use `memory/run.sh code-search` for exact lexical code anchors.
6. Resolve the strongest symbol through `memory/run.sh code-node --source` so
   the card receives current/stale source-hash evidence.
7. Use allowlisted fixed-string ripgrep only when current source is needed or
   GMO is unavailable.

## Recommended future GMO profile

A first-class GMO profile can improve ranking without changing this skill's
contract:

```python
"live_interview_evidence": RecallProfileSpec(
    name="live_interview_evidence",
    description="Current public-safe project, career, proof, and code evidence for a live professional conversation.",
    weights={
        "exact_entity_match": 0.20,
        "bm25": 0.20,
        "semantic": 0.20,
        "graph_multihop": 0.15,
        "freshness": 0.15,
        "proof_strength": 0.10,
    },
    collections=[
        "project_memory_active",
        "project_states",
        "project_activity",
        "project_knowledge",
        "lessons_v2",
        "tau_orchestration_episodes",
        "dogpile_research",
        "code_symbols",
    ],
    required_artifacts=["source_locator", "project_identity", "freshness_or_commit"],
    reranker_mode="cache",
    k=8,
    depth=2,
)
```

This snippet is a design handoff, not an applied GMO change. Until the deployed
service exposes that profile, `/intent` selection plus existing fallback
profiles remain authoritative.

## Code projection preflight

Keep the interview repositories indexed before the call:

```bash
skills/ingest-code/run.sh ensure-current \
  --repo /path/to/tau \
  --branch main \
  --commit "$(git -C /path/to/tau rev-parse HEAD)" \
  --path README.md \
  --json
```

For a broader refresh on a clean canonical checkout:

```bash
skills/ingest-code/run.sh scan /path/to/repo --treesitter --code-index
```

Live Evidence treats stale code-node responses as lower-confidence evidence and
keeps the stale qualification visible.
