# Handoff Report: project-watchdog V2

**Timestamp**: 2026-09-15T11:46:22Z
**Active Agent**: Codex

## 1. Project Overview

- **Ecosystem**: Python CLI, Bash launcher, GitHub CLI, native Pi subagents; the handoff detector reports `Unknown` because this V2 directory has no current project manifest.
- **Core Purpose**: A cron-driven, one-ticket-at-a-time GitHub repair loop. `tick --apply` selects a ticket, claims an owned lease, runs one native Pi fixer/reviewer workflow, executes configured trusted proof, then closes only on success or releases the lease and cools down on failure.

## 2. Current State (Doc-Code Alignment)

- **Documented Features**: `SKILL.md` documents `status`, `tick`, state control, cron installation, failure triage, and draft/active workflow editing.
- **Implemented Reality**: `run.sh` dispatches to `scripts/watchdog_v2.py` and `scripts/watchdog_workflow_cli.py`. The controller checks the owned lease, native reviewer result, configured proof, and GitHub close read-back. Its failure path attempts lease release, sets cooldown, classifies, and writes a receipt.
- **Drift/Misalignments**: `README.md`, `CONTEXT.md`, `ARCHITECTURE.md`, and much of the earlier V1 code/UI are currently deleted in the dirty checkout; there is no current `01_TASKS.md`. Treat `SKILL.md` and V2 source as the live contract, and do not restore those deletions without the operator's direction. The skill documents an editor URL, but no editor UI was verified during this handoff.
- **Operational State**: `run.sh status` read back global `paused`, reason `Production #1688 native workflow failure under triage`; `crontab -l` still shows the `*/15` V2 tick. Scheduled invocations are expected to return `paused` until state is explicitly changed. This report did not resume production.

## 3. What is Working Well

- The retained `/agentic-evals` receipt `/mnt/storage12tb/skills/project-watchdog/outputs/agentic-eval-project-watchdog-after-b25-authority.json` reports `READY`, 6/6 cases, 12 trials, `mocked=false`, `live=true`, including cron-shaped real-ticket, native workflow, editor graph, admission guard, and historical false-close cases. This is a prior-run receipt, not a fresh production tick.
- Current code read-back confirms the controller fails closed before proof/close when the native workflow or reviewer fails, and `_fail` records triage, lease release, and cooldown. `run.sh status` and `crontab -l` worked in this handoff.

## 4. What is Currently Broken

- **Failed Tests**: None run during this documentation-only handoff. The prior V2 eval is green; it does not prove the current #1688 repair succeeded or that the timer runs indefinitely.
- **Known Issues**: `gh issue view 1688 --repo grahama1970/agent-skills` read back `OPEN`, with `agent-work` and without `agent-active`. The isolated retry receipt `/mnt/storage12tb/skills/project-watchdog/work/retry-1688-one-final/receipts/20260915T035714Z-battle-b25-retry-1688.json` says `outcome=failure`, `failed_stage=workflow`, and `lease_release.released=true`; its triage code is `project_watchdog_unclassified_1f51020d`.
- **Recent Regression / Review Finding**: Retained reviewer artifacts `/tmp/pi-subagents-uid-1000/artifacts/9f48d0e2-8813-4220-bc96-f73826c3282e_reviewer_output.md` and `/tmp/pi-subagents-uid-1000/artifacts/6b1d1a3e-8370-4194-9c91-4b46a55e55f3_reviewer_output.md` both flag a P1 in `skills/battle/src/battle_skill/team_artifact_pipeline.py`: `_retained_response_errors` checks file hash but does not parse/gate retained `TIMEOUT`, `QUOTA`, `MALFORMED_RESPONSE`, or `CANCELLED` status; `scillm_call_receipt_sha256` is only checked for presence; `annotate_tau_authoring_route_receipts` preserves an existing retained binding via `setdefault`. The current source read-back still shows these behaviors. Some Battle source and tests are already unstaged; preserve and inspect them before any repair.

## 5. Next Steps

1. **Resume Here**: Keep Watchdog global state paused. Read the #1688 retry receipt, both reviewer artifacts, and the current unstaged Battle diff. Verify retained response status and binding through the production Battle/Tau path with a negative TIMEOUT/QUOTA/CANCELLED case. Do not infer success from a green unit test or from the older Watchdog eval.
2. After a focused fix and owning Battle `/agentic-evals` live proof, rerun one isolated #1688 workflow and read back its native result, receipt, lease/labels, and GitHub issue state. Only resume the 15-minute Watchdog tick after the failure is resolved and the operator accepts production reactivation.
3. Reconcile the deleted legacy docs/code with the V2 `SKILL.md` when the operator decides whether those deletions should be retained. No restore or broad cleanup is part of this handoff.

## 6. Project Context for Success

- **Key Files**: `skills/project-watchdog/SKILL.md`; `run.sh`; `scripts/watchdog_v2.py`; `scripts/watchdog_graph.py`; `scripts/watchdog_workflow_cli.py`; `registry/projects.json`; `workflows/watchdog-v2.json` (active) and `watchdog-v2.draft.json` (draft); `fixtures/agentic_eval.json`; `skills/battle/src/battle_skill/team_artifact_pipeline.py` for #1688.
- **Recent Changes**: `e9912d1156` introduced V2 cron lifecycle; `4777c26ff9` fixed production registry and graph checks; `bbdf834aed` guarded active-ticket admission; `514cb5bf5f` scoped repairs in dirty checkouts. Repo-head `4f8fe64afc`, `ef0d892160`, and `107763bbdc` changed Battle B25 Tau routing and authority receipts. These SHAs are context, not proof of #1688 success.
- **Proof Boundary**: This handoff used live `status`, `crontab -l`, `gh issue view`, source reads, and retained receipt/artifact reads; mocked: no new mock run; live: read-backs only, no new production tick. The prior Watchdog eval reports live cases, but current #1688 end-to-end success and unattended timer behavior remain unverified.
- **Checkout**: Primary checkout `/home/graham/workspace/experiments/agent-skills`, branch `main`; `git status -sb` has extensive pre-existing changes. Stage only handoff-specific paths if committing.
