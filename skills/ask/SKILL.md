---
name: ask
description: >
  Use when the user asks to query project memory, ask an oracle, use supported
  browser-backed reviewers, run Tau roundtable/single-handler workflows,
  run persona/deep-review workflows,
  generate image prompts, check OS/project health through composed skills, or run
  an ask DAG. This skill is the executable /ask runtime; do not replace it with
  an informal subagent, plain web search, or hand-written review.
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
  - ask DAG
  - Tau DAG
provides:
  - >
    Executable ask runtime for memory-backed answers, oracle calls, reviews,
    supported browser-backed review, Tau single-handler and roundtable
    workflows, persona workflows, image generation, ask/scillm-style DAG runs,
    and strict Tau DAG runs.
  - >
    Evidence artifacts for each run: request, status, events, and mode-specific
    review outputs.
composes:
  - memory
  - scillm
  - surf
  - subagent-runner
  - browser-oracle
  - create-report
  - tau
  - interview
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

Run commands from this directory. `./run.sh tau-dag "<request>"` maps to the
Typer `tau-dag run` subcommand internally.

```bash
cd skills/ask
./run.sh --help
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

## Required Behavior

- Build a concrete bundle before review or oracle escalation: objective, target
  files/artifacts, commands already run, uncertainty, exact question, and
  acceptance gates.
- For human requests that ask a named handler/model to answer, solve, review, or
  collaborate, use `./run.sh tau-dag ...` as the modern front door. `$ask`
  compiles the request into a strict `tau.dag_contract.v1` bundle, emits
  `dag.json` before execution, uses `$interview` when required DAG fields are
  missing, and delegates execution and live status/viewer polling to `$tau`.
- Treat modern roundtable and creator-reviewer loops as prompt-to-Tau-DAG. The
  user should only need to name handlers and shape: single call, concurrent
  roundtable, sequential roundtable, or explicit multi-step DAG. It must not
  matter to the user whether a handler is browser-backed or API-backed except
  for the handler/model name they request.
- Pass the bundle to the documented ask mode. Do not compress a review target
  into an informal prompt when the mode has a target option.
- Report artifact paths as evidence. Browser reviewers or model
  reviewers are not deterministic proof by themselves.
- Direct WebGPT/ChatGPT oracle routing is not an `$ask ask` backend: `$ask
  webgpt`, `$ask chatgpt`, `--oracle-backend webgpt`, `--webgpt-*`, and
  `webgpt-project` must fail closed. This does not ban Tau roundtable
  `webgpt`: `webgpt` is a supported Tau browser handler routed through `$surf`.
- Close only from local deterministic proof appropriate to the task: tests,
  schema checks, endpoint responses, screenshots, database/query evidence, or
  generated artifact validation.
- Fail closed when tab binding, target file, reviewer configuration, browser
  state, or runtime artifact creation is missing.
- Use readiness language when proof is incomplete: `NOT_READY`,
  `NOT_ESTABLISHED`, `NEEDS_ATTENTION`, or `BLOCKED`, with the missing proof
  named explicitly.
- Provider/model execution in generated Tau DAGs is Tau-owned: `$ask` emits
  local adapter nodes and Tau dispatches their command specs; those adapters
  call the `$scillm` container service (`http://127.0.0.1:4001` by default).
  Real provider calls require explicit `--allow-provider-calls`. Use
  `--local-fixture` only for Tau scheduler sanity proof; report that it does
  not prove provider/model behavior.

## Single Calls And Roundtables

Use `./run.sh tau-dag` for current handler/model orchestration.

- **Single call**: use one Tau handler or one solver/reviewer model. This is the
  path for "ask webclaude", "ask webkimi", "ask webgemini", "ask webgpt", or one
  API-backed model such as `gpt-5.5`, `claude-sonnet-4-6`, or another model
  routed by `$tau` through `$scillm`.
- **Roundtable**: use repeatable `--handler` values and `--topology concurrent`
  or `--topology sequential`. A roundtable compiles to `tau.dag_contract.v1`
  with handler nodes and a join node.
- **Creator-reviewer loop**: use `--topology sequential` and list the creator
  handler first, then reviewer handlers. Downstream handlers receive prior
  handler receipts and response excerpts. If the request asks for pass/fail
  review, the reviewer prompt requires `VERDICT: PASS`, `VERDICT: FAIL`, or
  `VERDICT: NEEDS_ATTENTION`.
- **Explicit DAG**: describe the dependency order in the request when the user
  wants multiple steps. Use `--topology sequential` for a linear handler chain;
  use `--topology concurrent` when handlers can work independently before join.
- **Supported browser handlers**: `webgpt`, `webclaude`, `webkimi`,
  `webgemini`. Aliases normalize as `gpt -> webgpt`, `claude -> webclaude`,
  `kimi -> webkimi`, and `gemini -> webgemini`.
- **Supported API handlers**: any explicit non-browser handler label is treated
  as a `$scillm` model name and emitted as a Tau-owned `scillm.chat` adapter
  node. `$ask` does not decide provider internals.
- **Browser transport**: browser handlers execute through `$surf` and
  `$browser-oracle` from Tau command specs. Use `--handler-project
  handler=project` when the browser-oracle project differs from the handler
  name, for example `--handler-project webgpt=tau`.
- **Evidence**: `--json` returns the Ask Tau bundle path, provider/handler gate,
  and Tau execution receipt when `--execute` is used. Preserve `dag.json`,
  command specs, node receipts, and join receipts.

Current command patterns:

```bash
# Compile a single browser-handler call without executing it.
./run.sh tau-dag "Ask webclaude to answer: <prompt>" \
  --repo local/ask --target single-webclaude \
  --handler webclaude --json

# Execute a single browser-handler call through Tau and Surf/browser-oracle.
./run.sh tau-dag "Ask webkimi to answer: <prompt>" \
  --repo local/ask --target single-webkimi \
  --handler webkimi --execute --json

# Compile a concurrent browser roundtable, then join.
./run.sh tau-dag "Roundtable these handlers concurrently, then join." \
  --repo local/ask --target roundtable-web \
  --handler webclaude --handler webkimi --handler webgemini --handler webgpt \
  --handler-project webgpt=tau \
  --topology concurrent --json

# Execute a sequential browser roundtable.
./run.sh tau-dag "Ask webclaude, pass its answer to webkimi, then have webgpt review." \
  --repo local/ask --target sequential-web \
  --handler webclaude --handler webkimi --handler webgpt \
  --handler-project webgpt=tau \
  --topology sequential --execute --json

# Creator-reviewer loop with a browser creator and pass/fail browser reviewer.
./run.sh tau-dag "Ask webgpt to do the work, then ask webclaude to review the work for pass/fail." \
  --repo local/ask --target webgpt-webclaude-passfail \
  --handler webgpt --handler webclaude \
  --handler-project webgpt=tau \
  --topology sequential --execute --json

# Mixed API/browser loop. The API handler is routed by Tau through SciLLM.
./run.sh tau-dag "Ask gpt-5.5 to draft an answer, then ask webclaude to review it for pass/fail." \
  --repo local/ask --target api-webclaude-passfail \
  --handler gpt-5.5 --handler webclaude \
  --topology sequential --execute --json

# API/model DAG with real provider calls requires explicit provider consent.
./run.sh tau-dag "Solve X with two solvers, then review." \
  --repo local/tau --target issue-123 \
  --solver-model gpt-5.6-xhigh --solver-model gpt-5.6-xhigh \
  --reviewer-model claude-fable --criterion correctness \
  --allow-provider-calls --execute --json
```

## Mode Router

Use the narrowest mode that matches the user request.

| Request | Runtime pattern | Required details |
| --- | --- | --- |
| Memory-backed question | `./run.sh ask "<question>" --json` | Include scope when relevant. |
| Oracle answer | `./run.sh ask "<question>" --oracle ... --json` | Choose backend/model/persona explicitly when requested. |
| Single named handler | `./run.sh tau-dag "<request>" --handler <handler-or-model> --json` | Browser handlers use `$surf`; non-browser handlers are `$scillm` model names routed by Tau. Add `--execute` for live transport. |
| Multi-handler roundtable | `./run.sh tau-dag "<request>" --handler webclaude --handler gpt-5.5 ... --topology <concurrent|sequential> --json` | Roundtable is prompt-to-Tau-DAG. Preserve `dag.json`, command specs, handler receipts, and join receipts. |
| Creator-reviewer loop | `./run.sh tau-dag "<request>" --handler <creator> --handler <reviewer> --topology sequential --json` | The reviewer receives prior handler receipts. Pass/fail requests require a verdict in the reviewer response. |
| Supported direct browser oracle | documented browser mode such as `webgemini`, `webkimi`, `webperplexity`, or `cursor-browser` | Use only when the user asks for that direct mode; attach local target content when browser cannot read paths. |
| Deep review | `./run.sh ask "<question>" --deep-review --deep-review-target <path> ... --json` | Pass complete target bundle; return `review.md` and `review.json`. |
| Parallel review | `./run.sh ask "<question>" --parallel-review ... --json` | State reviewer count/focus and preserve per-reviewer outputs. |
| Persona roundtable/argue | `./run.sh ask "<question>" --roundtable ... --json` or argue mode | Persona deliberation only. For web/API handler roundtables, use `tau-dag`. |
| CAE gap review | documented CAE gap mode | Include current claim, evidence, gaps, and acceptance gate. |
| Tau DAG front door | `./run.sh tau-dag "<request>" --repo <repo> --target <target> --solver-model <model> --reviewer-model <model> --criterion <c> --json` | Emits strict `tau.dag_contract.v1` first; uses `$interview` packet when incomplete; add `--execute` to delegate to Tau. |
| Ask/scillm-style DAG file | `./run.sh ask "<question>" --dag-file <graph.json> ... --json` | Use only when the user provides an existing ask/scillm-style DAG file; preserve DAG manifest, node outputs, and fail-closed events. |
| Image generation | documented image mode | Preserve prompt, provider response, output path, and review artifact. |
| OS/project health | `./run.sh os ... --json`, `./run.sh doctor ... --json` | Report degraded dependencies, not green-by-absence. |
| Status/config | `./run.sh status ... --json`, `./run.sh config doctor ... --json` | Use for artifact inspection and readiness preflight. |

## Browser Rules

Direct WebGPT/ChatGPT browser oracle workflows have moved out of `$ask ask`.
`$ask webgpt`, `$ask chatgpt`, `--oracle-backend webgpt`, `--webgpt-*`, and
`webgpt-project` must fail closed.

Do not confuse that direct-oracle restriction with Tau roundtable handlers:
`webgpt`, `webclaude`, `webkimi`, and `webgemini` are supported as peer Tau
browser handlers through `$surf`/`$browser-oracle` command specs.

- A browser tab cannot inspect bare local paths unless the runtime attaches file
  contents or serves an artifact URL. Include readable target content in the
  bundle when needed.
- Browser handler failures must emit
  `ask.browser_failure_recovery_packet.v1` in the node artifact directory when
  they can be classified as `repo_access_blocked`, `missing_sentinel`,
  `prompt_too_large_or_stalled`, or `stale_raw_capture`. The packet must include
  `failure_code`, `local_readable_bundle_paths`, `auto_retry_allowed`,
  `auto_retry_blocked_reason`, `next_command`, and `fallback_instruction`.
- Browser auto-retry is allowed only when `$ask` can read a local bundle file
  and the selected Surf handler supports `--attach-file`. A private GitHub URL,
  a bare local path inside the prompt, or a stale raw capture is not enough.
  Without a readable bundle, fail closed and return the recovery packet.
- Use the configured tab id when available. If the tab is missing, wrong, stale,
  or cannot be proven to match the requested reviewer, stop with
  `NEEDS_ATTENTION`.
- Do not use raw `surf` as a substitute for `$ask`; use it only for transport
  debugging, direct project-level WebGPT workflows, or Tau command specs emitted
  by `./run.sh tau-dag`.
- Browser review output is reviewer evidence. It still must be reconciled
  against repository state and deterministic local checks before closure.

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

## Common Commands

```bash
./run.sh config doctor --profile smoke --json
./run.sh doctor --json
./run.sh ask "What do we know about this project?" --scope ask --json
./run.sh ask "Review this target" --deep-review --deep-review-target path/to/file --json
./run.sh tau-dag "Ask webclaude to answer this prompt" --repo local/ask --target single-webclaude --handler webclaude --json
./run.sh tau-dag "Roundtable webclaude, webkimi, webgemini, and webgpt concurrently, then join" --repo local/ask --target roundtable-web --handler webclaude --handler webkimi --handler webgemini --handler webgpt --handler-project webgpt=tau --topology concurrent --json
./run.sh tau-dag "Solve X with two GPT 5.6 xhigh solvers, then Claude Fable reviews" --repo local/tau --target issue-123 --solver-model gpt-5.6-xhigh --solver-model gpt-5.6-xhigh --reviewer-model claude-fable --criterion correctness --criterion maintainability --json
./run.sh tau-dag "Solve X" --repo local/tau --target issue-123 --solver-model gpt-5.6-xhigh --solver-model gpt-5.6-xhigh --reviewer-model claude-fable --criterion correctness --criterion maintainability --execute --local-fixture --viewer-link --json
./run.sh status --run <ask_id> --json
```

Opt-in live sanity checks are intentionally outside the default test suite:

```bash
uv run python scripts/live_sanity_report.py --plan-only --profile smoke
uv run python scripts/live_sanity_report.py --allow-live --profile smoke
uv run python scripts/webclaude_sanity_eval.py --plan-only
uv run python scripts/webclaude_sanity_eval.py --allow-live --project webclaude
uv run python scripts/webkimi_sanity_eval.py --plan-only
uv run python scripts/webkimi_sanity_eval.py --allow-live --project webkimi
uv run python scripts/tau_roundtable_sanity_eval.py --plan-only
uv run python scripts/tau_roundtable_sanity_eval.py --allow-live --output-root /tmp/ask-roundtable-live --timeout-seconds 1800 --json
uv run python scripts/dag_negative_sanity.py
uv run python scripts/dag_e2e_sanity.py
uv run python scripts/tau_dag_e2e_sanity.py --json
uv run python scripts/tau_dag_stress_sanity.py --json
uv run python scripts/tau_dag_e2e_sanity.py --no-local-fixture --allow-provider-calls --require-provider-calls --json
uv run python scripts/persona_delegate_e2e_sanity.py --skip-ask --skip-scillm
```

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
- Use `$best-practices-skills` when modifying this skill or its scripts.
