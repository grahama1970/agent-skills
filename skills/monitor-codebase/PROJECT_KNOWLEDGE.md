# Project Knowledge: monitor-codebase

**Last updated:** 2026-04-29 12:14 by agent
**Status:** Active development

## Current Understanding

- Project initialized, knowledge tracking started
- 2026-04-29: monitor-codebase now emits a Fallow-style schema_version 2 report contract. Full scans and audits normalize scanner outputs into findings[] with verdict, summary.by_source, summary.by_rule, summary.by_severity, actions[], evidence, and remediation_route.
- Changed-file audits are first-class via run.sh audit <project> [--base REF]. Audit mode filters file-scoped findings to changed files while preserving repo-level findings such as embedding coverage.
- Embedding coverage is now part of monitor-codebase health: embedding_coverage.py compares expected script files against Qdrant-synced code_symbols for scope monitor-<project> and emits normalized embedding findings when coverage is incomplete.

## Recent Decisions

| Date | Decision | Why |
|------|----------|-----|
| 2026-04-29 | Initialize project knowledge | Enable shared human/agent context |
| 2026-04-29 | Use Fallow-style finding contract v2 for monitor-codebase reports | The pipeline now composes many scanners; a stable schema with normalized findings and pass/warn/fail verdicts gives /orchestrate, /code-runner, dashboards, PR comments, and humans one contract to consume. |

## Open Questions

- [ ] Should `scan --fix` consume normalized `remediation_route` entries directly when skills-ci has no fix plan?
- [ ] Should PR comments render top normalized findings instead of only summary counts?

## Key Files

| File | Purpose |
|------|---------|
| PROJECT_KNOWLEDGE.md | Shared project knowledge |
| fallow_contract.py | Normalizes quality, best-practices, security, duplication, dependency, coverage, embedding, and skills-ci outputs into the Fallow-style report contract. |
| monitor-output-schema.json | JSON schema for schema_version 2 monitor-codebase reports. |
| embedding_coverage.py | Audits expected script files against Qdrant-synced code_symbols records. |
| run.sh | Runs full scans, changed-file audits, aggregation, trend tracking, and optional remediation workflow. |

## Infrastructure State

<!-- Auto-populated from /project-state --quick -->
