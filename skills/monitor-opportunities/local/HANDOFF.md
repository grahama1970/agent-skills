# Handoff Report: monitor-opportunities

**Timestamp**: 2026-08-30T14:35:00Z
**Active Agent**: Pi/Codex
**Canonical workspace**: `/home/graham/workspace/experiments/agent-skills`
**Target skill**: `skills/monitor-opportunities`
**Current status**: source adapters repaired for retained Slack/Discord/Gmail evidence, Discord bot readback, and mailbox-mining memory readback. Slack remains degraded until a Slack read token or retained Slack evidence file exists.

## Operator correction now binding

Tau is not decorative review. Tau exists to reduce model lying, laziness, evasiveness, and malicious/self-serving claims by making model output pass through immutable goals, receipts, validators, reviewers, and explicit evidence gates.

For `monitor-opportunities`, Tau/provider output is treated as an evidence-gated claim source. A human-facing Tau-live claim is accepted only when bound to a provider receipt. A naked `nightly-receipt.json` claim of Tau liveness with no provider receipt is a blocking truth-status failure.

## What changed in the source-adapter repair

Files changed:

```text
skills/monitor-opportunities/src/monitor_opportunities/discovery.py
skills/monitor-opportunities/src/monitor_opportunities/pipeline.py
skills/monitor-opportunities/src/monitor_opportunities/cli.py
skills/monitor-opportunities/src/monitor_opportunities/ranking.py
skills/monitor-opportunities/schemas/report.schema.json
skills/monitor-opportunities/tests/test_discovery.py
skills/monitor-opportunities/tests/test_report_visibility.py
skills/monitor-opportunities/scripts/tau_opportunity_eval_smoke.py
skills/monitor-opportunities/fixtures/agentic_eval.json
skills/monitor-opportunities/local/HANDOFF.md
```

Implemented behavior:

- `run` and `sweep` accept `--slack-evidence`, `--discord-evidence`, and `--gmail-evidence` retained read-only capture files.
- `MONITOR_OPPORTUNITIES_SLACK_EVIDENCE`, `MONITOR_OPPORTUNITIES_DISCORD_EVIDENCE`, and `MONITOR_OPPORTUNITIES_GMAIL_EVIDENCE` are consumed when explicit CLI evidence paths are absent.
- Slack can use `SLACK_BOT_TOKEN` or `SLACK_USER_TOKEN` for `conversations.history`; `SLACK_WEBHOOK_URL` is explicitly rejected as write-only for discovery.
- Discord can use `DISCORD_BOT_TOKEN` or `CLAWDBOT_TOKEN`, resolves the configured `horus` channel through `DISCORD_SERVER_ID`, and reads messages through Discord's channel messages endpoint.
- Gmail discovery uses `/memory /recall` over the `contacts` collection written by `/mailbox-mining`; it never calls a Gmail send/forward/schedule path.
- Slack/Discord/Gmail source capture records are ranked/rendered as source-intel only, not as employment opportunities or application authority.
- `report.schema.json` now accepts the new social/mail read-only automation policies.
- The false positive hardcoded-secret finding in `tests/test_report_visibility.py` was removed by avoiding a test variable pattern that matched `token\s*=\s*"...` across lines.
- The hardcoded Tau path in `scripts/tau_opportunity_eval_smoke.py` now defaults through `TAU_ROOT` with `~/workspace/experiments/tau` fallback.

## Verification readback

VERIFIED by `git rev-parse --show-toplevel && git branch --show-current && git status -sb`:

```text
repo=/home/graham/workspace/experiments/agent-skills
branch=main
```

VERIFIED by focused deterministic tests:

```bash
uv run --project skills/monitor-opportunities --extra test pytest \
  skills/monitor-opportunities/tests/test_discovery.py::test_sweep_uses_retained_social_and_mail_evidence_for_required_sources \
  skills/monitor-opportunities/tests/test_discovery.py::test_read_only_social_api_receipts_use_tokens_without_outbound_effects \
  skills/monitor-opportunities/tests/test_report_schema_runtime.py::test_report_schema_allows_mandatory_social_and_mail_source_receipts \
  -q
```

Readback:

```text
3 passed in 0.32s
```

VERIFIED by broader focused tests:

```bash
uv run --project skills/monitor-opportunities --extra test pytest \
  skills/monitor-opportunities/tests/test_discovery.py \
  skills/monitor-opportunities/tests/test_pipeline.py::test_diagnostic_run_degrades_required_source_gate_without_changing_strict_mode \
  skills/monitor-opportunities/tests/test_truth_status.py \
  -q
```

Readback:

```text
28 passed in 0.75s
```

VERIFIED by source-adapter agentic eval:

```bash
skills/agentic-evals/run.sh run skills/monitor-opportunities/fixtures/agentic_eval.json \
  --case social-and-mail-no-evidence-degrades-honestly \
  --case social-and-mail-retained-evidence-adapters \
  --case social-read-token-api-adapters \
  --case social-and-mail-report-schema-regression \
  --output /tmp/monitor-opportunities-source-adapters-agentic-eval-final.json
```

Readback from `/tmp/monitor-opportunities-source-adapters-agentic-eval-final.json`:

```text
readiness=READY
outcome_counts={PASS: 4, FAIL: 0, BLOCKED: 0, NOT_TESTED: 0}
trial_count=8
```

VERIFIED by live Stage 0 run under the same zshrc-sourced environment shape used by scheduler:

```bash
zsh -lc 'source ~/.zshrc >/dev/null 2>&1; \
  export MONITOR_CLAIM_SNAPSHOT_PATH=/home/graham/workspace/experiments/agent-skills/skills/monitor-opportunities/local/nightly/authority/claim-snapshot.json; \
  export MONITOR_OPPORTUNITIES_MORNING_DISCORD_CHANNEL=horus; \
  cd /home/graham/workspace/experiments/agent-skills && \
  skills/monitor-opportunities/run.sh run --out /tmp/monitor-opportunities-stage0-source-adapter-zsh-live-2484169'
```

Readback from `/tmp/monitor-opportunities-stage0-source-adapter-zsh-live-2484169/report-manifest.json` and `report-acceptance`:

```text
slack_channels AUTH_REQUIRED response_status=None content_sha256=False automation_policy=slack_read_only_no_post_no_dm_no_reaction
discord_channels MATCHES response_status=200 content_sha256=True automation_policy=discord_read_only_no_post_no_dm_no_reaction
gmail_mailbox MATCHES response_status=200 content_sha256=True automation_policy=mailbox_mining_memory_read_only_no_gmail_send_no_forward_no_schedule
acceptance=PASS
truth=DEGRADED EMIT_DEGRADED degradation_codes=[SCHEDULER_RELIABILITY_UNPROVEN, SOURCE_COVERAGE_DEGRADED] blocking_codes=[]
```

VERIFIED by project-state rerun:

```bash
PROJECT_STATE_ROOT=/home/graham/workspace/experiments/agent-skills/skills/monitor-opportunities \
PROJECT_STATE_NAME=monitor-opportunities \
skills/project-state/run.sh report --json --output /tmp/monitor-opportunities-project-state-after-source-adapters.json
```

Readback from `/tmp/monitor-opportunities-project-state-after-source-adapters.json`:

```text
best_practices_total=0
```

## Current product state

The latest verified live Stage 0 run emits a report and passes report acceptance, but truth-status remains degraded because:

1. `SCHEDULER_RELIABILITY_UNPROVEN`: a manual run is not proof of the next real 2 AM scheduler invocation.
2. `SOURCE_COVERAGE_DEGRADED`: Slack has no read credential or retained evidence file in the scheduler environment.

Discord and Gmail discovery are no longer unwired in the zshrc-sourced run: Discord readback produced `MATCHES`, and Gmail mailbox-mining memory readback produced `MATCHES`.

## Still not done

1. Provide one of these Slack inputs, then rerun and read back `truth-status.json`:
   - `SLACK_BOT_TOKEN` or `SLACK_USER_TOKEN` with read access to `MONITOR_OPPORTUNITIES_SLACK_CHANNEL_IDS`, or
   - `MONITOR_OPPORTUNITIES_SLACK_EVIDENCE=/path/to/retained-read-only-slack-capture.json`.
2. Commit and push the source-adapter repair.
3. Re-register `monitor-opportunities-nightly` after the final pushed revision so `--expected-revision` matches the code the scheduler will execute.
4. Verify the next real 2 AM cron with `run-receipt.json.trigger == "SCHEDULER"`.

## Proof boundary

- Live: Stage 0 source discovery, ATS board reads, Discord bot read, `/memory` mailbox-mining recall, report rendering, report acceptance.
- Fixture/deterministic: source-adapter `$agentic-evals` and token-path tests.
- Unverified: Slack channel coverage until a Slack read token or retained evidence file is supplied; next real 2 AM cron reliability until it fires.
- Forbidden external effects remain forbidden: no Gmail send/forward/schedule, no LinkedIn action, no ATS submit, no Meetup RSVP.
