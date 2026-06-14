---
name: skill-maintainer
description: >
  Project-agent entrypoint for running the skill-maintainer GitHub issue repair
  loop with JSON status artifacts, subagent dispatch, deterministic verification,
  advisory WebGPT review, scoped publication, and terminal disposition.
triggers:
  - skill-maintainer
  - skill maintainer
  - run skill-maintainer
  - maintain skills issue
  - repair skill issue
taxonomy:
  - orchestration
  - maintenance
  - reliability
---

# Skill Maintainer

Use this skill when a project agent needs to hand one GitHub issue to
`skill-maintainer` and monitor it through the real repair -> verify -> review ->
WebGPT advisory -> publication loop.

## Commands

Run one scheduler tick. This is the cron-friendly entrypoint; cron/systemd
should invoke it every N minutes instead of running a long-lived daemon:

```bash
skills/skill-maintainer/run.sh scheduler --max-issues 1
```

Run one cron tick. This fetches and fast-forwards the worker worktree from
`origin/main` before invoking the single-shot scheduler:

```bash
skills/skill-maintainer/run.sh cron-tick --max-issues 1 --auto-update
```

Install the managed crontab entry that launches the single-shot scheduler every
N minutes:

```bash
skills/skill-maintainer/run.sh install-cron --interval-minutes 5 --max-issues 1
```

Inspect or remove the managed crontab entry:

```bash
skills/skill-maintainer/run.sh cron-status
skills/skill-maintainer/run.sh remove-cron
```

The managed cron entry is tagged with `skill-maintainer-scheduler`, appends
cron stdout/stderr to `.artifacts/skill-maintainer/cron.log`, and leaves the
scheduler JSONL stream in `.artifacts/skill-maintainer/scheduler-events.jsonl`.
By default, the managed entry calls `cron-tick --auto-update`, so each host cron
tick fetches `origin/main` and checks out the updated `main` branch before
running the scheduler. Use `install-cron --dry-run` before mutating a host
crontab.

For a pinned queue item, keep the same single-shot scheduler path and specify
the issue explicitly:

```bash
skills/skill-maintainer/run.sh scheduler --issue 123
```

The scheduler tick appends JSONL events to:

```text
.artifacts/skill-maintainer/scheduler-events.jsonl
```

Start one explicit issue and dispatch the repair worker:

```bash
skills/skill-maintainer/run.sh start --issue 123
```

Inspect one local issue artifact directory:

```bash
skills/skill-maintainer/run.sh status .artifacts/skill-maintainer/<run>/issue-123
```

Audit one local issue artifact directory after a maintainer run:

```bash
skills/skill-maintainer/run.sh audit-run .artifacts/skill-maintainer/<run>/issue-123
```

If the post-job audit detects a maintainer bug or improvement opportunity and
the project-agent lane wants a GitHub ticket record, file that follow-up
explicitly:

```bash
skills/skill-maintainer/run.sh audit-run .artifacts/skill-maintainer/<run>/issue-123 --file-issue
```

Advance one local issue artifact directory by one maintainer transition:

```bash
skills/skill-maintainer/run.sh step .artifacts/skill-maintainer/<run>/issue-123
```

Drive an issue until a terminal state or timeout. This emits live JSONL events
to stdout for project-agent monitors:

```bash
skills/skill-maintainer/run.sh drive --issue 123 --timeout-seconds 1800
```

Once `drive` knows the issue artifact directory, it also appends the emitted
monitor events to `<issue-artifact-dir>/drive-events.jsonl`. Fresh-drive
startup failures may emit a `start` event to stdout before an event log path
exists. Resume mode appends new monitor events to the existing artifact
directory's `drive-events.jsonl`:

```bash
skills/skill-maintainer/run.sh drive --artifact-dir .artifacts/skill-maintainer/<run>/issue-123
```

Every terminal `drive` run must write a post-job audit before emitting the
terminal event:

```text
<issue-artifact-dir>/post-job-audit.json
```

The terminal JSONL stream includes a `post_job_audit` event with the audit path,
classification, recommended action, and any self-improvement issue URL.

## Contract

- One run handles one issue.
- Scheduled use is single-shot: cron launches `scheduler` every N minutes, and
  each tick leases/processes at most one eligible issue.
- Managed cron use launches `cron-tick`, which updates the worker worktree from
  `origin/main` before invoking `scheduler`.
- Project agents monitor the JSONL stream, not prose.
- Pre-repair WebGPT diagnosis is mandatory before repair dispatch.
- WebGPT tab id and URL must be resolved through `$browser-oracle` project
  binding; callers pass the project/walk-up root, not foreground-tab guesses.
- Deterministic local proof is required before publication or closure.
- WebGPT is advisory; it is not deterministic closure proof.
- Publication must be scoped to target paths/receipt paths only.
- Post-job audit is mandatory for terminal `drive` results.
- The audit may recommend a self-improvement issue; filing is explicit with
  `--file-issue` or `drive --file-audit-issue`.
- If `drive` reports `timeout` or `blocked`, preserve the artifact directory and
  resume with `step` or `drive --artifact-dir`.

## Important Artifacts

```text
.artifacts/skill-maintainer/<timestamp>/issue-<n>/
  cycle-result.json
  drive-events.jsonl
  issue-route.json
  diagnosis-bundle.md
  diagnosis-webgpt-result.json
  repair-response.json
  verifier-response.json
  review-response.json
  ask-webgpt-result.json
  publication-result.json
  post-job-audit.json
  subagent-sessions/*/status.json
```

The stable status interface is:

```bash
skills/skill-maintainer/run.sh status <issue-artifact-dir>
```
