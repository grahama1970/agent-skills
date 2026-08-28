---
name: best-practices-pi-extensions
description: >
  Evidence-backed standards for creating, reviewing, and hardening Pi extensions.
  Use when building or changing ~/.pi/agent/extensions or .pi/extensions code,
  package-style Pi extensions, event handlers, custom tools, TypeBox schemas,
  input/message/tool hooks, retry guards, final-report guards, or humorous but
  serious enforcement extensions such as lazy-report-shame-shame-shame.
triggers:
  - pi extension
  - pi extensions
  - pi package extension
  - message_end extension
  - before_agent_start hook
  - input hook
  - tool_call hook
  - tool_result hook
  - custom pi tool
  - final report guard
  - lazy report shame
  - extension event handler
provides:
  - pi-extension-patterns
  - extension-validation
  - report-guard-design
  - package-extension-standard
composes:
  - unlazy
  - agentic-evals
  - memory
  - brave-search
complies:
  - best-practices-skills
  - best-practices-python
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

Use this before writing or reviewing Pi extensions. Do not invent an extension
shape until you have read the Pi docs and the installed Nico Bailon extensions.

## Required evidence before implementation

Read the official Pi extension API:

- `/home/graham/.local/share/pi-node/node-v22.23.2-linux-x64/lib/node_modules/@earendil-works/pi-coding-agent/docs/extensions.md`
- `/home/graham/.local/share/pi-node/node-v22.23.2-linux-x64/lib/node_modules/@earendil-works/pi-coding-agent/examples/extensions/`

Apply current `$brave-search` results before finalizing public guidance. The
current search receipts used for this standard are:

- `/tmp/bppe-brave-pi.json`: found `https://pi.dev/docs/latest/extensions`, the
  upstream `earendil-works/pi` `docs/extensions.md`, the raw upstream docs, and
  a mirror that documents `pi.sendUserMessage`.
- `/tmp/bppe-brave-nico.json`: found Nico Bailon's `pi-interactive-shell`,
  `pi-intercom`, and `pi-mcp-adapter` repositories.

Use installed Nico repos as concrete implementation examples:

- `/home/graham/.pi/agent/git/github.com/nicobailon/pi-interactive-shell/`
- `/home/graham/.pi/agent/git/github.com/nicobailon/pi-intercom/`
- `/home/graham/.pi/agent/git/github.com/nicobailon/pi-mcp-adapter/`

## Package and module layout

For distributable extensions, copy Nico's package shape:

- `package.json` has `type: "module"`.
- `package.json` declares `pi.extensions` and, when bundled skills exist,
  `pi.skills`.
- Pi host packages and `typebox` are `peerDependencies`, not vendored copies.
- `scripts.test` exists; TypeScript-heavy extensions also have `typecheck`.
- `files` explicitly lists shipped modules, skills, examples, and README assets.
- `index.ts` registers the extension and delegates nontrivial logic to modules.

Keep modules separated by responsibility:

| Concern | Pattern from Nico extensions |
| --- | --- |
| User-facing registration | `index.ts` |
| Config loading/merge | `config.ts` (`pi-interactive-shell`, `pi-intercom`, `pi-mcp-adapter`) |
| Long-lived sessions | `session-manager.ts`, `runtime-coordinator.ts`, broker client/runtime modules |
| UI overlays/panels | `overlay-component.ts`, `mcp-setup-panel.ts`, `ui/**` |
| Output bounding | `mcp-output-guard.ts`, `tool-result-renderer.ts` |
| Tests | `*.test.ts`, `__tests__/`, `conformance/run.sh` |

Do not hide complex parsing, state transitions, subprocess handling, or output
truncation inside one giant `index.ts`.

## Pi APIs by use case

Use the smallest Pi event/API that owns the behavior:

| Need | Pi event/API |
| --- | --- |
| Add per-turn instruction | `before_agent_start` |
| Rewrite/block user input | `input` |
| Block a dangerous tool call | `tool_call` |
| Modify tool evidence | `tool_result` |
| Reject or replace assistant prose | `message_end` |
| Force another model attempt | `pi.sendUserMessage(..., { deliverAs: "followUp" })` |
| Wake the model after an event | `pi.sendMessage(..., { triggerTurn: true })` |
| Register agent tools | `defineTool` with `Type.Object` schemas |
| Show operator-visible status | `ctx.ui.notify`, `ctx.ui.setStatus`, `ctx.ui.setWidget` |
| Open rich UI | `ctx.ui.custom`, gated by `ctx.hasUI` / `ctx.mode` |
| Clean long-lived resources | `session_shutdown`, `dispose`, abort/teardown handlers |

If a feature can run headless, it must not require `ctx.ui.custom`. Follow
`pi-mcp-adapter`: notify that the interactive panel is unavailable and give a
CLI/config fallback when `ctx.hasUI` is false or the mode cannot show UI.

## Tool schemas and result surfaces

Custom tools are user-visible APIs. Use Nico's `defineTool` + `Type.Object`
style, and keep these rules:

- Every parameter has a bounded schema and description.
- Tool return content is concise; put bulky machine-readable data in `details` or
  a saved artifact.
- Errors are structured and name the next valid action.
- Do not dump arbitrary MCP/provider output into the model context.
- Use an output guard pattern like `guardMcpOutput` in `mcp-output-guard.ts`:
  normalize blocks, bound text, preserve images separately, spill oversized raw
  results, and expose the spill location in details.

## Lifecycle, concurrency, and cleanup

Nico's extensions are long-running because they own PTYs, broker sockets, MCP
server runtimes, OAuth callbacks, monitors, and UI panels. Copy the cleanup
contract even for smaller extensions:

- Register lifecycle handlers such as `session_start` and `session_shutdown`.
- Track ownership/generation so stale async callbacks cannot mutate a newer
  session.
- Provide `dispose` for sessions, overlays, monitors, sockets, and panels.
- Use explicit abort/timeouts for subprocesses and network calls.
- When a background process remains alive, expose a session id and status widget
  rather than hiding it.

## Config and trust boundaries

- Prefer global config under `~/.pi/agent/...` plus project overrides only after
  project trust is established.
- Read config through a dedicated loader, validate types, and use safe defaults.
- Never execute repository text as code merely because a config file names it.
- Treat extensions as full-permission code. Do not patch Pi internals or
  `node_modules` for normal behavior.

## Desperation guards must be deterministic

If the extension exists because agents ignored prose, do not ask the same agent
to judge itself.

- Put the decision in a deterministic checker script.
- The extension calls the checker and uses its exit code.
- The checker prints exact rejection reasons.
- The rejected assistant answer must not remain the accepted final answer.
- Queue a forced retry with checker diagnostics using
  `pi.sendUserMessage(..., { deliverAs: "followUp" })`.
- If a retry fails, queue another retry or hand off to the human with a rejection
  notice; never allow the lazy answer as success.

## Final-report guards

Reject reports that launder failure as progress:

- vague unresolved-work language without exact rows;
- `Committed and pushed`, branch names, SHAs, or hook status used as the result;
- `mostly done`, `partially complete`, `remaining gates`, `open items`, or
  `what remains` without exact gate IDs;
- counts that do not include rows and proof boundaries;
- progress reports with no immutable `goal-drift` boundary.

Require this shape:

```text
Progress:
- VERIFIED: <concrete user-visible change or artifact outcome>
MET: <n>
UNMET: <n>
ABANDONED: <n>
Immutable Goal: <goal-drift status and hash>
- UNMET `Gx`: failed condition: <exact condition>. Next legal command:
  <command/owner>. Receipt: <path>. Proof boundary: <what was and was not proven>.
```

## Executable evaluation is mandatory

This skill is a standard, but it still ships executable gates. Any Pi extension
skill or package must include `$agentic-evals` posture, not just prose.

Minimum fixture requirements:

- `fixtures/agentic_eval.json` version 2.
- `trials >= 2`.
- At least one positive real-world case using a script, skill entrypoint,
  test runner, or live API path.
- At least one negative or adversarial case that proves the checker fails when a
  required rule is removed.
- `capability_claims` and `seams` for any operational capability.
- Explicit proof boundary: what the eval proves and what it does not prove.

The canonical validator for this skill is:

```bash
python3 skills/best-practices-pi-extensions/scripts/check_pi_extension_standard.py \
  --skill-dir skills/best-practices-pi-extensions \
  --alias-dir skills/best-practices-pi-extension
```

Run the agentic eval with:

```bash
skills/agentic-evals/run.sh run skills/best-practices-pi-extensions/fixtures/agentic_eval.json
skills/agentic-evals/run.sh run skills/best-practices-pi-extension/fixtures/agentic_eval.json
```

## Validation checklist before reporting success

1. `best-practices-skills/scripts/validate_skill.py` passes for the canonical
   skill and the alias.
2. `scripts/check_pi_extension_standard.py` passes against the canonical skill
   and alias.
3. `$agentic-evals` fixture passes and includes negative/adversarial cases.
4. If code changed, package tests/typecheck run (`npm test`, `vitest`, `tsx
   --test`, or the extension's actual script).
5. If a Pi extension changed, run a live Pi print-mode or isolated extension-load
   test and read back stdout/stderr.
6. Report the proof boundary; Git metadata and unit tests are supporting
   evidence only.
