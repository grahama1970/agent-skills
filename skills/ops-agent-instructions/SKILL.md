---
name: ops-agent-instructions
description: >
  Maintain and audit global agent instruction files such as AGENTS.md, CLAUDE.md,
  and provider-specific agent markdown. Use for instruction parity, stale rule
  pruning, memory/skill-chain wording, proof-boundary reporting, and main-branch
  worktree guardrails.
triggers:
  - agent instructions
  - AGENTS.md
  - CLAUDE.md
  - optimize agent md
  - audit agent instruction files
  - provider instruction parity
provides:
  - skill-validation
  - project-state-readiness-pattern
composes:
  - memory
  - agentic-evals
  - best-practices-skills
  - best-practices-python
complies:
  - best-practices-skills
  - best-practices-python
taxonomy:
  - validation
  - developer-tooling
  - agent-operations
runtime_self_improvement: basic
disciplines:
  - developer-tooling
  - agent-operations
---

# Ops Agent Instructions

Use this skill when editing, pruning, comparing, or monitoring global agent
instruction files such as:

- `~/.codex/AGENTS.md`
- `~/.claude/CLAUDE.md`
- project-local `AGENTS.md`, `AGENT.md`, `CLAUDE.md`, or provider equivalents

The goal is one clear operating contract across providers, with provider
differences made explicit and no stale rule pileup.

## Required Workflow

1. Read current files before editing.
2. Run `$memory recall --brief` when prior agent-instruction incidents,
   provider differences, or solved patterns could matter.
3. Choose one canonical source when files should match. Keep provider-specific
   deltas short and named.
4. Preserve these invariants:
   - use `$memory` for durable recall and skill-chain suggestions;
   - read selected skills' current `SKILL.md` files before acting;
   - require `/agentic-evals` for new features and skill behavior;
   - report proof boundaries with mocked/live status;
   - speak plainly about blockers and missing evidence;
   - never hide failure behind commits, branches, pushes, or SHAs;
   - for alpha+ projects, use the primary checkout on `main` unless the human
     explicitly authorizes a different worktree or branch.
5. After edits, run the checker and read back its JSON receipt.
6. If this skill changes, update `fixtures/agentic_eval.json` and run
   `/agentic-evals`.

## Checker

Run the default audit against the current global files:

```bash
./run.sh audit --json --require-identical
```

Audit explicit files:

```bash
./run.sh audit --json --require-identical \
  --path codex=/home/graham/.codex/AGENTS.md \
  --path claude=/home/graham/.claude/CLAUDE.md
```

Write a receipt:

```bash
./run.sh audit --json --require-identical --output /tmp/agent-instructions-audit.json
```

Run skill-local sanity:

```bash
./sanity.sh
```

Run the agentic eval:

```bash
../agentic-evals/run.sh run fixtures/agentic_eval.json
```

## Output Contract

Reports should be bullet-point friendly and start with operational state:

- Status/Phase: what exists, what works, what is broken, what remains.
- Evidence: command, artifact path, file read-back, endpoint response, or
  screenshot.
- Proof Boundary: `mocked: yes|no`, `live: yes|no`, what was exercised, and
  what remains unverified.
- Next/Stop Condition: next command if work remains; exact blocker and needed
  input if blocked.

Do not use commit metadata, branch names, push results, or SHAs as the primary
status. They are retention metadata only.

## Editing Rules

- Keep instruction files short enough to be read during startup.
- Prefer one canonical template and broadcast it to providers.
- Remove duplicated, stale, impossible, or conflicting instructions.
- Do not add broad permission grants while fixing reporting wording.
- Do not put session memory under `~/.pi/agent/memory/`; use `$memory`.
- Do not add provider-specific behavior unless it is required by that provider.

## Proof Boundary

The checker proves only file presence, parity, required wording coverage, line
counts, hashes, and current read-back. It does not prove future agents will obey
the files. Obedience requires live task receipts, `/agentic-evals` runs, and
operational monitoring.
