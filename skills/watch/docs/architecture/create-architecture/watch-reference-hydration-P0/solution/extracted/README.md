# watch-reference-hydration-P0-solution

This bundle contains a scoped implementation-ready architecture package for Watch Reference Hydration P0.

Apply by copying `repo/` into the repository root:

```bash
cp -a repo/. /path/to/agent-skills/
```

Then run the commands in `COMMANDS.md`.

Main contents:

- `ARCHITECTURE.md` — complete architecture and implementation contract.
- `repo/skills/watch/docs/architecture/watch_reference_hydration_P0.md` — same contract at repo-relative destination.
- `repo/skills/watch/docs/architecture/schemas/*.schema.json` — schemas/API contracts.
- `repo/skills/watch/docs/architecture/state_machines/*.json` — state machine.
- `repo/skills/watch/scripts/*.py` — stdlib-only P0 helpers and CLIs.
- `repo/skills/watch/tests/*.py` and fixtures — deterministic contract tests.
- `ROLLBACK_REBUILD.md` — rollback/rebuild instructions.
- `prompt_improvements.md` — next-turn request improvements.

No file in this package claims live identity, Qdrant/Arango writes, memory persistence, or `$memory recall` proof.
