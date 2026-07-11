# persona-dream Pipeline

Each directory is one pipeline step. Steps communicate through machine-readable contracts in `../contracts/`.

```text
s01_idea/     → idea_contract.json
s02_memories/ → residue_links.json
s03_story/    → story_contract.json
s04_voice/    → voice_handoff_plan.json
s05_panels/   → panel images + receipts
s06_gate/     → gate_validation.json
s07_movie/    → provider packet + movie
```

## Rules

1. Each step consumes exactly one input contract and produces exactly one output contract.
2. Hardcoded persona/story details belong in `../fixtures/`, never in step code.
3. If `s06_gate` reports a contract violation, the orchestrator re-runs the offending step with a surgical correction.
4. Old script paths under `../scripts/` are temporary shims and will be removed once all callers are migrated.
