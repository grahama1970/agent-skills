# Handoff Report: monitor-opportunities

**Timestamp**: 2026-08-17T15:57:54Z
**Active Agent**: Codex
**Canonical workspace**: `/home/graham/workspace/experiments/agent-skills`
**Branch observed**: `main` at `1c04b6d890ad6c9767894a80e51a9ee37d66a35e`

## 1. Project Overview

- **Ecosystem**: Python skill with shell entrypoints, Typer CLI, JSON schemas, pytest
  tests, and local report artifacts.
- **Core purpose**: Nightly, human-in-the-loop opportunity monitor for Graham Anderson.
  It researches targeted employment, federal/defense, commercial contract, and
  relationship/reconnect signals; ranks a small eligible set; prepares claim-bound
  resume/application/outreach artifacts; and renders one morning report/interview.
- **Immutable goal**: Daily top opportunities that are highly targeted, delivered in an
  interactive report/interview, with human-authorized application preparation using a
  custom targeted resume and evidence-backed `screening_interface_profile`.
- **Safety boundary**: Current stage is `STAGE_0_RESEARCH_ONLY`. `external_effects` must
  remain `false`. No auto-apply, auto-submit, auto-send, LinkedIn automation, Gmail send,
  or autonomous ATS mutation.

## 2. Current State (Doc-Code Alignment)

Current readbacks:

- `./skills/monitor-opportunities/run.sh status --json` returned:
  - `stage: STAGE_0_RESEARCH_ONLY`
  - `operational_readiness: NOT_ESTABLISHED`
  - `external_effects: false`
  - `not_implemented_commands: []`
  - 27 implemented commands, including `run`, `nightly`, `apply`,
    `tau-semantic-prepare`, `tau-semantic-provider-eval`, `report-acceptance`, and
    `scheduler-exec-check`.
- `python3 scripts/check_tree_fresh.py --path skills/monitor-opportunities` returned:
  `tree freshness: branch main, 1 ahead / 0 behind origin/main` and
  `OK: working tree matches HEAD for the checked path`.
- No `.pi/skills/handoff/run.sh` runner exists in this repository, so this handoff uses
  direct repository inspection and local commands as the fallback.

Doc-code alignment:

- `README.md` says the nightly is operational and scheduled, but `status --json` still
  reports `operational_readiness: NOT_ESTABLISHED`. Treat run-specific receipts as local
  evidence only; do not infer complete cron or immutable-goal readiness from prose.
- `docs/PROJECT_KNOWLEDGE.md` is the most current project context. Its top section
  correctly records the current red sanity state caused by stale discovery fixture dates.
- `PROJECT_STATE.md` is dated `2026-08-12` and explicitly says it is not rolling context.
  Use it only as historical assessment metadata.
- Previous `local/HANDOFF.md` snapshots contained superseded guidance around relationship
  expansion. This file now leads with the current 2026-08-17 command evidence.

## 3. What is Working Well

- Local Stage 0 report-kernel verification passed:
  `./skills/monitor-opportunities/run.sh verify --out /tmp/monitor-opportunities-handoff-verify-20260817T155639Z`
  wrote `/tmp/monitor-opportunities-handoff-verify-20260817T155639Z/verification-receipt.json`.
- That receipt reports:
  - `overall: PASS`
  - `live: true`
  - `mocked: false`
  - `network_used: false`
  - `external_effects: false`
  - 9/9 fixture cases passing.
- The passing verification cases cover:
  - valid Stage 0 report rendering
  - hidden action artifact rejection
  - feed failure mislabeled as no-match rejection
  - relocation-required shortlist rejection
  - sendable outreach rejection in Stage 0
  - ATS authorization rejection in Stage 0
  - sensitive/free-text autofill rejection
  - shortlist cap rejection
  - unknown source status rejection
- Current status shows the command surface is implemented rather than placeholder-only:
  `not_implemented_commands: []`.
- The tree freshness guard is present and working for this path. Run it before future
  edits or proof claims:
  `python3 scripts/check_tree_fresh.py --path skills/monitor-opportunities`.

## 4. What is Currently Broken

### Failed Tests

`./skills/monitor-opportunities/sanity.sh` is red:

- Result: `17 failed, 406 passed in 65.09s`.
- Shared failure signature: the committed discovery fixture under
  `skills/monitor-opportunities/tests/fixtures/discovery/` has aged out of the two-week
  recency window. Fixture runs produce zero shortlisted opportunities, so downstream
  tests fail when they expect report-visible opportunities, tailoring receipts,
  application packets, Gmail outreach packets, or Tau semantic inputs.

Failing test files/functions observed:

- `tests/test_buzz_review.py::test_buzz_summary_emits_ops_buzz_message_dry_run`
- `tests/test_claim_snapshot_binding.py::test_report_claim_artifacts_share_one_snapshot_digest`
- `tests/test_cli.py::test_apply_requires_exact_report_visible_packet`
- `tests/test_cli.py::test_apply_blocks_unresolved_human_required_fields`
- `tests/test_eligibility.py::test_rank_is_stable_and_caps_shortlist`
- `tests/test_pipeline.py::test_run_creates_one_report_and_receipt`
- `tests/test_pipeline.py::test_run_with_linkedin_contact_evidence_renders_second_degree_signal`
- `tests/test_pipeline.py::test_run_renders_reviewed_gmail_draft_receipt`
- `tests/test_report_acceptance.py::test_report_acceptance_fails_shortlist_overflow`
- `tests/test_report_acceptance.py::test_report_acceptance_fails_authorized_or_effectful_application_packet`
- `tests/test_report_visibility.py::test_loopback_service_decisions_replay_and_visibility`
- `tests/test_tau_semantic_prepare.py::test_tau_semantic_prepare_writes_validated_inputs`
- `tests/test_tau_semantic_prepare.py::test_tau_semantic_prepare_includes_direct_relationship_evidence`
- `tests/test_tau_semantic_prepare.py::test_tau_semantic_prepare_rejects_meetup_primary_input`
- `tests/test_tau_semantic_provider.py::test_tau_semantic_install_projects_addendum_into_interview_page`
- `tests/test_visibility_accounting.py::test_authoritative_shortlist_cap_prevents_hidden_downstream_ids`
- `tests/test_visibility_accounting.py::test_prior_applied_alias_dedupe_suppresses_downstream_artifacts`

### Known Issues

- The active test blocker is not a broad pipeline regression; it is a dated-fixture time
  bomb. Either freeze the test clock or generate fixture dates relative to the test run.
- `operational_readiness: NOT_ESTABLISHED` remains the authoritative status result until
  the readiness command changes and is read back.
- Stage 0 deliberately blocks ATS inspect/prefill/submit, Gmail mailbox draft/send, and
  LinkedIn handoff/automation. Do not treat those as broken unless the task is a scoped
  capability promotion.
- Repository-level working tree is heavily dirty outside `skills/monitor-opportunities`.
  Do not reset, stash, clean, or stage unrelated paths. Use path-scoped status/diff/add.

### Recent Regressions / Risk Notes

- `docs/PROJECT_KNOWLEDGE.md` documents a 2026-08-17 stale-working-tree incident where
  missing tracked files made a live run prove the wrong tree. Always run the freshness
  guard before testing or editing.
- Recent path-scoped commits:
  - `ce9ecfa451 monitor-opportunities: target AI, agentic pipelines, agentic extraction, R&D, robotics`
  - `07c99981a5 monitor-opportunities: stop local run artifacts from marking the skill tree dirty`
  - `8d055b3c43 monitor-opportunities: record current red sanity state and the stale-tree guard`
  - `eee45fb278 Restore project knowledge content dropped by a stale working tree`
  - `4b2b7e8ca7 monitor-opportunities: record relationship expansion lane in project knowledge`

## 5. Next Steps

1. Fix the dated discovery fixture failure family. Choose one invariant and apply it
   consistently:
   freeze time in affected tests, or make fixture dates relative to the test run.
2. Re-run `./skills/monitor-opportunities/sanity.sh` from the repo root and require
   the current `17 failed, 406 passed` signature to disappear.
3. Re-run `./skills/monitor-opportunities/run.sh status --json`; do not claim readiness
   until `operational_readiness` reflects the intended stage and the command explains the
   evidence behind that state.
4. Re-run the local verify receipt:
   `./skills/monitor-opportunities/run.sh verify --out /tmp/<fresh-dir>`.
5. Only after deterministic sanity is green, run the live Stage 0 path needed for the
   current acceptance rung, then bind the result to receipts and Memory/Buzz readbacks.
6. Keep external effects blocked unless a separate human-authorized capability promotion
   is explicitly requested and receipt-backed.

## 6. Project Context for Success

Key files:

- `skills/monitor-opportunities/SKILL.md` — immutable goal, stage authority, lanes,
  source/fallback policy, and no-auto-effect rules.
- `skills/monitor-opportunities/docs/PROJECT_KNOWLEDGE.md` — current implementation
  state and known red sanity cause.
- `skills/monitor-opportunities/src/monitor_opportunities/cli.py` — command surface,
  status output, nightly orchestration, and stage gates.
- `skills/monitor-opportunities/src/monitor_opportunities/pipeline.py` — run pipeline,
  required-source enforcement, API website fallback, ranking/tailoring/report flow.
- `skills/monitor-opportunities/src/monitor_opportunities/eligibility.py` and
  `ranking.py` — eligibility-before-ranking behavior.
- `skills/monitor-opportunities/src/monitor_opportunities/report.py` and
  `report_acceptance.py` — report rendering and visibility/acceptance checks.
- `skills/monitor-opportunities/src/monitor_opportunities/verification.py` — local
  Stage 0 verify receipt.
- `skills/monitor-opportunities/tests/fixtures/discovery/` — current failing fixture
  family.
- `skills/monitor-opportunities/tests/test_*` — broad pytest coverage; many failing tests
  currently share the stale-recency fixture root cause.

Working rules for the next agent:

- Start with `git status --short -- skills/monitor-opportunities` and
  `python3 scripts/check_tree_fresh.py --path skills/monitor-opportunities`.
- Do not use broad git cleanup in this repository.
- Do not touch external-effect capabilities unless explicitly authorized.
- Treat mocked/fixture checks as local wiring or deterministic contract evidence only.
- Treat live receipts as scoped to the specific run directory and source version.

Immutable Goal: NOT_MET
