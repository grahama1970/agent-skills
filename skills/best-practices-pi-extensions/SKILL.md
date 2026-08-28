---
name: best-practices-pi-extensions
description: >
  Best practices for creating, reviewing, and hardening Pi extensions. Use when building or changing ~/.pi/agent/extensions or .pi/extensions code, event handlers, custom tools, input/message hooks, retry guards, final-report guards, or humorous enforcement extensions such as lazy-report-shame-shame-shame.
triggers:
  - pi extension
  - pi extensions
  - message_end extension
  - before_agent_start hook
  - input hook
  - custom pi tool
  - final report guard
  - lazy report shame
  - extension event handler
provides:
  - pi-extension-patterns
  - extension-validation
  - report-guard-design
composes:
  - unlazy
  - agentic-evals
  - memory
complies:
  - best-practices-skills
  - best-practices-security
  - typescript-code
taxonomy:
  - developer-tooling
  - validation
  - resilience
disciplines:
  - developer-tooling
  - engineering-standards
---

# Pi Extensions Best Practices

Use this before writing or reviewing Pi extensions.

## Required reading

Read Pi docs and examples before implementation:

- `/home/graham/.local/share/pi-node/node-v22.23.2-linux-x64/lib/node_modules/@earendil-works/pi-coding-agent/docs/extensions.md`
- Relevant files under `/home/graham/.local/share/pi-node/node-v22.23.2-linux-x64/lib/node_modules/@earendil-works/pi-coding-agent/examples/extensions/`

For final-report, retry, or anti-laziness work, also read `$unlazy` and its agent-skills workflow reference.

## Do not bespoke the enforcement pattern

Use the smallest Pi event that owns the behavior:

| Need | Pi event/API |
| --- | --- |
| Add per-turn instruction | `before_agent_start` |
| Rewrite/block user input | `input` |
| Block a dangerous tool call | `tool_call` |
| Modify tool evidence | `tool_result` |
| Reject or replace assistant prose | `message_end` |
| Force another model attempt | `pi.sendUserMessage(..., { deliverAs: "followUp" })` |
| Show operator-visible status | `ctx.ui.notify`, `ctx.ui.setStatus`, `ctx.ui.setWidget` |

## Desperation guards must be deterministic

If the extension exists because agents ignored prose, do not ask the same agent to judge itself.

- Put the decision in a deterministic checker script.
- The extension calls the checker and uses its exit code.
- The checker prints exact rejection reasons.
- The rejected assistant answer must not remain the accepted final answer.
- Queue a forced retry with the checker diagnostics in the retry prompt.
- If a retry fails, queue another retry or hand off to the human with a rejection notice; never allow the lazy answer as success.

## Final-report guards

Reject reports that launder failure as progress:

- vague unresolved-work language without exact rows;
- `Committed and pushed`, branch names, SHAs, or hook status used as the result;
- `mostly done`, `partially complete`, `remaining gates`, `open items`, or `what remains` without exact gate IDs;
- counts that do not include rows and proof boundaries.

Require:

```text
Progress:
- VERIFIED: <concrete user-visible change or artifact outcome>
MET: <n>
UNMET: <n>
ABANDONED: <n>
- UNMET `Gx`: failed condition: <exact condition>. Next legal command: <command/owner>. Receipt: <path>. Proof boundary: <what was and was not proven>.
```

## Safety and portability

- Global extensions live under `~/.pi/agent/extensions/`; project extensions under `.pi/extensions/` after project trust.
- Extensions run with full user permissions. Do not execute repository text unless the user approved that boundary.
- Keep extension-local deterministic scripts dependency-light and executable with `node`.
- Do not patch Pi internals or `node_modules` for normal extension behavior.
- Test via `pi -e /path/to/extension -p '<prompt>'` and read stdout/stderr.
- Use TypeScript through Pi/Jiti; `node --check` does not parse TypeScript annotations.

## Validation checklist

Before reporting success:

1. Direct checker positive and negative fixtures pass.
2. Live Pi print-mode test loads the extension.
3. Live rejection path replaces bad output.
4. Live retry path produces a second model turn or a fail-closed handoff.
5. The report names proof boundaries and does not count Git metadata as the result.
