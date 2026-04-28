# Project Knowledge: ask

**Last updated:** 2026-04-28 00:00 by agent
**Status:** Active development

This file is the human-readable current-state projection for `/ask`
development. Agents should still query `/memory` first, then use this file as
curated context. Memory recall is context, not evidence.

## Current Understanding

- `/ask` is intended to be the front door for zero-cognitive-load questions,
  persona consultation, memory-backed synthesis, and high-value oracle review.
- The oracle path should default to practical high reasoning for high-value
  analytical questions, with `gpt-5.5` and `high` as preferred normal settings
  when available. Reserve `xhigh` for explicit requests and deep-review gates.
- `/ask` should not become `/code-runner`; implementation-time agents may edit
  `/ask`, but runtime deep-review mode must remain read-only except for
  artifacts and telemetry.
- Roundtable and parallel review are separate protocols:
  - roundtable is sequential, stateful persona deliberation
  - parallel review is independent reviewer fanout followed by moderator
    synthesis
- Roundtable should be treated as a state-machine review protocol, not a loose
  group chat: each persona gets a protocol role, sees prior claims, reacts to
  specific claims, and the moderator synthesizes.
- Runner-backed oracle calls use push-style liveness when available:
  `/subagent-runner` emits transcript delta and heartbeat events, `/ask` follows
  `events.jsonl`, and status polling is fallback behavior.
- Normal oracle/persona/roundtable defaults use `high` reasoning for practical
  latency; `xhigh` remains available explicitly and as the default for deep
  review when no explicit reasoning is supplied.
- JSON output improves coverage and auditability, but reasoning depth comes
  from pass-based prompts, bounded evidence, reviewer roles, and verifier gates.
- Deep review now emits both `review.md` and `review.json` under
  `.ask_artifacts/deep-review/<timestamp>/`.
- ask README.md now mirrors the structural onboarding shape of pi-subagents: installation, try-first prompts, what happens, modes, workflows, command reference, configuration, artifacts, development knowledge, validation, troubleshooting, and non-goals.
- `/ask argue` is now a bounded protocol inside `/ask`, not a separate broad
  parity project: it runs constrained for/against roles, applies a fixed judge
  rubric, and returns one of `FOR`, `AGAINST`, `NO_CLEAR_WINNER`, or
  `INSUFFICIENT_EVIDENCE`.
- Prompt quality for `/ask argue` is reviewed through a full prompt payload
  fixture under `docs/prompts_review/`, matching the reviewable-prompt pattern
  used by skills such as `/create-qras`.
- The broader portable-parity work is planned but not executed yet. The current
  plan is `03_ASK_PORTABLE_PARITY_TASKS.yaml`; `/review-plan` returned no
  FAIL-grade issues, but orchestration is intentionally paused until runner
  integration is clean.
- `$orchestrate`, `$code-runner`, and `$scillm` remain the intended execution
  primitives for appropriate tasks. The required update was compatibility and
  safety, not bypassing those skills.

## Recent Decisions

| Date | Decision | Why |
| --- | --- | --- |
| 2026-04-27 | Add a deep-review lane to `/ask` instead of creating a separate review skill. | `/ask` should be the human-facing oracle/review front door. |
| 2026-04-27 | Keep runtime deep review read-only. | Review mode should produce analysis, verdicts, and remediation plans, not patches. |
| 2026-04-27 | Use three-layer read-only enforcement. | Prompt-only read-only behavior is insufficient; runtime controls and git before/after checks are required. |
| 2026-04-27 | Emit `review.md` and `review.json`. | Humans need readable synthesis; automation needs schema-checkable artifacts. |
| 2026-04-27 | Treat JSON as a gate, not intelligence. | Valid JSON can still be shallow; verifier must reject shallow-but-valid outputs. |
| 2026-04-27 | Distinguish `none_found` from `not_assessed`. | Empty issue arrays are only meaningful when backed by inspected evidence. |
| 2026-04-27 | Store summaries and artifact metadata by default, not full transcripts. | Prevent memory pollution from prompts, chatter, diffs, and large repo snippets. |
| 2026-04-27 | Default normal oracle reasoning to `high`, not `xhigh`. | `xhigh` is too slow for default chat use; keep it for explicit calls and deep-review gates. |
| 2026-04-27 | Make semantic E2E validation mandatory. | Empty answers, refusal-style non-answers, missing domain grounding, wrong persona routing, and missing roundtable participants must fail. |
| 2026-04-27 | Keep domain-specific cybersecurity prompts as sanity/E2E fixtures, not README onboarding content. | README should stay developer/provider-neutral while tests prove the real SPARTA/persona/roundtable path. |
| 2026-04-27 | Add explicit run ids and standardized artifact directories. | `/ask status --runs` needs stable runtime objects instead of buried logs. |
| 2026-04-27 | Move reviewer roles into frontmatter specs. | Protocol roles should be inspectable, reusable, and not hidden inside one giant `SKILL.md`. |
| 2026-04-27 | Store saved review chains as YAML specs. | Deep review and parallel review should be repeatable workflows, not ad hoc prompt branches. |
| 2026-04-27 | Treat review-and-fix as a separate worktree-isolated lane. | `/ask` deep review remains read-only; implementation writes require explicit isolation. |
| 2026-04-27 | Add bounded `/ask argue` directly before broad portable-parity work. | Arguing for and against a decision is valuable now and fits the existing adversarial review protocol surface. |
| 2026-04-27 | Use a fixed argue judge rubric by default. | Free-form persona debate is too easy to make shallow; the judge must score evidence strength, failure-mode coverage, assumption quality, target relevance, falsifiability, and implementation cost/risk. |
| 2026-04-27 | Add full prompt payload coverage for `/ask argue`. | Prompt changes need reviewable fixtures, not only CLI assertions. |
| 2026-04-27 | Pause broad `/ask` portable-parity orchestration until `$orchestrate`/`$code-runner`/`$scillm` integration is updated. | The first orchestration run exposed stale backend aliases, wrong `/scillm` endpoint assumptions, and unsafe `git stash` behavior. |
| 2026-04-27 | Keep `$scillm` and `$code-runner` in the `/orchestrate` path. | They remain the right primitives when the task needs LLM inference or bounded iterative code execution; the fix is routing/safety normalization. |

## Open Questions

- [x] Should `/ask` expose `--deep-review` as a first-class CLI mode or infer it
      only from prompt routing? It now supports both.
- [ ] Which runner should own structured-output enforcement when both Codex
      `exec --output-schema` and `/scillm` model calls are available?
- [x] What exact artifact directory should deep-review runs use:
      `.ask_artifacts/deep-review/`.
- [ ] Should `docs/PROJECT_KNOWLEDGE.md` be synced by `/project-knowledge` on
      every durable `/ask` decision, or only at handoff/checkpoint boundaries?
- [ ] Which tests should count as real E2E smoke tests versus deterministic
      monkeypatched protocol tests?
      Current answer: realistic E2E must include domain scope, persona routing,
      and roundtable behavior; deterministic tests remain route/unit coverage.
- [x] Should `/ask` include an argue function? Yes: implement it as a bounded
      adversarial protocol with explicit for/against roles and a fixed judge
      rubric, not as unconstrained chat.
- [x] Does `/ask argue` need a prompt review payload? Yes: the prompt payload
      is now a first-class review artifact under `docs/prompts_review/`.
- [ ] After the `$orchestrate` compatibility patch, should the broad portable
      parity plan run from a fresh isolated worktree? Current answer: yes,
      because `$code-runner` now fails closed on dirty tracked worktrees instead
      of using `git stash`.

## Key Files

| File | Purpose |
| --- | --- |
| `README.md` | GitHub/developer overview for `/ask` |
| `SKILL.md` | Full skill contract and operational instructions |
| `src/ask/ask.py` | Main command implementation |
| `src/ask/ask_routing.py` | Natural-language route inference |
| `src/ask/ask_oracle.py` | Oracle and subagent-backed synthesis |
| `src/ask/deep_review.py` | Deep-review prompt, artifact, and verifier support |
| `src/ask/run_state.py` | Run ids, standardized artifact directories, status files, events, context policy, needs-attention states |
| `src/ask/doctor.py` | Preflight diagnostics for memory, dogpile, scillm, subagent-runner, specs, chains, artifacts, and git |
| `src/ask/reviewer_specs.py` | Frontmatter reviewer specs and dynamic reviewer-angle selection |
| `src/ask/chain_specs.py` | Saved chain specs for repeatable review workflows |
| `src/ask/review_protocols/adversarial_review.py` | Existing roundtable/parallel review protocol support |
| `docs/prompts_review/ASK_ARGUE_PROMPT_PAYLOAD.md` | Full prompt payload fixture for `/ask argue` prompt review |
| `docs/reviewers/` | Protocol-role specs with model/reasoning/fallback/write/inheritance policy |
| `docs/chains/` | Saved deep-review and parallel-review chain definitions |
| `docs/HUMAN_CHAT_EXAMPLES.md` | Human prompt examples and route expectations |
| `docs/ASK_DEEP_REVIEW_CONTRACT.md` | Deep-review runtime and verifier contract |
| `01_ASK_DEEP_REVIEW_TASKS.yaml` | Current implementation plan for deep review |
| `03_ASK_PORTABLE_PARITY_TASKS.yaml` | Planned broad portable-parity implementation, not yet executed |
| `scripts/live_e2e.py` | Live E2E matrix, including semantic answer validation |
| `sanity.sh` | Skill-level deterministic sanity checks |

## Deep Review Contract Summary

Required behavior:

- Resolve an explicit target before reviewing.
- Fail closed if no reliable target exists.
- Run Memory First before bounded context discovery.
- Treat memory as context, not evidence.
- Prefer the requested reasoning profile and record the actual model/profile/reasoning.
- Record downgraded capability in `review.json.execution.capability_degraded`.
- Emit `review.md` and `review.json`.
- Verify required sections, evidence-bearing fields, verdict enum, and
  read-only invariants.
- Fail verifier checks for generic boilerplate, missing evidence, unsupported
  safety claims, or required sections marked `not_assessed`.

Allowed final verdicts:

- `SAFE`
- `SAFE_WITH_CONDITIONS`
- `NOT_SAFE`
- `INSUFFICIENT_EVIDENCE`

## Validation State

Latest implementation checks, as of 2026-04-27:

- Deep-review contract doc exists.
- Deep-review verifier tests exist.
- Deep-review context and artifact tests exist.
- `sanity.sh` includes deep-review tests.
- Targeted regression suite: `30 passed`.
- Realistic domain E2E: `3/3` passed using `--scope sparta`, stored Brandon
  persona routing, and Brandon/Margaret/Jennifer roundtable.
- E2E validators now fail empty answers, `No answer could be synthesized`,
  refusal-style non-answers, missing domain grounding, wrong persona routing,
  and missing roundtable participants.
- A realistic E2E run intentionally failed before the fix because SPARTA memory
  items exposed `None` fields in relevance scoring; fixed in
  `src/ask/ask_relevance.py`.
- Evidence dashboard:
  `.ask_artifacts/validation-dashboard/20260427T171501Z/index.html`.

Additional implementation checks, as of 2026-04-27:

- `/ask argue` targeted tests passed:
  `uv run --project . --group dev python -m pytest -q tests/test_review_protocols.py tests/test_human_chat_examples.py tests/test_ask_cli_protocols.py`
  reported `28 passed`.
- `/ask` `sanity.sh` passed after argue integration, including human chat
  routing coverage.
- Portable parity plan validation passed via `/plan`, DAG rendering succeeded,
  and `/review-plan` reported no FAIL-grade issues.
- `$orchestrate` compatibility updates passed syntax checks,
  `$code-runner` module tests, `$orchestrate` preflight tests, backend alias
  validation, and dirty-worktree fail-closed verification.

## Current Handoff State

- `/ask argue` is implemented in the active worktree and validated, but not
  committed.
- The portable parity task file exists and is ready to run only after choosing a
  clean or isolated worktree for `$orchestrate`/`$code-runner`.
- `$orchestrate` and `$code-runner` were patched to normalize Codex-era aliases,
  normalize `/scillm` chat URLs, include `X-Caller-Skill`, and fail closed on
  dirty tracked worktrees rather than using `git stash`.
- Do not rerun broad `/ask` parity orchestration from a dirty worktree; use a
  fresh worktree or commit/stage only the intended changes first.

## Timeout and Recovery Policy

- `--oracle-timeout` is the wall-clock cap.
- `--oracle-idle-timeout` is silence/stall detection, not a normal long-reasoning
  timeout.
- `/subagent-runner` emits transcript delta and heartbeat events.
- `/ask` follows `events.jsonl` as the primary liveness source and writes sparse
  heartbeat snapshots to `/memory` collection `ask_subagent_heartbeat`.
- Full transcripts/chatter are not persisted by default; summaries, artifact
  paths, status, timings, and durable lessons are preferred.

## Maintenance Rules

- Update this file after durable decisions about `/ask` architecture,
  trust boundaries, runtime behavior, artifacts, telemetry, or verification.
- Do not use this file as the only source of truth; sync durable lessons into
  `/memory`.
- Keep entries curated and current-state oriented. Do not paste full logs,
  transcripts, prompts, diffs, or large code snippets.
