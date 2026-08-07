---
name: webgpt-review
description: >
  Submit a readable review bundle to WebGPT through the deterministic ask-owned
  review command. Use when a project agent needs WebGPT/ChatGPT review of code,
  design, prompt, or implementation-plan evidence and should not interpret the
  broad $ask webgpt surface. Trigger phrases include WebGPT review, ChatGPT
  review bundle, ask WebGPT to review this bundle, and browser-backed review.
triggers:
  - WebGPT review
  - ChatGPT review bundle
  - ask WebGPT to review this bundle
  - browser-backed review
  - webgpt-review
provides:
  - browser-review-receipt
  - webgpt-review-artifacts
  - fail-closed-review-submission
composes:
  - ask
  - surf
complies:
  - best-practices-skills
taxonomy:
  - review
  - browser
  - validation
  - resilience
disciplines:
  - browser-automation
  - evaluation-quality
---

# WebGPT Review

## Contract

Use this skill instead of free-form `$ask webgpt ...` for project-agent WebGPT
reviews. The supported path is the dedicated wrapper:

```bash
./scripts/run-webgpt-review.sh \
  --bundle /absolute/path/to/review-bundle.md \
  --review-type code \
  --project <project-name> \
  --json
```

The wrapper validates the bundle, records Surf freshness diagnostics, preflights
the exact WebGPT tab when a tab id or URL is supplied, retries extension reload
only when preflight cannot reach Surf/focus state, and then calls the ask-owned
executable command:

```bash
../ask/run.sh webgpt-review \
  --bundle /absolute/path/to/review-bundle.md \
  --review-type code \
  --project <project-name> \
  --json
```

The bundle must be exactly one browser-readable artifact:

- one concatenated `.md` or `.txt` file, or
- one small `.zip` with at most five files.

Do not pass a directory, a path-only manifest, or scattered local paths. A
browser reviewer cannot read those reliably.

This skill composes `$ask` and `$surf` as runtimes, but callers should treat this
wrapper as the stable interface. Do not hand-compose broad `$ask webgpt` and raw
`$surf` commands for normal review submission.

## Required Workflow

1. Create or select one readable review bundle.
2. Include the full review target in the bundle: full diff, changed files, test
   output, and exact questions. Do not submit summary-only snippets for code
   review.
3. Run `scripts/run-webgpt-review.sh` with `--bundle`, `--review-type`, and either
   `--project`, `--tab-id`, `--url`, or `--create-tab`.
4. Return the command result and artifact paths from `status.json`.
5. Treat WebGPT output as reviewer evidence, not local closure proof.

## Stable Invocation

Prefer explicit tab and URL when the human provides them:

```bash
skills/webgpt-review/scripts/run-webgpt-review.sh \
  --bundle /tmp/review-bundle.md \
  --review-type code \
  --tab-id 837352346 \
  --url 'https://chatgpt.com/g/.../c/...' \
  --ask-id issue-3-review \
  --json
```

Use `--project <name>` only when the project binding is fresh. If project
binding fails with a stale tab id, retry with the exact `--tab-id` and `--url`
reported by the human or by `surf tab.list --json`.

Preflight the target without submitting a review when diagnosing tab identity:

```bash
ASK_WEBGPT_ALLOW_FOREGROUND=1 \
skills/webgpt-review/scripts/run-webgpt-review.sh \
  --tab-id 837352346 \
  --url 'https://chatgpt.com/g/.../c/...' \
  --preflight-only \
  --json
```

## Fail Closed

If the command returns `BLOCKED`, report the blocker and the `recovery_command`
from `status.json`. Do not fall back to raw `$surf`, free-form `$ask webgpt`,
or a normal model/subagent unless the user explicitly asks for that fallback.

If `BLOCKED` says the reviewer could not assess the bundle, rebuild the bundle
with the full diff or full artifact content and rerun this skill. Do not treat a
transport PASS as a review PASS.

## Review Types

Use `--review-type code`, `design`, `prompt`, or `plan`. If unsure, use `plan`
for implementation strategy and `code` for diffs or changed files.
