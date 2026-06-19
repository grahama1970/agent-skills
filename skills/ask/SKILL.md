---
name: ask
description: >
  Use when the user asks to query project memory, ask an oracle, use WebGPT or
  another browser-backed reviewer, run persona/roundtable/deep-review workflows,
  generate image prompts, check OS/project health through composed skills, or run
  an ask DAG. This skill is the executable /ask runtime; do not replace it with
  an informal subagent, plain web search, or hand-written review.
triggers:
  - $ask
  - /ask
  - ask oracle
  - WebGPT review
  - deep review
  - parallel review
  - roundtable
  - persona review
  - CAE gap review
  - browser oracle
  - ask DAG
provides:
  - >
    Executable ask runtime for memory-backed answers, oracle calls, reviews,
    browser-backed review, persona workflows, image generation, and DAG runs.
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

If the user names `$ask`, `/ask`, an ask mode, WebGPT, oracle, deep review,
parallel review, roundtable, argue, CAE gap review, or ask DAG, read this whole
file before acting. Then use the real runtime entrypoint unless the user
explicitly asks for a fallback or the runtime is unavailable and that fallback
is reported.

Do not substitute `spawn_agent`, a plain model call, a plain web search, a
manual summary, or an invented review for `$ask`.

## Runtime Entrypoint

Run commands from this directory:

```bash
cd /home/graham/workspace/experiments/agent-skills/skills/ask
./run.sh --help
./run.sh ask --help
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
- Pass the bundle to the documented ask mode. Do not compress a review target
  into an informal prompt when the mode has a target option.
- Report artifact paths as evidence. WebGPT, browser reviewers, or model
  reviewers are not deterministic proof by themselves.
- Close only from local deterministic proof appropriate to the task: tests,
  schema checks, endpoint responses, screenshots, database/query evidence, or
  generated artifact validation.
- Fail closed when tab binding, target file, reviewer configuration, browser
  state, or runtime artifact creation is missing.
- Use readiness language when proof is incomplete: `NOT_READY`,
  `NOT_ESTABLISHED`, `NEEDS_ATTENTION`, or `BLOCKED`, with the missing proof
  named explicitly.

## Mode Router

Use the narrowest mode that matches the user request.

| Request | Runtime pattern | Required details |
| --- | --- | --- |
| Memory-backed question | `./run.sh ask "<question>" --json` | Include scope when relevant. |
| Oracle answer | `./run.sh ask "<question>" --oracle ... --json` | Choose backend/model/persona explicitly when requested. |
| WebGPT/browser review | `./run.sh ask "<question>" --webgpt ... --json` or documented browser mode | Use bound tab/config; attach local target content when browser cannot read paths. |
| Deep review | `./run.sh ask "<question>" --deep-review --deep-review-target <path> ... --json` | Pass complete target bundle; return `review.md` and `review.json`. |
| Parallel review | `./run.sh ask "<question>" --parallel-review ... --json` | State reviewer count/focus and preserve per-reviewer outputs. |
| Roundtable/argue | `./run.sh ask "<question>" --roundtable ... --json` or argue mode | Name personas and rounds; do not invent missing personas silently. |
| CAE gap review | documented CAE gap mode | Include current claim, evidence, gaps, and acceptance gate. |
| Ask DAG | `./run.sh ask "<question>" --dag-file <graph.json> ... --json` | Preserve DAG manifest, node outputs, and fail-closed events. |
| Image generation | documented image mode | Preserve prompt, provider response, output path, and review artifact. |
| OS/project health | `./run.sh os ... --json`, `./run.sh doctor ... --json` | Report degraded dependencies, not green-by-absence. |
| Status/config | `./run.sh status ... --json`, `./run.sh config doctor ... --json` | Use for artifact inspection and readiness preflight. |

## Browser And WebGPT Rules

- A browser tab cannot inspect bare local paths unless the runtime attaches file
  contents or serves an artifact URL. Include readable target content in the
  bundle when needed.
- Use the configured tab id when available. If the tab is missing, wrong, stale,
  or cannot be proven to match the requested reviewer, stop with
  `NEEDS_ATTENTION`.
- Do not use raw `surf` as a substitute for `$ask`; use it only for transport
  debugging or when an ask reference explicitly routes there.
- Explicit `$ask webgpt ...` calls default to the WebGPT browser timeout
  (`ASK_WEBGPT_TIMEOUT`, 900 seconds) unless `--oracle-timeout` is supplied,
  and to ChatGPT reasoning `Pro` (`ASK_WEBGPT_REASONING`) unless a caller
  explicitly overrides the WebGPT reasoning label.
- Surf may also write `round-*/02_response.md.receipt.json`: `prepared_prompt`
  means no ChatGPT acceptance proof yet, while `submitted_to_chatgpt` is a
  transport receipt distinct from final response proof.
- Browser review output is reviewer evidence. It still must be reconciled
  against repository state and deterministic local checks before closure.

## Review Contracts

Load only the reference needed for the selected mode:

- Deep review: `docs/ASK_DEEP_REVIEW_CONTRACT.md`
- Parallel review: `docs/ASK_PARALLEL_REVIEW_CONTRACT.md`
- Argue/roundtable: `docs/ASK_ARGUE_CONTRACT.md`
- CAE gap review: `docs/ASK_CAE_GAP_REVIEW_CONTRACT.md`
- SPARTA preflight: `docs/ASK_SPARTA_PREFLIGHT_CONTRACT.md`
- Collaboration/status: `docs/ASK_COLLABORATION_STATUS_CONTRACT.md`
- Human chat examples: `docs/HUMAN_CHAT_EXAMPLES.md`
- WebGPT reliability: `docs/WEBGPT_EXECUTION_RELIABILITY.md`
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
./run.sh status --run <ask_id> --json
```

Opt-in live sanity checks are intentionally outside the default test suite:

```bash
uv run python scripts/live_sanity_report.py --plan-only --profile smoke
uv run python scripts/live_sanity_report.py --allow-live --profile smoke
uv run python scripts/dag_negative_sanity.py
uv run python scripts/dag_e2e_sanity.py
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
