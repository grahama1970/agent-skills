---
name: oai-degradation
description: >
  Emergency operating procedure for suspected OAI quantization, context rate limiting,
  compression damage, or degraded reasoning. Use when the user says the model is
  quantized, context-limited, evasive, lazy, lying, losing thread, or asks to switch to
  GLM, Kimi, DeepSeek, or another non-OAI model because OAI is unreliable.
triggers:
  - extreme quantization
  - context rate limited
  - OAI degraded
  - model is quantized
  - losing context
  - stop lying
  - stop being evasive
  - switch to GLM
  - switch to Kimi
  - switch to DeepSeek
  - degraded model protocol
runtime_self_improvement: basic
provides:
  - degraded-model-operating-protocol
  - blocker-table-reporting
  - model-transition-policy
composes:
  - memory
  - ask
  - agentic-evals
  - ticket
  - project-watchdog
complies:
  - best-practices-skills
  - best-practices-agent
  - best-practices-delivery-proof
taxonomy:
  - resilience
  - precision
  - truthfulness
disciplines:
  - agentic-orchestration
  - evaluation-quality
  - human-collaboration
---

# OAI Degradation Protocol

Use this skill when the human says, or the agent's behavior shows, that OAI is
quantized, context-rate-limited, over-compressed, evasive, or unreliable.

Do **not** argue about whether the internal OAI cause is provable. Treat the
session as degraded and work around it.

## Immediate response

Say this, then act:

```text
Treating this session as degraded. I will not debate the cause. I will use the
recovery protocol: blocker table, one live check at a time, external ledger, and
non-OAI handoff when needed.
```

Then provide this table before any explanation:

| Field | Entry |
|---|---|
| Goal | one sentence |
| Blocked | VERIFIED / INFERENCE rows only |
| Failing | what just failed, with command/artifact if verified |
| Confused | what I do not know yet |
| Human needed | exact item, or `none verified` |
| Next command | one command or one file read |
| Switch trigger | whether to move to GLM/Kimi/DeepSeek now |

## Hard rules while degraded

1. No denial. Do not say "I cannot verify quantization" as the main answer.
2. No essays. Use tables and commands.
3. No claim without a current-turn read-back.
4. No process report as the result. Report the user-facing artifact first.
5. One active goal. Put everything else into a ticket or ledger.
6. One next command. Run it, read back the artifact, update the table.
7. If the user names a live artifact or URL, inspect that before config, env,
   logs, tickets, or watchdogs.
8. If two focused attempts miss the obvious path, stop OAI execution for this
   task and route review or continuation to a non-OAI model.

## Model transition policy

Switch away from OAI for the next reasoning step when any of these are true:

- the user explicitly asks for GLM, Kimi, DeepSeek, or non-OAI;
- the agent missed a directly named artifact, URL, file, tab, ticket, or command;
- the agent gave two unverified claims in one task;
- the agent produced a long status report while a live check was available;
- context compaction caused loss of goal, blockers, or proof boundary;
- OAI provider/tooling is rate-limited, looping, or returning low-information output.

Preferred handoff shape:

```text
Task: <one concrete task>
Current verified facts: <bullets with commands/artifacts>
Unknowns: <bullets>
Forbidden actions: <bullets>
Required output: Blocked / Failing / Confused / Next / Proof table
```

Use live model catalogs or tool error messages for exact model IDs. Do not invent
provider names. If `$ask`/Tau owns the provider route, use `$ask`; do not call
internal SciLLM directly unless the human asked for SciLLM maintenance.

## External ledger

When degraded behavior affects a task longer than one turn, create or update:

```text
.Codex/session-ledger.md
```

Minimum contents:

```markdown
# Session Ledger

## Goal

## Verified facts
- command/artifact: fact

## Blocked
- blocker: human action or next command

## Failing
- failure: evidence

## Confused
- unknown: next check

## Next command

## Forbidden actions
```

Read the ledger at the start of each degraded turn. Update it after each live
check. The ledger is the state; the model is not.

## Human help contract

Ask for help only in this form:

| Need | Why agent cannot do it | Exact human action |
|---|---|---|
| credential / authorization / decision | verified reason | one action |

Do not ask the human to repeat a failed command. Do not bury the needed action in
paragraphs.

## Recovery closeout

A degraded session can leave degraded mode only after a current-turn table shows:

- no `Blocked` rows except real human-only blockers;
- no `Confused` rows without a next command;
- all claims are backed by command/artifact read-back;
- relevant new/changed feature work has retained `$agentic-evals` coverage;
- relevant repo work is committed and pushed, or a real external blocker is named.

Until then, do not say the task is done.
