---
name: governance
description: >
  Enforce a deterministic pre-plan self-improvement loop before /plan. Use
  when a task needs proof that the agent read the relevant files, resolved
  confusion through /interview or /dogpile, and can show a transparent
  understanding report before creating an orchestration plan.
triggers:
  - governance before plan
  - prove understanding before planning
  - pre-plan governance
  - self improvement loop before planning
  - have you read all relevant files
metadata:
  short-description: Gate planning with understanding proof
provides:
  - task-governance
  - readiness-report
composes:
  - memory
  - interview
  - dogpile
  - create-walkthrough
  - best-practices-self-improvement-loop
  - agentic-evals
taxonomy:
  - governance
  - planning
  - self-improvement
  - validation
disciplines:
  - agentic-orchestration
  - evaluation-quality
---

# /governance

Run `/governance` before `/plan` when the agent might plan too early. The skill
creates a machine-readable report and an HTML walkthrough showing the agent's
understanding, evidence read, open unknowns, and next actions.

The gate question is:

```text
Have you read all relevant files required to fully understand deeply how to correctly implement with confidence?
```

## Required Flow

1. Use `/memory recall` before repository scanning when the target project requires it.
2. Read the files, docs, skill instructions, and integration points needed for the task.
3. If understanding is incomplete, use `/interview` for human decisions and `/dogpile`
   for research or multi-source insight.
4. Run this skill with the task, files read, skills used, assumptions, risks, and gate
   answer.
5. Continue to `/plan` only when the report status is `PASS`.

## Commands

```bash
./run.sh run --task "task text" \
  --files-read skills/plan/SKILL.md \
  --files-read skills/best-practices-skills/SKILL.md \
  --skill plan \
  --skill best-practices-skills \
  --understanding-confirmed

./run.sh status --task "task text" --require-pass
```

`run` writes artifacts to `/mnt/storage12tb/skills/governance/reports/<task-hash>/`.
It updates both task-specific and global `latest.json` markers. `latest.json` is
only a pointer; `status --require-pass` loads and validates the referenced
`report.json`. Do not store run reports inside Git-controlled skill folders.

## PASS Criteria

- `--understanding-confirmed` is set.
- At least one relevant repository file is listed with `--files-read` during
  normal use. Digest-bearing URI evidence may supplement repo file evidence.
- File evidence exists, is non-empty, is inside the repository or
  `/mnt/storage12tb`, and is fingerprinted with sha256, size, and mtime. `/tmp`
  evidence is accepted only with `--allow-test-evidence-root` or
  `GOVERNANCE_ALLOW_TMP_EVIDENCE=1` for tests.
- No unresolved `--unknown` entries remain.
- If `--needs-interview` or `--needs-research` is set, the gate blocks and tells the
  agent to use `/interview` or `/dogpile` before retrying.
- The current context fingerprint matches the report context: repo root, git HEAD,
  scoped dirty digest for evidence and plan/governance integration files,
  evidence fingerprints, and selected skill docs. Full repo dirty status is
  recorded for human review but unrelated dirty paths do not invalidate a PASS.
- The PASS report is not older than the status max age (default: 86400 seconds).

## Integration With /plan

`/plan` requires a matching fresh `/governance` PASS before creating planning
guidance for a goal. The check is enforced in `plan.py`, so direct `plan.py
"goal"` calls are also gated. Validation, rendering, DAG inspection, and plan
maintenance commands can run without this gate because they operate on existing
plan files.

`PLAN_SKIP_GOVERNANCE=1` or `plan.py --skip-governance` is a developer-only
escape hatch for tests and emergency maintenance.

## Outputs

Each run produces:

```text
/mnt/storage12tb/skills/governance/reports/<task-hash>/<timestamp>/
  report.json
  index.html
```

The JSON report is the source of truth. The HTML file is a human-readable
walkthrough for transparent review.

## Storage Contract

By default, reports and the skill uv environment live under
`/mnt/storage12tb/skills/governance`. `/tmp` is allowed for tests. Repo-local
artifact roots are refused unless `GOVERNANCE_ALLOW_UNSAFE_ARTIFACT_ROOT=1` is
set explicitly.
