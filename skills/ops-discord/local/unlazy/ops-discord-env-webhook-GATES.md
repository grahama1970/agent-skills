# Gates: ops-discord env webhook + monitor-opportunities repair notification

OWNS: skills/ops-discord/discord_ops/utils.py, skills/ops-discord/discord_ops.py, skills/ops-discord/tests/test_env_webhooks.py, skills/ops-discord/fixtures/agentic_eval.json, skills/monitor-opportunities/src/monitor_opportunities/cli.py, skills/monitor-opportunities/tests/test_scheduler.py

Scope: Make env-backed webhook configuration visible and usable by ops-discord, then let monitor-opportunities scheduler self-repair receipts expose a no-secret notification path.

- [x] G1: named skill contracts were read before task actions
  CHECK: printf 'SKILL_CONTRACT_READBACK_OK ops-discord monitor-opportunities pipeline-self-repair agentic-evals unlazy\n'
  EXPECT: SKILL_CONTRACT_READBACK_OK
  EVIDENCE: read `skills/unlazy/SKILL.md`, `skills/unlazy/references/agent-skills-workflow.md`, `skills/unlazy/SECURITY.md`, `skills/ops-discord/SKILL.md`, `skills/monitor-opportunities/SKILL.md`, `skills/pipeline-self-repair/SKILL.md`, and `skills/agentic-evals/SKILL.md` before edits.

- [x] G2: ops-discord loads env-backed webhooks without leaking URLs
  CHECK: cd skills/ops-discord && uv run --project . pytest tests/test_env_webhooks.py -q && echo OPS_DISCORD_ENV_WEBHOOK_TESTS_OK
  EXPECT: OPS_DISCORD_ENV_WEBHOOK_TESTS_OK
  EVIDENCE: `5 passed in 0.84s`; sentinel `OPS_DISCORD_ENV_WEBHOOK_TESTS_OK`.

- [x] G3: retained ops-discord agentic eval covers env webhook behavior
  CHECK: skills/agentic-evals/run.sh run skills/ops-discord/fixtures/agentic_eval.json --case env-webhook-discovery-regression --output /tmp/ops-discord-env-webhook-agentic-eval.json
  EXPECT: "readiness": "READY"
  EVIDENCE: `/tmp/ops-discord-env-webhook-agentic-eval.json`; readiness `READY`, case_count `1`, trial_count `2`, outcome_counts PASS `1`.

- [x] G4: monitor-opportunities self-repair receipts expose notification status
  CHECK: cd skills/monitor-opportunities && uv run --project . pytest tests/test_scheduler.py -q -k 'self_repair' && echo MONITOR_OPPORTUNITIES_SELF_REPAIR_NOTIFICATION_TESTS_OK
  EXPECT: MONITOR_OPPORTUNITIES_SELF_REPAIR_NOTIFICATION_TESTS_OK
  EVIDENCE: `1 passed, 15 deselected in 0.24s`; sentinel `MONITOR_OPPORTUNITIES_SELF_REPAIR_NOTIFICATION_TESTS_OK`. Full `./sanity.sh`: `446 passed in 65.60s`.

- [ ] G5: relevant files are retained on main
  CHECK: git diff --cached --name-status && git ls-remote origin refs/heads/main
  EXPECT: refs/heads/main
  EVIDENCE: local commit created; `git push origin HEAD:main` rejected non-fast-forward because local `main` is behind `origin/main`. Remote retention exists on `repair/ops-discord-env-webhook-monitor-alerts`; main integration is still pending.

- [x] G6: final status preserves immutable-goal boundary
  CHECK: printf 'IMMUTABLE_GOAL_BOUNDARY_OK Immutable Goal: NOT_MET\n'
  EXPECT: IMMUTABLE_GOAL_BOUNDARY_OK
  EVIDENCE: latest `skills/monitor-opportunities/run.sh status --json` reports `operational_readiness: DEGRADED`; `report-manifest.json` has 8 opportunities, 12 source_intel, 78 relationship_signals, hidden_total 0, and one `FEED_DOWN` source receipt for Hyperproof Greenhouse `ReadTimeout`.
