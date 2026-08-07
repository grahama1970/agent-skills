---
name: align
description: >
  Round-based context alignment before execution. Use when the human, project
  agent, WebGPT, scillm, ask, dogpile, memory, or project-knowledge may each
  hold different facts about a task; especially before ambiguous design,
  infographic, product workflow, high-stakes implementation, plan-iterate,
  project-infographic, or multi-review work.
triggers:
  - align the task
  - alignment before execution
  - align with webgpt
  - align with scillm
  - align with project knowledge
  - clarify across reviewers
  - create an alignment lock
  - context reconciliation
  - multi round clarification
provides:
  - alignment-lock
  - context-reconciliation
  - clarification-rounds
  - pre-execution-gate
composes:
  - project-knowledge
  - memory
  - scillm
  - ask
  - dogpile
  - interview
taxonomy:
  - coordination
  - validation
  - resilience
disciplines:
  - human-collaboration
  - agentic-orchestration
---

# Align

Use `$align` to equalize context before action. The skill exists for tasks where
the human, project agent, WebGPT, `$scillm`, `$ask`, `$dogpile`, `$memory`, or
`$project-knowledge` may each know different facts. It produces an
`alignment_lock.json` that later skills can execute from.

Do not use `$align` to implement, render, refactor, or review final work. It is
a pre-execution gate. No code, infographic, dashboard, plan-iterate phase, or
project-infographic render should start until the alignment lock says
`ready_for_execution: true`.

## Core Rule

Alignment is complete only when all blocking questions are answered and the
lock records:

- agreed goal
- agreed non-goals
- source context
- participant facts
- remaining assumptions and risks
- output shape
- acceptance criteria
- explicit ready/not-ready decision

If disagreement remains, keep the lock `ready_for_execution: false`.

## Participants

Use only participants that are relevant to the task:

| Participant | Role |
|---|---|
| `human` | Intent, preferences, domain nuance, acceptance bar |
| `project_agent` | Local repo state, constraints, executable next steps |
| `project_knowledge` | Durable project history and takeover notes |
| `memory` | Prior lessons and similar solved problems |
| `scillm` | Direct model critique through the localhost LLM proxy |
| `ask` | Ask/oracle/deep-review runtime with artifacts; owns WebGPT routing |
| `dogpile` | Fresh external research when local context is insufficient |
| `webgpt` | Browser/session-visible context and human-facing judgment |

WebGPT calls must route through `$ask webgpt`; `$ask` already owns the WebGPT
oracle backend and uses `surf webgpt.submit --no-activate` against the user's
authenticated ChatGPT tab. `$align` does not call `surf` directly. Do not send
WebGPT requests through `$scillm`; `$scillm` is for direct model calls such as
`gpt-5.5`, Gemini, Claude, or OpenCode Go. Preserve the tab id when the human
provides it.
Use `$dogpile` only when alignment is blocked by missing external/current
knowledge. Do not use it for facts that `$project-knowledge` or `$memory`
already answer.

## Runtime Routing

```text
                         +-----------------------+
                         |    $align init        |
                         | goal, output, sources |
                         +-----------+-----------+
                                     |
                                     v
                   +-----------------+-----------------+
                   |     Round N: alignment_brief      |
                   | participants state facts, gaps,   |
                   | contradictions, and questions     |
                   +-----------------+-----------------+
                                     |
                   +-----------------+-----------------+
                   | compile-round extracts questions  |
                   | Question[blocking/nonblocking]:   |
                   +-----------------+-----------------+
                                     |
                  open blocking questions?
                         | yes                         | no
                         v                             v
        +----------------+----------------+    +-------+--------+
        | route each question to owner    |    | lock --ready   |
        | human/project/memory/reviewer   |    | writes lock    |
        +----------------+----------------+    +----------------+
                         |
                         v
        +----------------+----------------+
        | add-response / answer-question  |
        | update brief, increment round   |
        +----------------+----------------+
                         |
                         v
                    Round N+1
```

Reviewer routes are optional inputs to a round:

```text
                                +----------------+
                                | Round N brief  |
                                +-------+--------+
                                        |
          +-----------------------------+-----------------------------+
          |                             |                             |
          v                             v                             v
+--------------------+       +--------------------+       +--------------------+
| WebGPT via $ask    |       | $scillm direct     |       | $ask review/oracle |
| prepare-review     |       | prepare-review     |       | prepare-review     |
| --reviewer webgpt  |       | --reviewer scillm  |       | --reviewer ask     |
+---------+----------+       +---------+----------+       +---------+----------+
          |                            |                            |
          v                            v                            v
skills/ask/run.sh ask webgpt    round-N-scillm-request.json   round-N-ask-request.md
--webgpt-tab-id <id>            model: gpt-5.5               skills/ask/run.sh ask
          |                     reasoning_effort: high       --deep-review
          v                     optional persona prompt
 $ask -> surf webgpt.submit            |
 --no-activate                         v
          |                  POST localhost:4001/v1/chat/completions
          v
 authenticated ChatGPT tab

External/current research:
  prepare-review --reviewer dogpile -> round-N-dogpile-request.md
  Use only when missing external facts block alignment.
```

## Round Loop

Each round follows the same sequence:

1. Broadcast the current alignment brief to selected participants.
2. Each participant states what they believe the task is.
3. Each participant lists facts they know that others may not know.
4. Each participant lists assumptions, contradictions, and questions.
5. Merge questions into blocking and non-blocking sets.
6. Route questions to the party that can answer them.
7. Update the brief.
8. Stop only when blocking questions are resolved or max rounds is reached.

If max rounds is reached with blocking questions open, stop with
`ready_for_execution: false` and surface the smallest human decision needed.

## CLI

### WebGPT tab binding (CLI parity)

Prefer **zero-flag** `$ask webgpt` from a registered working directory. `/ask` composes
`$browser-oracle` automatically. `init` and `prepare-review` persist binding hints in
`.align/state.json` and emit the same flags on generated `round-*-webgpt-ask-command.sh`.

| Flag | When to use |
|------|-------------|
| *(none)* | cwd has walk-up registry + binding — preferred |
| `--browser-oracle-from <dir>` | Override walk-up root (monorepo subdir) |
| `--webgpt-project <name>` | Explicit project; skips yaml walk-up |
| `--webgpt-tab-id <id>` | One-off override; skips walk-up |
| `--webgpt-url <url>` | Resolve by conversation URL; skips walk-up |

**Resolution order** (same as `$ask` / `$surf`): `--webgpt-tab-id` → `--webgpt-url` →
`$browser-oracle` walk-up → `--webgpt-project` → one `chatgpt.com` tab (fail-closed).

Setup: `$browser-oracle register` + `bind` + `doctor --from <dir>`. See `$browser-oracle`
and `$ask` SKILL.md **WebGPT tab binding** sections.


Run from the repository or project root that owns the task:

```bash
skills/align/run.sh init \
  --goal "Create a clear plan-iterate infographic request" \
  --output-shape "source-derived storyboard and web infographic request" \
  --participant human \
  --participant project_agent \
  --participant project_knowledge \
  --participant scillm \
  --participant ask \
  --participant dogpile \
  --participant webgpt
# Prefer zero-flag from a registered dir, or persist walk-up root:
#   --browser-oracle-from skills/oc-subagent/personas/mathematics
# Legacy explicit override:
#   --webgpt-tab-id 837343529
```

Record participant responses:

```bash
skills/align/run.sh add-response \
  --participant project_agent \
  --round 1 \
  --text "Task: reconcile the workflow before rendering. Fact: the prior visual failed because there was no approved storyboard. Question[blocking]: what exact sample project should anchor the visual?"
```

Compile the round:

```bash
skills/align/run.sh compile-round --round 1
```

Lock only after blocking questions are resolved:

```bash
skills/align/run.sh lock --ready --approved-by human
```

## Reviewer Request Generation

`prepare-review` creates replayable request artifacts for reviewers. It does
not call the reviewer by itself.

```bash
skills/align/run.sh prepare-review --round 1 --reviewer scillm
skills/align/run.sh prepare-review --round 1 --reviewer ask
skills/align/run.sh prepare-review --round 1 --reviewer dogpile
skills/align/run.sh prepare-review --round 1 --reviewer webgpt --browser-oracle-from skills/oc-subagent/personas/mathematics
# or: --webgpt-tab-id 837343529
```

Use WebGPT when the review needs the human's authenticated ChatGPT browser
session or browser-visible context. Use `$scillm` when the review should be a
direct, replayable model call, for example GPT-5.5 high reasoning with a
persona/system prompt:

```bash
skills/align/run.sh prepare-review \
  --round 1 \
  --reviewer scillm \
  --scillm-model gpt-5.5 \
  --reasoning-effort high \
  --persona-prompt "You are a skeptical product alignment reviewer. Focus on mismatched assumptions and missing acceptance criteria."
```

Recommended calls after `prepare-review`:

```bash
# scillm direct review
.align/reviews/round-001-scillm-command.sh

# ask deep review or WebGPT oracle
skills/ask/run.sh ask "Review the alignment request at .align/reviews/round-001-ask-request.md" \
  --deep-review --deep-review-target .align/reviews/round-001-ask-request.md

skills/ask/run.sh ask webgpt "Review the alignment request at .align/reviews/round-001-webgpt-request.md" \
  --browser-oracle-from skills/oc-subagent/personas/mathematics --oracle-iterations 1

# dogpile research only if alignment is blocked by missing external facts
skills/dogpile/run.sh search "facts needed to unblock this alignment" \
  --context-file ".align/reviews/round-001-dogpile-request.md"
```

Store the resulting reviewer text with `add-response`. Reviewer receipts are
inputs to alignment; they are not execution approval by themselves.

## Live Composition Sanity

`sanity.sh` is the fast local check. It proves the round loop, blocking-question
gate, reviewer request generation, and lock schema without spending external
quota.

`sanity-live.sh` is the required real-world E2E gate before claiming `$align`
is ready as a composite skill. It is opt-in because it calls live downstream
systems:

- `$memory recall --brief` through the real memory skill
- project-agent response ingestion through `$align add-response`
- `$dogpile search` with the generated alignment request as context
- `$ask webgpt` against the authenticated browser-backed WebGPT path
- final `alignment_lock.json` creation only after those receipts validate

Run it only when the local workstation has memory, dogpile credentials/search,
Chrome, and an authenticated ChatGPT session:

```bash
ALIGN_LIVE_E2E=1 skills/align/sanity-live.sh
```

Optional controls:

```bash
ALIGN_LIVE_E2E=1 \
ALIGN_WEBGPT_TAB_ID=837343529 \
ALIGN_LIVE_OUTPUT_ROOT=/mnt/storage12tb/skills/align/live-e2e \
skills/align/sanity-live.sh
```

If no `ALIGN_WEBGPT_TAB_ID` or `ALIGN_WEBGPT_PROJECT` is provided, the live
check passes `--webgpt-create-tab` to `$ask`; this still requires a valid local
Chrome/WebGPT setup. The proof artifact is
`/mnt/storage12tb/skills/align/live-e2e/<timestamp>/report.json` by default.
Skipped live checks do not establish readiness.

## Artifact Layout

```text
.align/
  alignment_state.json
  alignment_brief.md
  alignment_lock.json
  rounds/
    round-001/
      participant-human.md
      participant-project_agent.md
      participant-scillm.md
      round_summary.md
      questions.json
  reviews/
    round-001-scillm-request.json
    round-001-scillm-command.sh
    round-001-ask-request.md
    round-001-dogpile-request.md
    round-001-webgpt-request.md
    round-001-webgpt-ask-command.sh

/mnt/storage12tb/skills/align/live-e2e/<timestamp>/
  report.json
  memory.stdout
  dogpile.stdout
  webgpt.stdout
  ask-runs/<ask_id>/
```

## Stop Conditions

Set `ready_for_execution: true` only when:

- no blocking questions remain open
- the agreed goal and non-goals are explicit
- the output shape is concrete
- the acceptance criteria are testable or reviewable
- the source context is named
- the human or delegated owner approved the lock

Set `ready_for_execution: false` when:

- blocking questions remain
- WebGPT, `$scillm`, `$ask`, or project knowledge contradict the brief
- the output shape is still abstract
- a participant exposed missing source evidence
- the requested next step would produce a receipt instead of solving the real task

## Common Mistakes

- Do not use `$align` as a substitute for `$interview`; use interview when the
  missing information is purely human preference or acceptance criteria.
- Do not use `$align` as a substitute for `$review-code`, `$review-plan`, or
  `$plan-iterate`; alignment happens before those skills.
- Do not summarize WebGPT or `$ask` manually. Use their real runtimes and store
  artifact paths or reviewer text.
- Do not call an alignment lock complete because a reviewer passed it. The
  project agent must merge the result and clear blocking questions.
