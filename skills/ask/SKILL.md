---
name: ask
description: >
  Use when the user asks to query project memory, ask an oracle, use supported
  browser-backed reviewers, run Tau roundtable/single-handler workflows,
  ask Pi-native subagents from within Pi, run persona/deep-review workflows,
  generate image prompts, check OS/project health through composed skills, or run
  an ask DAG. This skill is the executable /ask runtime; do not replace it with
  an informal subagent, plain web search, or hand-written review; inside Pi,
  explicit Pi-native subagent targets are routed through the pi-subagents tool as
  an Ask target type.
triggers:
  - $ask
  - /ask
  - ask oracle
  - deep review
  - parallel review
  - roundtable
  - persona review
  - CAE gap review
  - browser oracle
  - Pi subagent
  - ask subagent
  - local subagent
  - ask DAG
  - Tau DAG
  - reasoning effort
  - select reasoning level
  - compete
  - bakeoff
  - captcha security evaluation
provides:
  - >
    Executable ask runtime for memory-backed answers, oracle calls, reviews,
    supported browser-backed review, Pi-native subagent advisory/worker calls,
    Tau single-handler and roundtable workflows, Tau compete/bakeoff workflows,
    persona workflows, image generation, ask/scillm-style DAG runs, and strict
    Tau DAG runs.
  - >
    Evidence artifacts for each run: request, status, events, and mode-specific
    review outputs.
composes:
  - triage-error
  - memory
  - scillm
  - surf
  - captcha
  - subagent-runner
  - pi-subagents
  - browser-oracle
  - create-report
  - tau
  - interview
  - best-practices-roundtable
  - best-practices-competition
  - agentic-evals
complies:
  - best-practices-skills
  - best-practices-tau-dag
taxonomy:
  - orchestration
  - retrieval
  - review
  - validation
  - browser
  - resilience
allowed-tools:
  - Bash
  - Read
  - Write
  - Edit
  - MultiEdit
  - Glob
  - Grep
  - mcp__surf__*
  - mcp__browser_oracle__*
  - subagent
disciplines:
  - agentic-orchestration
  - research-retrieval
---

# ask

## Stop First

If the user names `$ask`, `/ask`, an ask mode, oracle, deep review,
parallel review, roundtable, argue, CAE gap review, or ask DAG, read this whole
file before acting. Then use the real runtime entrypoint unless the user
explicitly asks for a fallback or the runtime is unavailable and that fallback
is reported.

Do not substitute `spawn_agent`, a plain model call, a plain web search, a
manual summary, or an invented review for `$ask`.

## Runtime Entrypoint

Run commands from this directory. Pi skill-command syntax such as
`/skill:ask webgpt What is 2 + 2?` is a first-class shortcut: the leading
browser handler (`webgpt`, `webclaude`, `webkimi`, `webgemini`, or `webgrok`)
routes to a Tau `single-call` browser-handler DAG with `--execute --json`. Inline
Pi skill references such as `$ask webgpt What is 2 + 2?` and the spaced natural
language spelling `$ask web gpt What is 2 + 2?` must be treated the same way
(`web gpt` normalizes to `webgpt`). This is only a compatibility shortcut for Pi
users; it must not use the removed direct WebGPT oracle path.

`./run.sh tau-dag "<request>"` maps to the Typer `tau-dag run` subcommand
internally. `./run.sh team-plan "<request>" --team <preset>` renders a
role-based multi-agent plan and frozen Tau DAG preview; execution requires
explicit `--execute --live` (see README "Team Orchestration").

```bash
cd skills/ask
./run.sh --help
./run.sh webgpt What is 2 + 2?
./run.sh webgpt --compile-only What is 2 + 2?
./run.sh ask --help
./run.sh tau-dag run --help
```

Every nontrivial run must preserve the runtime artifacts. The standard artifact
set is:

- `<ask_id>.request.json`
- `<ask_id>.status.json`
- `<ask_id>.events.jsonl`
- mode-specific outputs such as `review.md`, `review.json`, DAG manifests, or
  browser evidence

Runtime artifacts default under `.ask_artifacts/runs/<ask_id>` or the provided
`--run-output-root`. For long, live, or generated runs prefer a storage-backed
root such as `/mnt/storage12tb/skills/ask/outputs/...`. Do not commit generated
ask artifacts.


## Deep-Dive References (read on demand)

| Before doing this | Read |
| --- | --- |
| `team-plan` with a plan file; `status --run --projection` | `references/plans-and-status.md` |
| Explicit Pi-native subagent target | `references/pi-subagents.md` |
| `herdr list/who/send` to another agent's pane | `references/herdr.md` |
| Choosing one-shot vs roundtable vs compete; model/effort selectors | `references/modes.md` |
| Panel audits, seat roster, rate-limited seats, webclaude policy | `references/seats-and-audits.md` |
| Executing/supervising any live run (monitoring, windows, payload matrix, unblock, drift) | `references/operations.md` |
| Any run failure | `references/diagnosis.md` |
| Compiling/executing any multi-seat DAG (roundtable/compete/creator-reviewer) | `references/workflows.md` |
| Any browser-handler execution | `references/browser.md` |

## Four Kinds Of Target

`/ask` addresses four peer target types. They differ in transport, not in
standing:

| Target | Example | Transport owner |
| --- | --- | --- |
| **Herdr session** — a live agent in a pane | `memory`, `w11:p13` | `$monitor-herdr` via `herdr pane run` |
| **Model call** — API/model handler | `gpt-5.5-high`, `Codex-opus-5-high`, `deepseek-ai/DeepSeek-V3.2-TEE` | `$tau` (SciLLM is internal to Tau) |
| **Web model** — browser-backed reviewer (chat tab, NOT the agentic model; see the `webclaude` warning below) | `webgpt`, `webclaude`, `webkimi` | `$surf` + `$browser-oracle` |
| **Pi-native subagent** — local Pi child advisor/worker | `pi reviewer`, `subagent general-purpose`, `local coder` | `pi-subagents` native `subagent` tool |

A project agent should not care which side is browser, model, Herdr session, or
Pi-native subagent beyond naming the target.

## Project-Agent Quickstart

Start here when the user asks for a single model call, roundtable, competition,
or creator-reviewer loop. Use one of these shapes; do not invent a custom
orchestration path.

| User intent | Command shape |
| --- | --- |
| One handler answers | `./run.sh tau-dag "<task>" --repo <repo> --target <target> --immutable-goal "<goal>" --handler <handler-or-model> --execute --json` |
| Roundtable | `./run.sh tau-dag "<shared task>" --repo <repo> --target <target> --immutable-goal "<goal>" --dag-template roundtable --handler <a> --handler <b> --topology concurrent --execute --json` |
| Competition | `./run.sh compete "<isolated task>" --repo <repo> --target <target> --immutable-goal "<goal>" --handler <a> --handler <b> --criterion <criterion> --execute --json` |
| One-shot (per-seat answers, no consensus) | `./run.sh one-shot "<question>" --handler <a> --handler <b> --handler <c>` — N independent single-call lanes run concurrently; each returns its own nonce-bound answer or a named blocker. Partial answers are DEGRADED-but-usable (exit 0 at or above `--min-answered`); a roundtable's quorum refusal never applies here. |
| Pi-native subagent from inside Pi | `subagent({ action: "list" })`, then `subagent({ agent: "<agent>", task: "<task>" })` or one `workflowScript` fanout. This is for explicit `pi`/`subagent`/`local reviewer` targets only; it is not a replacement for Tau/browser handlers. |
| Creator then reviewer | `./run.sh tau-dag "<creator task then reviewer verdict>" --repo <repo> --target <target> --immutable-goal "<goal>" --dag-template creator-reviewer --handler <creator> --handler <reviewer> --topology sequential --execute --json` |
| Diagnose/fix/close GitHub issues | `./run.sh fix-issues --repo <owner/name> --issue <N> [--issue <M>] [--handler gpt-5.5] [--execute]` — gathers each issue via `gh`, diagnoses through a live one-shot handler into structured cause/fix JSON with the **debugger ladder gate** (`needs_debugger` recommends `$debugger` only when the failing transition is in-process runtime state no artifact explains), and is fail-closed: dry-run by default; `--execute` closes an issue ONLY after its named verify command (typically an `$agentic-evals` fixture) actually passes. No verify → `blocked`; failing verify → `verify-failed`, issue stays open. Per-issue receipts under `outputs/fix-issues/`. Gate: `fixtures/fix_issues.json`. |

Handlers are peers even when their transports differ. Browser handlers
(`webgpt`, `webclaude`, `webkimi`, `webgemini`, `webgrok`) run through `$surf`
and `$browser-oracle`. API/model handlers such as `gpt-5.5-high`,
`gpt-5.5-xhigh`, `Codex-opus-5-high`, or
`chutes deepseek-ai/DeepSeek-V3.2-TEE` are routed by Tau. Project agents should
not care which side is browser or API beyond naming the handler.


Handlers are peers whether browser-backed (`webgpt`, `webclaude`, `webkimi`,
`webgemini`, `webgrok` via `$surf`/`$browser-oracle`) or API-backed
(`gpt-5.5-high`, `claude-opus-5-high`, `chutes <provider/model>` via Tau).
Before executing any multi-seat DAG: compile first (omit `--execute`), show the
human the printed ASCII chart, and run only on confirmation. Full mode examples
and selector rules: `references/modes.md`. Full protocols and fail-closed
tables: `references/workflows.md`.

## Non-Negotiables For Every Run

- An explicit immutable goal (`--immutable-goal` or a labeled `Immutable goal:`
  line) is required for roundtable, creator-reviewer, and compete; missing goal
  fails preflight with `NEEDS_INTERVIEW` before any handler is contacted.
- Roundtables are ALWAYS `--topology concurrent` with an identical packet for
  every seat. Compete candidates are isolated and never see each other.
- Executed DAGs must be monitored to a terminal verdict via the run's JSON
  stream artifacts (`events.jsonl`, `dag-progress.json`, node receipts,
  `execution-status.json`); do not launch and walk away.
- `PASS` is reviewer/model evidence only; local closure requires deterministic
  local proof. `DEGRADED`/`NEEDS_ATTENTION`/rate limits are lane-local: keep
  usable seats, follow the failed lane's recovery packet.
- Failures are non-silent: every failed lane exposes `failure_code`, a recovery
  packet, and `next_command`/ticket instruction. On any failure, read
  `references/diagnosis.md` and dispatch on the owning receipt before theorising.
- Direct WebGPT oracle routing (`$ask chatgpt`, `--oracle-backend webgpt`,
  `--webgpt-*`) fails closed; Tau browser handlers remain supported.
- **Follow-up continuity:** every browser lane's node receipt / `response.meta.json`
  must carry `controlled_tab_id` and the conversation URL; a null tab id is a
  failed handoff. When the human may ask clarifying or follow-up questions,
  run with `--browser-tab-lifecycle fresh-keep` (or `reuse-bound`) — the default
  `auto`/fresh-temporary CLOSES the window after the run, killing the
  conversation. After the run, report the tab id + conversation URL and bind
  them (`skills/browser-oracle/run.sh bind <project> --backend <b> --tab-id <id>
  --url <url> --manual`) so the follow-up targets the same session.
- `webclaude` is a claude.ai chat tab, testing-only — NOT agentic Claude. Prefer
  `claude-fable-low`, then `claude-opus-4-8-high` (see
  `references/seats-and-audits.md`).

## Mode Router

Use the narrowest mode that matches the user request.

| Request | Runtime pattern | Required details |
| --- | --- | --- |
| Memory-backed question | `./run.sh ask "<question>" --json` | Include scope when relevant. |
| Oracle answer | `./run.sh ask "<question>" --oracle ... --json` | Choose backend/model/persona explicitly when requested. |
| Pi browser-handler shortcut | `./run.sh webgpt What is 2 + 2?` from `/skill:ask webgpt What is 2 + 2?` | Rewrites to Tau `single-call` with `--handler webgpt --execute --json`; use `--compile-only` to emit the DAG without live browser transport. |
| Single named handler | `./run.sh tau-dag "<request>" --handler <handler-or-model> --json` | Browser handlers use `$surf`; non-browser handlers are `$scillm` model names routed by Tau. Add `--execute` for live transport. |
| Pi-native subagent target | Native Pi `subagent` tool, after `subagent({ action: "list" })` | Only when running inside Pi and the user explicitly names `pi`, `subagent`, `pi-subagent`, `local reviewer`, or `local coder`. Browser/model/Tau Ask requests do not use this route. |
| Multi-handler roundtable | `./run.sh tau-dag "<request>" --handler webclaude --handler gpt-5.5 ... --topology concurrent --execute --json` | Roundtable is prompt-to-Tau-DAG. Browser handlers get an Ask-owned fresh window by default. Preserve `browser-tab-lifecycle.json`, `dag.json`, command specs, handler receipts, and join receipts. |
| Compete / bakeoff | `./run.sh compete "<task>" --handler webgpt --handler webclaude --handler gpt-5.5-high --criterion deterministic-proof --execute --json` | Isolated candidates plus compete scorecard and winner continuation request. Browser/API handlers are peers. Project agent must locally verify features before promotion. |
| Creator-reviewer loop | `./run.sh tau-dag "<request>" --handler <creator> --handler <reviewer> --topology sequential --json` | The reviewer receives prior handler receipts. Pass/fail requests require a verdict in the reviewer response. |
| Supported direct browser oracle | documented browser mode such as `webgemini`, `webkimi`, `webperplexity`, or `cursor-browser` | Use only when the user asks for that direct mode; attach local target content when browser cannot read paths. |
| Deep review | `./run.sh ask "<question>" --deep-review --deep-review-target <path> ... --json` | Pass complete target bundle; return `review.md` and `review.json`. |
| Parallel review | `./run.sh ask "<question>" --parallel-review ... --json` | State reviewer count/focus and preserve per-reviewer outputs. |
| Persona roundtable/argue | `./run.sh ask "<question>" --roundtable ... --json` or argue mode | Persona deliberation only. For web/API handler roundtables, use `tau-dag`. |
| CAE gap review | documented CAE gap mode | Include current claim, evidence, gaps, and acceptance gate. |
| Tau DAG front door | `./run.sh tau-dag "<request>" --repo <repo> --target <target> --solver-model <model> --reviewer-model <model> --criterion <c> --json` | Emits strict `tau.dag_contract.v1` first; uses `$interview` packet when incomplete; add `--execute` to delegate to Tau. |
| Ask/scillm-style DAG file | `./run.sh ask "<question>" --dag-file <graph.json> ... --json` | Use only when the user provides an existing ask/scillm-style DAG file; preserve DAG manifest, node outputs, and fail-closed events. |
| Authorized local CAPTCHA evaluation | Generate `ask.dag.v1` with `../captcha/run.sh ask-dag ...`, then use `./run.sh ask "<request>" --dag-file <graph.json> --json` | Ask owns orchestration; `$captcha` owns authorization and receipts; `$surf` supplies browser-transport proof; ReCAP `dynamic` loopback only. |
| Image generation | documented image mode | Preserve prompt, provider response, output path, and review artifact. |
| OS/project health | `./run.sh os ... --json`, `./run.sh doctor ... --json` | Report degraded dependencies, not green-by-absence. |
| Status/config | `./run.sh status ... --json`, `./run.sh config doctor ... --json` | Use for artifact inspection and readiness preflight. |

## Browser Rules (summary)

### MANDATORY prompt/bundle preflight (run before EVERY browser submit)

Surf rejects prompts/bundles referencing unreadable local paths or `~<digits>`
tokens (agent-skills#973), failing late as `browser_submit_not_accepted`. Run
the fail-closed preflight on the prompt AND every `--attach-file` first:

```bash
python3 skills/ask/scripts/browser_prompt_preflight.py --prompt "<prompt>" <each --attach-file>
# exit 0 = safe to submit; exit 2 = offending tokens listed, fix them first
```

Everything else browser-side — tab lifecycle (`auto` = fresh temporary window),
stale-binding refresh, conversation rollover, rate-limit/capacity cooldowns,
transport-vs-provider classification, attachment matrix — is in
`references/browser.md` and `references/operations.md`. Read them before any
browser-handler execution.

## Review Contracts

Load only the reference needed for the selected mode:

- Deep review: `docs/ASK_DEEP_REVIEW_CONTRACT.md`
- Parallel review: `docs/ASK_PARALLEL_REVIEW_CONTRACT.md`
- Argue/roundtable: `docs/ASK_ARGUE_CONTRACT.md`
- CAE gap review: `docs/ASK_CAE_GAP_REVIEW_CONTRACT.md`
- SPARTA preflight: `docs/ASK_SPARTA_PREFLIGHT_CONTRACT.md`
- Human chat examples: `docs/HUMAN_CHAT_EXAMPLES.md`
- Project knowledge: `docs/PROJECT_KNOWLEDGE.md`
- Review chains: `docs/chains/`
- Reviewer definitions: `docs/reviewers/`
- Templates: `docs/templates/`

When a reference file is selected, read it completely before running that mode.

## Command Reference

For common commands, use the examples above. For live browser workflow proof,
validate the returned run directory instead of trusting command exit status:

```bash
scripts/validate_live_browser_workflow.py <run-dir> \
  --workflow-mode roundtable \
  --handler webgpt --handler webclaude --handler webkimi --handler webgemini \
  --min-concurrency 4 \
  --require-cleanup \
  --json

scripts/validate_live_browser_workflow.py <run-dir> \
  --workflow-mode compete \
  --handler webgpt --handler webclaude --handler webkimi --handler webgemini \
  --min-concurrency 4 \
  --require-cleanup \
  --json
```

The release gate for mixed browser/API roundtable and competition transport is:

```bash
uv run --project skills/ask python \
  skills/ask/evals/live_mixed_dag_e2e.py --iterations 2 --allow-live
```

It resets each bound browser tab to a fresh chat, executes both Tau DAG modes,
and fails unless every browser/API lane and the join are live, non-mocked, and
usable. It can take several hours when providers impose cooldowns.

## Output Expectations

For normal answers, return the answer plus the artifact directory when artifacts
exist. For reviews, lead with findings and include the artifact paths. For
blocked or degraded runs, return the failing command, missing proof, and next
deterministic gate.

Do not say work is complete, verified, green, or fixed unless the artifacts and
local checks prove it.

## Related Skills

- Use `$memory` before ask when the task is about prior project context.
- Use `$scillm` only for direct model/runtime diagnosis after reading its skill.
- Use `$surf` or `$browser-oracle` only when this skill or a selected reference
  routes browser transport there.
- Use `$best-practices-roundtable` when leading or synthesizing a substantial
  roundtable.
- Use `$best-practices-competition` when leading or judging a substantial
  compete/bakeoff workflow.
- Use `$best-practices-skills` when modifying this skill or its scripts.

## Ecosystem

Member of the agent-governance ecosystem (see `skills/agent-ecosystem/SKILL.md`
for the shared map, mermaid graph, and the `pi.receipt_envelope.v1` boundary
envelope). Produces: `tau.dag_contract.v1` bundles, recovery packets with triage codes. Consumes: escalation payloads from `pi.agent_status.v1` needs_* states. Envelope-wrapped
boundary events: dispatch, escalation. Failure names come only from the triage-error
catalog or minted `*_unclassified_<8hex>` codes; ambiguous labels are
unrepresentable ecosystem-wide.
