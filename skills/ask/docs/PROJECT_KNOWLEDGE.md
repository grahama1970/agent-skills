# Project Knowledge: ask

**Last updated:** 2026-05-06 12:56 by agent
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
- Runtime observability now uses per-run request/status/events artifacts for
  `ask`, `learn`, `nightly`, `os learn`, `os ask`, and `os health`.
- Deep-review `review.md` and `review.json` paths are registered back into
  `<ask_id>.status.json` when an `--ask-id` is used.
- Runs can pause with `state: needs_attention` instead of guessing, starting
  with missing deep-review targets.
- Runtime artifacts can be listed and pruned with `status --runs` and
  `status --prune`.
- ask README.md now mirrors the structural onboarding shape of pi-subagents: installation, try-first prompts, what happens, modes, workflows, command reference, configuration, artifacts, development knowledge, validation, troubleshooting, and non-goals.
- `/ask argue` is an explicit three-call `/scillm` DAG: FOR advocate and
  AGAINST advocate run in parallel, then a sequential judge produces a verdict
  that the deterministic verifier gates.
- `/ask` now attaches opaque `scillm_metadata` and source bundle IDs to
  argue and parallel-review DAG nodes so artifacts can correlate model calls
  without trusting model-invented IDs.
- `/ask` now writes source bundle artifacts for argue and parallel-review and
  records source-grounding fallback/degradation in node artifacts when `/scillm`
  cannot complete the source-backed path.
- Mocked/unit tests are regression checks only. User-visible `/scillm`
  composition paths require opt-in live E2E before they are described as
  validated.
- Source-grounding degradation now affects verifier trust: unqualified
  `FOR`/`AGAINST` argue verdicts and `SAFE`/`SAFE_WITH_CONDITIONS`
  parallel-review verdicts fail when critical `/scillm` nodes fall back from
  source grounding.
- Returned `scillm_metadata` mismatches on core identity fields
  (`ask_id`, `protocol`, `node_id`, `batch_id`, `item_id`) now fail verifier
  checks; missing echoes are recorded as observability degradation rather than
  silently treated as full node correlation.
- `/ask` now uses `ask.citations.v1` across answer surfaces. Memory citations
  are admissible for knowledge, persona, OS, and project-context answers, but
  code/review safety claims require target/file/diff/artifact citations.
- Parallel-review, deep-review, and argue verifier gates reject missing
  structured citations on verdict-bearing outputs. Parallel-review also rejects
  memory-only citations for `SAFE` and `SAFE_WITH_CONDITIONS`.
- Large target source bundles are chunked into addressable IDs such as
  `TARGET_BUNDLE.1`, avoiding prefix-only `/scillm` grounding.
- SPARTA evidence-case routing now fails closed: when preflight requires
  `/create-evidence-case` and that skill is unavailable or fails, `/ask` returns
  `needs_attention` with `safe_default=do_not_answer_as_grounded` instead of
  falling through to normal memory/oracle synthesis.
- Runtime transparency now includes a token-gated, localhost-only HTML viewer:
  `./run.sh status --run <ask_id> --serve --open` writes `index.html`,
  `ask-viewer.css`, `ask-viewer.js`, and `viewer.json` into the run directory
  and polls `request/status/events` so long runs are not black boxes.
- Release `config doctor --profile release` now performs read-only live probes
  for ArangoDB, Qdrant/vector-store/embedder, memory, and scillm. It still never
  starts containers, but it can now claim `release_ready` when those probes pass.
- The argue verifier rejects high-confidence judge verdicts when
  `missing_evidence` is non-empty.
- /ask now supports leading provider-family shorthand for direct scillm oracle calls: `$ask oc kimi ...`, `$ask oc-qwen ...`, `$ask chutes kimi ...`, and `$ask chutes-kimi ...`. OpenCode Go shorthand queries scillm live model discovery before selecting the preferred configured family model; Chutes shorthand uses configured scillm aliases such as `text-kimi`.
- 2026-05-03 live E2E reconfirmed `$ask oc kimi` and `$ask chutes-kimi` through real `/scillm`; both returned oracle answers and `answered` runtime state. Direct `/scillm` Kimi also passed for `opencode-go/kimi-k2.6` and `text-kimi`. Direct scillm oracle calls now use OpenAI-compatible SSE streaming, pass an explicit request `timeout`, and emit `oracle_scillm_call_started`, `oracle_scillm_stream_progress`, `oracle_scillm_call_finished`, and `oracle_scillm_call_failed` runtime events with model, served model, reasoning effort, backend, timeout, and accumulated content length so long Kimi/GPT calls are not opaque after `synthesis_started`. OpenCode Go shorthand discovery timeout increased to 30s so `$ask oc kimi` can use live `/v1/scillm/opencode-go/models` instead of falling back prematurely.
- 2026-05-03 Kimi deep-review E2E proved the previous stale/running bug is fixed at the observability layer: `$ask` emitted SSE progress events until the declared hard budget, then wrote terminal `failed` status and JSON error output without a Rich traceback. OpenCode Kimi remains too slow for the tested 35s/240s deep-review budget, so use a larger `--oracle-timeout` or GPT-5.5 High for production review until Kimi latency improves.
- `/ask --cae-gap-review` is a post-evidence-case QRA review layer. `/create-evidence-case` builds or loads the QRA, controls, answer, crosswalk chains, formal proof/SACM refs when present, and cached `evidence_case`; `/ask` freezes that snapshot and reviews whether the QRA has enough cited support for human review.
- 2026-05-06: /ask now has standalone image generation mode. Use ./run.sh ask <prompt> --image-generate to call /scillm POST /v1/images/generations, write generated image files plus image_generation.json into the ask run artifacts, and mark the run answered without mixing memory retrieval, oracle, roundtable, argue, parallel-review, deep-review, or CAE gap-review modes.
- 2026-05-06 correction: /ask --image-generate relies on scillm image credentials; the normal project-agent path is existing Codex/OpenAI OAuth through scillm. OPENAI_API_KEY is optional platform-key override only, not required for project agents when OAuth is configured.

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
| 2026-04-28 | Add runtime artifacts across the primary `/ask` command family. | Long learning, OS, oracle, and review runs need inspectable state without tailing logs. |
| 2026-04-28 | Add `needs_attention` as a pause state. | When the request is under-specified, `/ask` should fail closed with a fix hint instead of guessing scope. |
| 2026-04-28 | Add runtime artifact retention controls. | `.ask_artifacts/runs` needs operator-visible pruning rather than unbounded growth. |
| 2026-04-28 | Treat `/ask argue` as a real `/scillm` DAG. | Two parallel advocates plus a sequential judge prevents single-prompt fake debate and aligns with `/ask` DAG-lite architecture. |
| 2026-04-28 | Add `/scillm` metadata and source bundles to DAG nodes. | `/ask` needs portable node correlation, source grounding, and artifact observability without depending on Pi-native child sessions. |
| 2026-04-28 | Require live `/scillm` E2E for new composition paths before claiming validation. | Mocked sanity checks prove code shape, not that `/ask` actually composes with the runtime service. |
| 2026-04-28 | Make grounding degradation verifier-visible. | Recording fallback is insufficient if safe/binary verdicts can still pass as fully grounded. |
| 2026-04-28 | Verify returned `/scillm` metadata identity when present. | Opaque node correlation only works if returned runtime metadata matches the requested DAG node identity. |
| 2026-04-29 | Enforce structured citations across `/ask`. | Memory can cite knowledge answers, but review safety claims need target/file/diff/artifact evidence. |
| 2026-04-29 | Make SPARTA evidence-case routing fail closed. | Grounded SPARTA questions must not silently become ordinary answers when `/create-evidence-case` is unavailable or fails. |
| 2026-04-29 | Add an ephemeral HTML run viewer. | `status --watch` is necessary but not sufficient for human inspection of DAG state, artifacts, verifier failures, and `needs_attention` reasons. |
| 2026-05-01 | Make release config doctor verify readiness with read-only probes. | Release readiness should be evidence-based in one command, without starting containers or relying on a separate live doctor transcript. |
| 2026-05-01 | Treat provider-family shorthand as a first-class $ask oracle route | The model shorthand is user-facing routing policy, uses live OpenCode Go discovery where available, and must preserve resolved alias metadata in output and runtime artifacts. |
| 2026-05-02 | Treat CAE gap review as QRA review, not QRA generation | This preserves /create-evidence-case as the evidence trail builder while /ask runs bounded Brandon/Margaret/Jennifer reviewer roles plus a judge that reroutes only unresolved missing evidence before halting. |
| 2026-05-03 | Add direct scillm oracle call runtime events and lengthen OpenCode Go discovery timeout | `$ask oc kimi` could answer successfully but looked stalled after `synthesis_started`; events now expose the active scillm model call and served model. |

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
      roundtable behavior, and real `/scillm` calls for `/scillm` DAG paths;
      deterministic tests remain route/unit coverage.

## Key Files

| File | Purpose |
| --- | --- |
| `README.md` | GitHub/developer overview for `/ask` |
| `SKILL.md` | Full skill contract and operational instructions |
| `src/ask/ask.py` | Main command implementation |
| `src/ask/ask_relevance.py` | Domain relevance checks and `/create-evidence-case` invocation |
| `src/ask/ask_routing.py` | Natural-language route inference |
| `src/ask/ask_oracle.py` | Oracle and subagent-backed synthesis |
| `src/ask/deep_review.py` | Deep-review prompt, artifact, and verifier support |
| `src/ask/argue.py` | Three-call `/scillm` argue DAG, judge verifier, and argue artifacts |
| `src/ask/parallel_review.py` | `/scillm` reviewer fanout, judge synthesis, verifier, and code-runner handoff artifacts |
| `src/ask/scillm_runtime.py` | Shared `/scillm` metadata, source bundle, observability, and debug helpers |
| `src/ask/run_state.py` | Runtime request/status/events protocol, needs-attention states, run listing, pruning |
| `src/ask/run_viewer.py` | Token-gated local HTML monitor for request/status/events artifacts |
| `src/ask/doctor.py` | Fast and live runtime diagnostics |
| `src/ask/review_protocols/adversarial_review.py` | Existing roundtable/parallel review protocol support |
| `docs/HUMAN_CHAT_EXAMPLES.md` | Human prompt examples and route expectations |
| `docs/ASK_ARGUE_CONTRACT.md` | Argue DAG, judge admissibility, verifier, and observability contract |
| `docs/ASK_PARALLEL_REVIEW_CONTRACT.md` | Parallel-review DAG, target bundle, verifier, and code-runner handoff contract |
| `docs/ASK_DEEP_REVIEW_CONTRACT.md` | Deep-review runtime and verifier contract |
| `docs/plans/01_ASK_DEEP_REVIEW_TASKS.yaml` | Current implementation plan for deep review |
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

Latest implementation checks, as of 2026-05-01:

- Deep-review contract doc exists.
- Deep-review verifier tests exist.
- Deep-review context and artifact tests exist.
- Runtime protocol tests cover request/status/events, recent run listing,
  pruning, needs-attention, deep-review artifact registration, and command
  smoke paths.
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
- `/ask argue` and `/ask parallel-review` now have deterministic regression
  coverage for `/scillm` metadata/source payload construction.
- Deterministic protocol suite after the `/scillm` metadata/source update:
  `98 passed`; after grounding/metadata verifier hardening: `102 passed`.
- Deterministic protocol suite after full citation enforcement and branch
  promotion: `134 passed`.
- Skill sanity after the update: `All sanity checks PASSED`; the live checks
  remain opt-in and skipped by default.
- Real `/scillm` E2E after the update:
  `ASK_LIVE_SCILLM_E2E=1 ... test_live_argue_scillm_metadata_and_source_bundle`
  passed in `113.23s`.
- Real `/scillm` E2E full live file after the update:
  `ASK_LIVE_SCILLM_E2E=1 ... tests/test_parallel_review_live_e2e.py`
  passed `2/2` in `31.67s` after verifier hardening.
- Fail-closed SPARTA evidence-case and viewer regression checks passed.
- Targeted suite after the fail-closed/viewer update:
  `tests/test_human_chat_examples.py tests/test_run_state_protocol.py` passed
  `105 passed`.
- Skill sanity after the fail-closed/viewer update:
  `All sanity checks PASSED`.
- UI verification for the HTML run viewer completed with CDP and wrote
  `.codex/ui-verification/ask-run-viewer/latest.json`.
- Release readiness fix validation:
  - `./run.sh config doctor --profile release --json` passed with
    `release_ready=true`, `services_reachable=true`, and
    `databases_bootstrapped=true`.
  - `./run.sh doctor --live --profile release --json` passed with
    `error_count=0` and `warning_count=0`.
  - `./sanity.sh` passed.
  - `ASK_LIVE_SCILLM_E2E=1 ./sanity.sh` passed, including live
    `tests/test_parallel_review_live_e2e.py` at `2 passed in 97.49s`.
- Provider/model shorthand live E2E completed on 2026-05-01: non-dry-run `$ask oc kimi`, `$ask oc-qwen`, `$ask chutes kimi`, and `$ask chutes-kimi` all exited 0, returned oracle answers through scillm, preserved `oracle.model_alias`, and wrote runtime status `answered`. The E2E pass also fixed two regressions: oracle answers with zero memory items now exit successfully, and runtime summaries now include oracle alias/model metadata. Focused regression suite after the fix: `32 passed`.

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
