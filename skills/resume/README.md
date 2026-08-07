# Resume skill

The `resume` skill provides a small, deterministic boundary around the repository's
canonical `RESUME.md`: validate the source, compile evidence-bound variants, and hand
those artifacts to `/monitor-opportunities`.

It deliberately leaves opportunity research, communication, and application effects
to the opportunity-monitoring skill. No claim may enter a variant without an approved
claim record and at least one evidence reference.

Use `./run.sh --help` for the command surface and `./sanity.sh` for the local smoke
gate.
