# DBA Auditor Self-Improvement Loop

This is the steering contract for Dewey/DBA Auditor after every substantial
audit. It converts review lessons into deterministic next-session behavior.

## Loop Boundary

DBA Auditor is a read-only reviewer by default. Its self-improvement loop may
update or propose updates to local auditor knowledge and candidate memory
records.

In **authorized database session commit/revert** mode only, Dewey may mutate
Arango through `agents/dba-auditor/scripts/db_repair_session.py` after session
`begin` commits a backup. Regression auto-reverts from that session dump only.
Outside that mode it must not mutate Arango, Qdrant, monitor state, GitHub
issue state, or canonical `persona_memory`.

## Inputs

Each audit session must produce a receipt JSON or report JSON with these fields:

- `memory_recall_query`
- `memory_recall_summary`
- `monitor_memory_summary_or_not_needed`
- `monitor_sparta_summary_or_not_needed`
- `external_research_summary_or_not_needed`
- `github_ticket_contract_summary_or_not_needed`
- `completed_task_assessment`
- `what_i_learned`
- `changed_or_recommended_agent_contract_rules`
- `memory_upsert_candidates`
- `next_audit_checklist_delta`
- `brave_search_used_or_not_needed`

## Deterministic Gate

Run:

```bash
python agents/dba-auditor/scripts/verify_self_improvement.py \
  --receipt <audit-receipt.json> \
  --print-json
```

The verifier returns:

- `PASS` when every required section is present and non-empty.
- `NEEDS_CHANGES` when the receipt is parseable but missing loop fields.
- `BLOCKED` when the receipt cannot be parsed or the target is missing.

## Steering Steps

1. Preflight: verify the receipt path exists and parses as JSON.
2. Measure: check every required self-improvement field.
3. Gate: fail if any required field is absent or empty.
4. Adjust: if the gate fails, the next audit response must add the missing
   fields before any readiness or handoff claim.
5. Persist: update or propose updates to:
   - `agents/dba-auditor/PROJECT_KNOWLEDGE.md`
   - `agents/dba-auditor/memory-upsert-candidates.jsonl`
6. Handoff: if the finding requires repository repair, prepare a
   `best-practices-github-ticket` packet with target, route, requested outcome,
   required proof, non-goals, and closure non-claims.

## Stop Conditions

- `PASS`: receipt can be consumed by the project agent.
- `NEEDS_CHANGES`: project agent must repair the receipt or rerun the auditor
  with the missing sections named by the verifier.
- `BLOCKED`: missing receipt, invalid JSON, denied permission, or source
  evidence unavailable.

## Non-Claims

Passing this loop proves only that Dewey emitted the required self-improvement
steering fields. It does not prove database health, recall health, trainer
readiness, GitHub issue closure, or canonical memory upsert.

## Database Session Commit/Revert (Dewey repair mode)

Git semantics for ArangoDB repair sessions:

| Git | Dewey |
|-----|-------|
| `git status` | `monitor-sparta health --json` + corpus counts |
| `git commit` | `db_repair_session.py begin` → baseline + `ops-arango dump` |
| `git diff` / CI | `db_repair_session.py verify` → post health + counts |
| `git revert` | `db_repair_session.py revert <session_dir>` (session dump only) |

Full mechanical loop:

```bash
python agents/dba-auditor/scripts/db_repair_session.py repair \
  --command 'SPARTA_MONITOR_MUTATION_ENABLED=1 uv run python scripts/validation/monitor_sparta.py health --fix'
```

Session artifacts: `/mnt/storage12tb/skills/review-db/outputs/dewey-sessions/<session_id>/`

Regression triggers auto-revert: collection count decrease, controls below minimum,
monitor pass-count decrease, `corpus_completeness` regression, memory `/health` not ok.

Semantic failures (QRA generation, descriptions) → queue to monitor-sparta lanes;
do not loop until 29/29 green in one session.

Optional receipt fields (not gated by verifier): `database_session_dir`,
`session_backup_receipt`, `baseline_health_summary`, `reverted`.
## QRA Landscape Audit (required when SPARTA QRAs in scope)

```bash
python agents/dba-auditor/scripts/audit_qra_landscape.py --manifest-limit 50
```

Report separately:
- direct/canonical coverage gaps (`qra_missing_generation_required`)
- relationship/control-to-control backlog (`gated_pairs_pending`)
- adversarial-retained rows (exclude from direct coverage)
- create-evidence-case SATISFIED band on **labeled** subsets only (~10-15% healthy for mixed/adversarial banks)

Do not conflate "245k QRAs" with "controls covered" — most rows are not per-control canonical coverage.
## SPARTA Dataset Improvement Opportunities

Dewey is not only a fault detector. On SPARTA scope, produce a ranked improvement backlog:

```bash
python agents/dba-auditor/scripts/sparta_dataset_opportunities.py --manifest-limit 50
```

Each opportunity should name: id, kind (mechanical/semantic/verification), owner lane, scale, and action.
Mechanical opportunities may proceed via `db_repair_session.py` after backup; semantic opportunities queue to monitor-sparta lanes.
## Overnight Morning Report (required)

After overnight scans, render the human morning readout:

```bash
python agents/dba-auditor/scripts/render_overnight_morning_report.py
# or reuse latest scan artifacts:
python agents/dba-auditor/scripts/render_overnight_morning_report.py --skip-scans
```

Human opens: `/mnt/storage12tb/skills/review-db/outputs/dewey-morning-reports/latest/report.html`
## Human Nightly Focus (subagent_memory)

Humans tell Dewey what to prioritize for the next overnight monitor-sparta pass:

```bash
# After /ask conversation
python agents/dba-auditor/scripts/dewey_nightly_focus.py store \
  --objective 'Focus on EMB3D ingestion and control-to-control QRA backlog' \
  --lanes qra_generation,framework_ingestion \
  --health-dimensions qra_coverage_per_control

# Or from ask artifacts
python agents/dba-auditor/scripts/dewey_nightly_focus.py from-ask --ask-run-id <ask_id>

# Overnight recall
python agents/dba-auditor/scripts/dewey_nightly_focus.py active
```

Stored in `$memory` → `subagent_memory` with `record_type: nightly_focus_directive`.

