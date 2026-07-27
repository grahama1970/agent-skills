# Project-State Current Knowledge

Last updated: 2026-07-27

`project-state` is a reporting and readiness skill. It may inspect local project
state, companion skill availability, and cleanup receipts, but it must not move,
delete, restore, reset, or otherwise mutate project files.

## Current Contract

- `./run.sh report` generates a project state report.
- `./run.sh report --quick --json` is the narrow smoke profile.
- `./run.sh report --cleanup-tail --cleanup-receipt <receipt.json> --json
  --output artifacts/cleanup/project_state_after.json` is the preferred
  cleanup-tail entrypoint.
- `./run.sh cleanup-tail --cleanup-receipt <receipt.json>` is a compatibility
  alias that writes the same
  `skill.readiness_report.v1` artifacts under
  `artifacts/project-state/readiness/<run-id>/`.
- `./run.sh config doctor --json` reports missing non-secret configuration
  without prompting.
- Standard mode is local/bounded. Full mode may use current external retrieval
  skills: `/brave-search`, `/github-search`, and `/arxiv`. `/dogpile` is legacy
  deep aggregation and should not be the default freshness path.
- Cleanup-tail reads local `.cleanup-evidence.json` and `.ingest-code.json`
  status when source-like cleanup candidates exist. These artifacts are
  evidence context only; they do not authorize deletion or prove backend
  embedding coverage.
- Cleanup-tail treats `project_knowledge_sync` and `memory_sync` as
  not-established unless the cleanup receipt records them.

## Cleanup Tail Safety

Cleanup-tail is intentionally evidence-only. A successful cleanup-tail report
means the cleanup receipt was readable and a quick state snapshot was captured.
It does not establish release readiness and does not authorize deletion of
`.cleanup` contents. Moved, quarantined, or manual-review items remain
`needs_attention` until separate usage evidence is checked.

## Known Gaps

- The historical default report is still Embry-oriented because the collectors
  target Embry paths and daemon names.
- Release readiness is not established by the quick profile or cleanup-tail
  profile.
- Full reports may depend on live companion skills such as `/memory` and
  `/dogpile`.
- Cleanup-tail can identify missing project-knowledge and memory sync evidence,
  but it does not write lessons itself.

## Validation

Run these before claiming skill work is ready:

```bash
python3 skills/best-practices-skills/scripts/validate_skill.py skills/project-state --skills-root skills
./skills/project-state/sanity.sh
```
