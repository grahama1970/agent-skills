# Project Knowledge: skill-maintainer

**Last updated:** 2026-06-13 08:14 by agent
**Status:** Active development

## Current Understanding

- Project initialized, knowledge tracking started
- Maintainer-local crash resume card: the repo root PROJECT_KNOWLEDGE.md remains the global project projection; this file tracks only skill-maintainer queue state, terminal blockers, artifact roots, and next stop conditions.

Current live queue snapshot from 2026-06-12 15:45 EDT: issue #3 is OPEN with maintainer-active and is waiting on maintainer merge/pull disposition for the ask/surf WebGPT recovery patch; issue #5 is OPEN with maintainer-blocked and needs-human after local repair/verifier/review receipts passed but the external WebGPT review timed out.

Last crash-boundary artifact for issue #5: /home/graham/workspace/experiments/agent-skills/.artifacts/skill-maintainer/20260612T174050Z/issue-5/cycle-result.json. WebGPT failure artifact: /home/graham/workspace/experiments/agent-skills/.ask_artifacts/webgpt-review/webgpt-review-20260612T175750Z/status.json.

Resume rule: do not reconstruct status from memory alone. Read this file, then the named cycle-result/status artifacts, then GitHub labels/comments before leasing or closing any issue.
- Issue #3 disposition on 2026-06-12 16:00 EDT: closed after pushed commit e69b2fde34538044c4cc4def412b05e8b94c835d on origin/feat/webgpt-no-activate. GitHub disposition comment: https://github.com/grahama1970/agent-skills/issues/3#issuecomment-4694840305. Deterministic proof commands recorded in /home/graham/workspace/experiments/agent-skills/.artifacts/skill-maintainer/issue-3-disposition-20260612T200000Z/github-comment.md. The maintainer-active label was removed from #3 after close. Remaining open queue: #4 scheduler/coordinator bug and #5 blocked controlled live mutation proof.
- Issue #4 status on 2026-06-12 16:15 EDT: local scheduler patch evidence collected, but #4 must remain open because the external WebGPT reviewer gate is BLOCKED with `missing_sentinel`. Patch surface adds scheduler `load --json`, parseable `run --json`, per-run stdout/stderr/result artifacts, persisted `last_run_artifacts`, and focused scheduler CLI tests. Local proof artifact: /home/graham/workspace/experiments/agent-skills/.artifacts/skill-maintainer/issue-4-scheduler-proof-20260612T200945Z/issue-status.md. WebGPT blocked status: /home/graham/workspace/experiments/agent-skills/.ask_artifacts/webgpt-review/issue-4-scheduler-proof-20260612T200945Z/status.json. Production skill-maintainer cron remains disabled pending review recovery and explicit production-enable policy.
- Issue #4 parking on 2026-06-13: #4 remains open and local scheduler changes are parked, not committed or closed, while WebGPT reliability tickets are filed. Parking artifact: /home/graham/workspace/experiments/agent-skills/.artifacts/skill-maintainer/issue-4-scheduler-proof-20260612T200945Z/parked-status-20260613.md.
- WebGPT reliability issues filed on 2026-06-13: #6 (https://github.com/grahama1970/agent-skills/issues/6) covers browser target state, stale tab id, and duplicate ChatGPT URL safety across browser-oracle/surf/ask. #7 (https://github.com/grahama1970/agent-skills/issues/7) covers missing-sentinel timeout/recovery, advisory output, and no false PASS. Do not treat filing these issues as E2E proof. Do not run skill-maintainer for them unless explicitly requested.
- Next maintainer target policy: continue existing queue order (#4/#5) by default. Escalate #6 ahead of the queue only if stale/ambiguous WebGPT targeting blocks review evidence. Escalate #7 only if missing-sentinel behavior causes hangs, false-green risk, or prevents review evidence. If both are escalated, fix #6 before #7 because safe browser targeting is upstream of reliable sentinel recovery.
- WebGPT reliability E2E slice on 2026-06-13: #6 was escalated as an explicit workflow test input and run through skill-maintainer with --github-dry-run, --dispatch-subagents, and --subagent-command-fixture. Status artifact: /home/graham/workspace/experiments/agent-skills/.artifacts/webgpt-reliability-e2e-20260613/project-agent-final-status.json. Maintainer artifact dir: /home/graham/workspace/experiments/agent-skills/.artifacts/skill-maintainer/20260613T130454Z/issue-6. Result is pending at WebGPT/closure wiring, not fixed/closed. The run exposed a route mismatch: #6 was inferred as design_or_ux with designer/qa-tester, but the ticket is ask/surf/browser-oracle runtime work. Before a real repair run, add explicit target paths/route metadata or fix maintainer route inference. GitHub #6 remained open and unchanged.
- WebGPT reliability E2E route correction on 2026-06-13: #6 now has explicit ## Target paths, ## Maintainer route backend_python_or_skill_runtime, and ## Requested repair agent coder. Focused proof command `pytest -q scripts/tests/test_skill_maintainer_cycle.py -k 'route_metadata or target_skills'` returned 3 passed / 38 deselected. Corrected maintainer dry-run artifact dir: /home/graham/workspace/experiments/agent-skills/.artifacts/skill-maintainer/20260613T131155Z/issue-6. Corrected route selects coder, project-or-harness-verifier, code-reviewer and target_skills ask/surf/browser-oracle. Current status artifact: /home/graham/workspace/experiments/agent-skills/.artifacts/webgpt-reliability-e2e-20260613/project-agent-final-status-v2.json. Status remains pending at real repair/WebGPT gate: no source patch, deterministic #6 regression tests, real $ask artifacts, or closure/disposition comment.
- Real #6 maintainer attempt on 2026-06-13: isolated clean worktree /tmp/agent-skills-issue6-e2e-real at f61a908a6 launched real Codex repair with --github-dry-run and no command fixture. Artifact dir: /tmp/agent-skills-issue6-e2e-real/.artifacts/skill-maintainer/20260613T131555Z/issue-6. Session skill-maintainer-issue-6-repair-aefcb8ed completed exit_code=0 and produced patch/proof artifacts copied to /home/graham/workspace/experiments/agent-skills/.artifacts/webgpt-reliability-e2e-20260613/real-run-issue6/. Current blocker: worker receipt uses status=repaired, but maintainer receipt_gate accepts status=completed; continuation recorded observed_repair_status=repaired and stayed waiting_for_repair_receipt, so verifier/review/WebGPT did not run. Current status artifact: /home/graham/workspace/experiments/agent-skills/.artifacts/webgpt-reliability-e2e-20260613/project-agent-final-status-v3.json. Resume by reconciling receipt schema, then continue the isolated issue dir.
- Final #6 E2E workflow proof on 2026-06-13: maintainer receipt-gate contract was repaired to accept well-formed status=repaired repair receipts, result=pass verifier/review receipts, and real WebGPT execution under github_dry_run without GitHub disposition. Focused runner tests returned 26 passed / 22 deselected; full scripts/tests/test_skill_maintainer_cycle.py returned 48 passed. The isolated run /tmp/agent-skills-issue6-e2e-real/.artifacts/skill-maintainer/20260613T131555Z/issue-6 advanced through repair, verifier, review, and real $ask WebGPT. WebGPT run webgpt-review-20260613T133914Z completed with PASS, blocking_findings=[], controlled_tab_id=837352352, raw_contains_sentinel=true, focus_changed=false. Current status artifact: /home/graham/workspace/experiments/agent-skills/.artifacts/webgpt-reliability-e2e-20260613/project-agent-final-status-v4.json. This is not issue closure: #6 remains open with 0 comments, and the isolated repair patch is not applied to the main dirty worktree.
- Full non-mocked #6 E2E closure on 2026-06-13: branch fix/issue-6-webgpt-tab-recovery was pushed with commit 2d6d745a725d2c8e45c180e1914716410c3aabfe. GitHub #6 received evidence comment https://github.com/grahama1970/agent-skills/issues/6#issuecomment-4698710095 and was closed at 2026-06-13T13:51:35Z. Final artifact: /home/graham/workspace/experiments/agent-skills/.artifacts/webgpt-reliability-e2e-20260613/project-agent-final-status-v5-full-real-e2e.json. Deterministic proof: targeted WebGPT tab tests 23 passed in 16.13s, skill_maintainer_cycle tests 41 passed in 0.13s, git diff --check no output. Repair/verifier/review subagent sessions all completed exit_code=0. WebGPT reviewer run webgpt-review-20260613T133914Z completed PASS with blocking_findings=[] but was reviewer evidence only.

## Recent Decisions

| Date | Decision | Why |
|------|----------|-----|
| 2026-06-12 | Initialize project knowledge | Enable shared human/agent context |
| 2026-06-12 | Maintain a skill-maintainer-local PROJECT_KNOWLEDGE.md | Repo-root PROJECT_KNOWLEDGE.md is global and too broad for crash recovery; the maintainer needs a nearby resume card with active GitHub leases, terminal blockers, artifact roots, and next stop conditions. |

## Open Questions

- [ ] What are the key architectural decisions?
- [ ] What are the known issues?

## Key Files

| File | Purpose |
|------|---------|
| PROJECT_KNOWLEDGE.md | Skill-maintainer crash-resume card |
| ../../PROJECT_KNOWLEDGE.md | Repo-level shared project knowledge |
| ../../.artifacts/skill-maintainer/ | Repo-root maintainer run artifacts |

## Infrastructure State

<!-- Auto-populated from /project-state --quick -->
