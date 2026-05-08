# Project Knowledge: agent-skills

**Last updated:** 2026-05-08 13:58 by agent
**Status:** Active development

## Current Understanding

- Project initialized, knowledge tracking started
- The /plan -> /review-plan -> /orchestrate -> /code-runner pipeline is now usable for bounded source-mutating code tasks when the plan opts into complete-task mode with apply_to_source=true, commit_on_success=true, rollback_on_failure=true, tight allowlist/read_context, visible DoD, and real blind_tests. Live E2E pass path was proven through /orchestrate -> /code-runner -> /scillm -> /test-lab with codex/gpt-5.5 high in session /mnt/storage12tb/artifacts/agent-skills/orchestrate/structured/session-1777913254. Hidden-test failure rollback was proven in session /mnt/storage12tb/artifacts/agent-skills/orchestrate/structured/session-1777913299; source commits were reverted and the repo ended clean.
- 2026-05-08 other-project adoption hardening adds an explicit adoption contract, AGENTS snippet, external-project adoption smoke, scheduled/manual CI adoption smoke, pipeline_readiness --include-adoption-smoke, and browser-rendered project infographic source. Opaque code-runner DoD commands such as make/npm/scripts now require an explicit local-only metadata contract: dod_scope=worktree_local, requires_network=false, requires_live_server=false, browser_required=false, opaque_command_reviewed=true.

## Recent Decisions

| Date | Decision | Why |
|------|----------|-----|
| 2026-05-04 | Initialize project knowledge | Enable shared human/agent context |
| 2026-05-04 | Use explicit complete-task mode for reliable source-mutating code-runner tasks | Patch-only remains safest by default, but controlled source mutation is reliable when /plan and /review-plan enforce apply_to_source=true, commit_on_success=true, rollback_on_failure=true, /orchestrate runs real /test-lab blind checks after source commit, and failed blind checks are reverted. |
| 2026-05-08 | Require adoption smoke and opaque DoD metadata for other projects | Other project agents need a portable PASS gate before using source-integrating plan-to-code-runner workflows, and opaque shell commands can hide live/browser/network checks unless the plan declares and reviewers audit the local-only DoD contract. |

## Open Questions

- [ ] What are the key architectural decisions?
- [ ] What are the known issues?

## Key Files

| File | Purpose |
|------|---------|
| PROJECT_KNOWLEDGE.md | Shared project knowledge |

## Infrastructure State

<!-- Auto-populated from /project-state --quick -->
