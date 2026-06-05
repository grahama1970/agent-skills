# agent-status

`agent-status` is a reusable skill for making long-running project-agent work observable.

It writes:

```text
.plan-iterate/<campaign-id>/status/
  status.json
  events.jsonl
  proof_manifest.json
  STATUS.html
```

The HTML page is generated from `status.json` and avoids dashboard theater:
no fake percentages, no broad green “complete” claims, and no status changes
unless the underlying artifact changes.

## Install

Place this directory at:

```text
skills/agent-status/
```

Then run:

```bash
chmod +x skills/agent-status/run.sh
```

## Quick start

```bash
skills/agent-status/run.sh init \
  --campaign refactor-harness-e2e \
  --goal "Finish scoped refactor harness E2E proof"

skills/agent-status/run.sh gate-passed \
  --campaign refactor-harness-e2e \
  --label "A01-A18 hardened concurrent LLM + OpenCode summarize" \
  --verdict PASS_SPEC \
  --proof ".plan-iterate/refactor-harness-e2e/proof/refactor-concurrent-mixed.json" \
  --next-action "Start reviewer packet + reviewer fan-in phase" \
  --not-proven "Transport Room B1 UI" \
  --not-proven "build_review_packet reviewer fan-in" \
  --not-proven "Full OpenCode message delivery"
```

Open:

```text
.plan-iterate/refactor-harness-e2e/status/STATUS.html
```

## Why this exists

Project agents often work opaquely when the work is not visual. UI work gets screenshots;
backend, harness, orchestration, and review-loop work usually gets logs. This skill creates
a consistent, proof-backed surface for humans.

It answers:

- what is the goal?
- what is the state?
- what just passed?
- what remains unproven?
- what should happen next?
- who owns the next action?
- what proof backs the claim?
- what should not happen next?

## Commands

```bash
run.sh init
run.sh update
run.sh gate-passed
run.sh needs-human
run.sh blocked
run.sh event
run.sh render
run.sh validate
```

See `SKILL.md` for command examples.
