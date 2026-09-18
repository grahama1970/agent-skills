---
name: thrash-guard
description: >
  Deterministic Pi extension that detects agent/subagent thrashing (multiple
  repeated errors, or the same command retried with no progress) and blocks
  further mutating tool calls until the agent climbs a cheapest-first diagnosis
  ladder: Jev/triage-error -> brave/web search -> bigger model subagent ->
  full $ask webgpt with comprehensive context -> subagent implements the fix.
  Use when an agent burns turns re-trying variants of a failing action instead
  of diagnosing. Detection is deterministic, never model judgment.
triggers:
  - thrash guard
  - thrashing
  - repeated errors
  - anti-thrash
  - stop guessing
composes:
  - triage-error
  - jev
  - brave-search
  - ask
  - pi-subagents
complies:
  - best-practices-pi-extensions
  - best-practices-skills
disciplines:
  - agentic-orchestration
  - observability-operations
---

# thrash-guard — force diagnosis when the agent is thrashing

An agent (or subagent) that hits a wall tends to re-try variants of the same
failing action for many turns instead of diagnosing. This session's cockpit-click
work is the paid example: `surf click` returned OK every time (exit 0) while
changing nothing, so an error-only guard would have missed it — the real signal
was **repeated near-duplicate commands with no progress**.

## What it does

A Pi extension (`pi-extension/index.ts`) with a deterministic detector
(`pi-extension/detector.mjs`, unit-tested in `test_detector.mjs`):

- `tool_result` -> records `isError` in a rolling window.
- `tool_call` -> records a command **verb signature** (program + subcommand, args
  stripped) so arg-varying retries collapse to one signature.
- Thrash = `THRESHOLD` errors OR `THRESHOLD` repeats of one signature within the
  last `WINDOW` tool calls (defaults 3 in 6; override via
  `THRASH_GUARD_THRESHOLD` / `THRASH_GUARD_WINDOW`).
- When locked, any **mutating** tool (`bash`/`edit`/`write`) is blocked with a
  reason that spells out the ladder. Reads (`read`/`grep`/`find`/`ls`) are never
  blocked — investigation is always allowed.
- Running any Tier 0/1 diagnostic (`triage-error classify`/`triage`, `web_search`,
  `source_check`, or a `brave_search` call) clears the lock.

## The escalation ladder (cheapest first; stop at the first that resolves)

| Tier | Action | Why |
|---|---|---|
| 0 | `skills/triage-error/run.sh classify --text "<signal>" --layer <l>` (Jev shadow) | typed `{code,cause,next_command}` in one cheap call; catalog hit → apply the fix |
| 1 | `web_search` / brave-search the failing signal | known cause/fix on the web |
| 2 | subagent `openai-codex/gpt-5.5:high` with full context | bigger model diagnoses + proposes a fix |
| 3 | `$ask webgpt` with COMPREHENSIVE context (signal, what was tried, code) | browser reviewer with the whole picture |
| 4 | subagent `claude-sonnet-5` implements the agreed fix, then read back the effect | cheap implementation once the approach is known |

This mirrors the operator "unblock ladder" (AGENTS.md) and composes the existing
`immutable-goal-mvp-loop` core mode for the orchestrated multi-subagent form —
it does NOT author a new bespoke workflowScript (best-practices-workflowscript
anti-bespoke rule: detection can't be a workflowScript anyway — no tool hooks).

## Why an extension, not a workflowScript

A workflowScript has only `runs`/`emit`/`console` — no `tool_call`/`tool_result`
hooks, no shell, no filesystem — so it cannot observe or block a running agent's
tools. The guard (detect + block) must be an extension. The tiered *response* is
the ladder above, actionable from the block reason.

## Install / activate

```bash
mkdir -p ~/.pi/agent/extensions/thrash-guard
cp pi-extension/index.ts pi-extension/detector.mjs ~/.pi/agent/extensions/thrash-guard/
# auto-discovered from ~/.pi/agent/extensions/*/index.ts on next session start
```

For subagents, load it as a subagent extension so children are guarded too.

## Proof

```bash
node pi-extension/test_detector.mjs   # -> THRASH_GUARD_DETECTOR_OK
```

The test feeds this session's real thrash (three `surf click` retries that
returned OK) plus error-thrash and asserts: the lock engages, reads stay allowed,
mutating calls are blocked, and a triage-error/web_search call clears it.

**Proof boundary:** the detector logic is unit-proven; live `pi.on` wiring inside
a running Pi session is not exercised by the unit test (same boundary
`eval-guard` documents). Validate live wiring with `pi -e pi-extension/index.ts`.
