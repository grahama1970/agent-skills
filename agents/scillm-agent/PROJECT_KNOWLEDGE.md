# Project Knowledge: scillm-agent

**Last updated:** 2026-06-20 14:43 by Codex
**Status:** Chutes reliability implementation in progress

## Current Understanding

- `scillm-agent` is intended to be the protected control surface for the
  Scillm project. Its job is to make Scillm behave like a reliable library for
  LLM and agent calls, not to add more orchestration layers.
- The first reliability lane is Chutes text and batch calls. No other call
  type should be expanded until Chutes is boring, direct, and repeatably
  proven.
- The target Chutes behavior includes direct-provider equivalence, stable
  single-call text completions, stable async batch completions, per-item
  receipts, bounded concurrency, Tenacity-style backoff for transient 429/5xx,
  and clear cold-model handling.
- Batch implementation should use `asyncio.create_task`, collect with
  `asyncio.as_completed`, and bound concurrency with `asyncio.Semaphore`.
  It should also respect the Chutes provider's 5-connection practical limit and
  avoid silent dropped items.
- Chutes operational debugging must use `ops-chutes` for model health,
  provider status, quota, budget, model-family recommendations, and
  concurrency-slot facts. `brave-search` is only for external/provider research
  when local ops data and docs are insufficient.
- `scillm-agent` should use `memory` first before scanning or patching, and
  should query memory again when a new repair error appears. Memory recall is
  advisory unless backed by current local proof.
- `debugger` is required when the failure depends on runtime state, including
  route choice, async scheduling, retry state, request parsing, response
  parsing, middleware interference, or container/runtime behavior.
- Repair work should happen through a scoped `$loop` node in a disposable
  worktree. The loop can self-correct and patch code, but it must not
  self-certify global project completion or close GitHub tickets without
  deterministic proof.
- The subagent must file or use a GitHub ticket for each lane, lease that
  ticket before patching, comment progress with artifacts, and close only after
  proof is attached and reconciled.
- `scillm-agent` may rebuild and relaunch the Scillm container only as an
  explicit deploy mode with a narrow Docker command allowlist, health checks,
  endpoint sanity checks, and rollback/blocker behavior if checks fail.
- `subagent_memory` now exists as a memory-owned durable collection for
  proof-backed subagent repair lessons, loop outcomes, provider failure
  patterns, GitHub issue outcomes, and deploy sanity outcomes. It is wired into
  `/recall`, `unified_search`, Qdrant semantic sync, and `subagent_memory_edges`
  graph traversal. Subagents should still emit proof-backed memory candidates
  through `/upsert`; they must not write raw Arango/Qdrant directly.
- External `$brave-search` sanity check on 2026-06-18 found a directly
  relevant "multi-agent overkill" warning: simple scenarios should avoid
  unnecessary multi-agent cascades, and risk rises when ordinary requests pass
  through 4+ handoffs or added roles increase latency/cost more than quality.
  This supports keeping `scillm-agent` as one control surface with internal
  modes, rather than splitting early into `scillm-debugger`, `scillm-coder`,
  `scillm-caller`, and similar roles.
- Follow-up `$brave-search` after sourcing `~/.zshrc` found useful external
  patterns but the Brave API still reported `plan=Free` and rate-limited some
  queries, so paid-key use is not proven. Relevant findings: self-healing loops
  need bounded retries, backoff, idempotency/side-effect awareness, and failure
  classification; coding agents should halt or report still-failing status
  after N attempts; structured harnesses should provide incremental steps,
  persisted progress, and verification checkpoints; multi-agent/handoff systems
  are useful as workflows grow more complex but add latency and stickiness
  risks.
- `prompt-reviewer` exists under `agent-skills/agents` and can be used as an
  optional read/propose reviewer for prompt contracts, structured error wording,
  and proof-bundle wording. It should not become a required handoff for every
  Chutes repair because that would reintroduce orchestration complexity.
- Dynamic Chutes concurrency is crucial. `scillm-agent` should treat caller
  concurrency as a requested ceiling, not a fixed provider pressure level. It
  must adjust effective concurrency from `ops-chutes` facts, observed 429 or
  90-second penalty behavior, latency, model health, and proof receipts.
- If a successful Chutes transport returns content that fails Pydantic/schema
  checks, `scillm-agent` should classify the failure as a prompt/schema
  contract issue before treating it as provider failure. The prompt-reviewer
  handoff packet must include the full rendered prompt payload, source fixture,
  expected result, actual result, exact validation errors, and consumer schema.
- The prompt-reviewer handoff requires a sanity fixture: send Chutes a badly
  written vague prompt, prove transport succeeded, prove Pydantic/schema
  validation failed, prove the prompt violates `best-practices-prompt`, and
  write the complete handoff packet for `prompt-reviewer`.
- Structured Chutes batches need a real full-prompt payload probe before
  prompt-reviewer and before target batch spend. Prompt-reviewer-only preflight
  is self-serving: it can approve a prompt contract even when the exact target
  payload is too large, malformed, missing metadata, incompatible with
  `response_format`, or silently stuck before any SSE progress event. The
  standard gate is now: `$ops-chutes` budget/model checks -> real one-item
  `full_prompt_payload` Chutes probe with expected JSON key validation ->
  prompt-reviewer preflight -> target batch.

## Recent Decisions

| Date | Decision | Why |
|------|----------|-----|
| 2026-06-18 | Create `scillm-agent` as the top-level subagent identity. | The project needs a durable owner for Scillm's library surface, not only an incident debugger. |
| 2026-06-18 | Treat Scillm like a library first. | The current project has too many call surfaces and hidden policy layers; direct curl has been more reliable than Scillm for some work. |
| 2026-06-18 | Start with reliable Chutes calls before any other call type. | Chutes is the immediate provider lane where Scillm must prove single-call, batch, 429/backoff, and cold-model behavior. |
| 2026-06-18 | Require GitHub tickets for repair lanes. | Tickets provide type, target, route, agent, proof requirements, progress comments, leases, and proof-gated closure. |
| 2026-06-18 | Use `$loop` for self-repair only within one scoped lane. | Loop provides bounded explorer/coder/checks/reviewer repair and writes `final-receipt.json`; it is not a global project DAG. |
| 2026-06-18 | Allow rebuild/relaunch only through explicit deploy mode. | Docker/system mutation is necessary for live Scillm proof but must be narrow, auditable, and health-gated. |
| 2026-06-18 | Implement `subagent_memory` as a memory-owned recall lane. | Repeated subagent repairs need durable, searchable lessons with ArangoSearch, Qdrant semantic recall, and graph traversal. |
| 2026-06-18 | Keep one `scillm-agent` before adding specialist Scillm subagents. | Splitting into many Scillm-specific workers risks recreating the orchestration complexity the reset is trying to remove. |
| 2026-06-18 | Use internal modes before persistent specialist agents. | External research supports bounded self-healing and guardrailed handoffs, but also reinforces that premature multi-agent decomposition increases complexity. |
| 2026-06-18 | Phase A live Chutes checks identify batch `item_id` loss as the first repair target. | Direct provider and Scillm single-call checks passed with `Qwen/Qwen3-32B-TEE`; error-shape checks passed; batch returned all indexes but dropped caller-provided `item_id`. |
| 2026-06-18 | Add cold/down model recovery as an explicit Chutes sanity path. | `scillm-agent` must use `ops-chutes model-health` and `ops-chutes recommend` to prove whether Scillm recovers to a usable sibling or returns an actionable structured error when the requested model is cold/down. |
| 2026-06-18 | Add live 6-concurrent-call rate-limit recovery as a separate stress path. | Chutes can apply a 90-second server-side penalty after 429; Scillm must prove it waits/retries sanely instead of fast-looping or dropping batch items. |
| 2026-06-18 | Phase B initially treated removed `deepseek-ai/DeepSeek-V3` as cold/down, then live inventory corrected that assumption. | Raw Chutes now returns 404 for `deepseek-ai/DeepSeek-V3`; Scillm must alias stale V3 requests to `deepseek-ai/DeepSeek-V3.2-TEE` and surface config drift for removed provider IDs. Six concurrent Qwen calls all succeeded first-attempt, so no 90-second rate-limit recovery was observed. |
| 2026-06-18 | Note `prompt-reviewer` as an optional reviewer agent. | It can review prompt/error/proof wording, but `scillm-agent` remains the single control surface for Chutes repair execution. |
| 2026-06-18 | Require dynamic Chutes concurrency. | The subagent must lower pressure after 429/penalty/latency signals and only raise concurrency within `ops-chutes` and receipt-backed limits. |
| 2026-06-18 | Phase C repaired Chutes batch `item_id` preservation. | Focused local tests passed; `scillm-proxy` restart loaded the patched module; live batch proof passed with `item_ids_preserved: true`. |
| 2026-06-18 | Define Pydantic failure handoff to `prompt-reviewer`. | Full prompt payload, expected result, actual result, validation errors, and schema context must be sent so prompt repair is grounded and testable. |
| 2026-06-18 | Add vague-prompt prompt-reviewer handoff as a Chutes sanity. | The sanity proves bad content from a vague prompt is routed to prompt review instead of transport debugging. |
| 2026-06-18 | Phase D prompt-reviewer handoff sanity passed. | A vague prompt produced successful Chutes transport, Pydantic validation failure, best-practices-prompt violations, and a complete prompt-reviewer handoff packet. |
| 2026-06-18 | OAuth GPT one-shot assessment became the next Scillm reliability lane. | `gpt-5.5` is the proven ChatGPT/Codex OAuth one-shot model; `gpt-5.3-codex` is rejected by the provider for this account and must not be advertised to project agents. |
| 2026-06-20 | Require full-prompt payload probe before structured Chutes batch launch. | A prompt-reviewer-only preflight produced no useful progress evidence for a persona-memory batch; real target-payload viability must be proven before target spend. |

## Open Questions

- [x] What is the canonical GitHub repository slug for filing Scillm issues?
  `grahama1970/scillm`; Chutes reliability tracking issue is
  https://github.com/grahama1970/scillm/issues/14.
- [x] Which Chutes model should be the first real-world sanity target?
  Use an exact live `Org/Model` selected with `$ops-chutes`. Chutes chat aliases
  such as `chutes-deepseek`, `chutes-qwen`, `chutes-kimi`, `vlm-chutes`, and
  `gpt-chutes` are disabled because they hide provider inventory drift.
- [ ] Should the first lane split single-call and batch into two tickets, or
  keep them under one `reliable_chutes_text_and_batch` ticket?
- [ ] What exact disposable worktree root should `scillm-agent` use for repair
  runs?
- [x] Which memory repo files own adding a new collection to `/recall`,
  ArangoSearch View membership, semantic sync, and graph promotion?
  Implemented in the memory repo across `_schema_collections.py`,
  `_schema_views.py`, `lessons/recall_sources`, `service/app/_core.py`,
  `semantic_sync.py`, and `lessons/recall.py`.
- [x] Should `subagent_memory` be a generic collection for all agents or scoped
  by project with fields such as `project`, `agent_id`, and `lane`?
  It is generic, with explicit `project`, `scope`, `subagent_id`, `lane`,
  `github_issue`, status, proof, command, artifact, and tag fields.
- [ ] What failures should the Chutes sanity suite monkeypatch locally versus
  provoke against real provider behavior?
- [ ] When, if ever, should `scillm-agent` split out a specialist helper such
  as `scillm-debugger`? The default answer is "not until one lane proves the
  single-agent control surface is overloaded by evidence, not preference."
- [ ] Where is the paid Brave API key stored? `~/.zshrc` exposes
  `BRAVE_API_KEY`, but Brave returned `plan=Free` during follow-up research.

## Key Files

| File | Purpose |
|------|---------|
| `agents/scillm-agent/PROJECT_KNOWLEDGE.md` | Human-readable running context for the subagent plan. |
| `agents/scillm-agent/CHUTES_RELIABILITY_PLAN.md` | Comprehensive plan for reliable Chutes calls and the self-repairing subagent workflow. |
| `/home/graham/workspace/experiments/scillm/PROJECT_KNOWLEDGE.md` | Main Scillm project knowledge; source of broader architecture history. |
| `/home/graham/workspace/experiments/scillm/src/scillm/proxy/chutes_direct.py` | Existing direct Chutes passthrough implementation target. |
| `/home/graham/workspace/experiments/scillm/deploy/docker/compose.scillm.core.yml` | Explicit Scillm compose stack for deploy-mode rebuild/relaunch. |
| `/home/graham/workspace/experiments/agent-skills/skills/loop/SKILL.md` | Contract for bounded self-repair loops and `final-receipt.json`. |
| `/home/graham/workspace/experiments/agent-skills/skills/best-practices-subagent/SKILL.md` | Contract for subagent ownership, tool policy, memory policy, retries, and artifacts. |
| `/home/graham/workspace/experiments/agent-skills/skills/best-practices-github-ticket/SKILL.md` | Contract for ticket filing, leases, proof comments, and proof-gated closure. |
| `/home/graham/workspace/experiments/agent-skills/skills/best-practices-python/SKILL.md` | Python implementation rules: `httpx`, async discipline, tests, visible errors. |
| `/home/graham/workspace/experiments/agent-skills/skills/best-practices-arangodb/SKILL.md` | Required rules for future `subagent_memory` collection integration. |
| `/home/graham/workspace/experiments/agent-skills/skills/ops-chutes/SKILL.md` | Chutes model, quota, health, recommendation, and concurrency operations. |

## Infrastructure State

- `scillm-agent` currently exists as a protected subagent contract and planning
  directory, not as a fully exercised runtime.
- GitHub issue https://github.com/grahama1970/scillm/issues/14 has been filed
  and leased to `scillm-agent` with lease id
  `20260618T114430Z-scillm-agent-14`.
- No `$loop` node has run yet.
- Initial Chutes sanity scripts exist. Local monkeypatched retry/backoff proof
  passed on 2026-06-18 and wrote
  `/home/graham/workspace/experiments/scillm/.scillm/proofs/chutes/20260618T114353Z/retry_backoff/receipt.json`.
- Phase A live provider text proof passed with `Qwen/Qwen3-32B-TEE` and wrote
  `/home/graham/workspace/experiments/scillm/.scillm/proofs/chutes/20260618T114847Z/text_call/receipt.json`.
- Phase A error-shape proof passed and wrote
  `/home/graham/workspace/experiments/scillm/.scillm/proofs/chutes/20260618T114929Z/error_shapes/receipt.json`.
- Phase A live batch proof returned `NEEDS_CHANGES` and wrote
  `/home/graham/workspace/experiments/scillm/.scillm/proofs/chutes/20260618T114929Z/batch_call/receipt.json`.
  The concrete failing field is `item_ids_preserved: false`.
- Phase A progress was commented on GitHub issue #14:
  https://github.com/grahama1970/scillm/issues/14#issuecomment-4741645229.
- Partial-failure, focused pytest, loop receipt, repaired live batch, and
  container sanity proofs are still pending.
- Cold/down model recovery proof is now part of the planned sanity suite via
  `scripts/prove_chutes_cold_model_recovery.sh`. Live proof passed on
  2026-06-18 and wrote
  `/home/graham/workspace/experiments/scillm/.scillm/proofs/chutes/20260618T115749Z/cold_model_recovery/receipt.json`.
- Live 6-concurrent-call rate-limit recovery proof is now part of the planned
  sanity suite via `scripts/prove_chutes_live_rate_limit_recovery.sh`. Live
  proof on 2026-06-18 wrote
  `/home/graham/workspace/experiments/scillm/.scillm/proofs/chutes/20260618T115809Z/live_rate_limit_recovery/receipt.json`
  with `NEEDS_CHANGES` because all six concurrent calls succeeded first-attempt
  and no 429 or 90-second penalty was observed.
- Phase B progress was commented on GitHub issue #14:
  https://github.com/grahama1970/scillm/issues/14#issuecomment-4741710228.
- Phase C repaired Chutes batch `item_id` preservation. Local tests passed and
  live post-restart batch proof wrote
  `/home/graham/workspace/experiments/scillm/.scillm/proofs/chutes/20260618T120801Z/batch_call/receipt.json`
  with `status: PASS` and `item_ids_preserved: true`.
- Phase C progress was commented on GitHub issue #14:
  https://github.com/grahama1970/scillm/issues/14#issuecomment-4741785330.
- Phase D prompt-reviewer handoff sanity passed and wrote
  `/home/graham/workspace/experiments/scillm/.scillm/proofs/chutes/20260618T122527Z/prompt_reviewer_handoff/receipt.json`.
- Phase D progress was commented on GitHub issue #14:
  https://github.com/grahama1970/scillm/issues/14#issuecomment-4741913614.
- Phase E initially drifted into OpenCode transport for `prompt-reviewer`,
  which was the wrong proof lane for Chutes model support. That exposed useful
  transport evidence (`Token refresh failed: 401`) but did not prove Chutes.
- Phase E was corrected to run the prompt-reviewer generation through Scillm's
  existing Chutes batch endpoint. Live proof passed on 2026-06-18 using
  `Qwen/Qwen3-32B-TEE` for both the failed prompt and reviewer prompt, and
  wrote
  `/home/graham/workspace/experiments/scillm/.scillm/proofs/chutes/20260618T130751Z/prompt_reviewer_loop/receipt.json`
  with `reviewer_transport: scillm_chutes_batch`,
  `reviewer_artifact_ok: true`, `rerun_transport_ok: true`, and
  `rerun_pydantic_passed: true`.
- Phase E progress was commented on GitHub issue #15:
  https://github.com/grahama1970/scillm/issues/15#issuecomment-4742251090.
- Dynamic concurrency adjustment proof passed on 2026-06-18 and wrote
  `/home/graham/workspace/experiments/scillm/.scillm/proofs/chutes/20260618T132039Z/dynamic_concurrency/receipt.json`
  with `saw_rate_limit_drop: true` and `saw_success_recovery: true`.
  The Chutes batch result events now expose `concurrency_limit` and
  `concurrency_events`.
- After the adaptive concurrency patch, `scillm-scillm-proxy-1` was restarted,
  health returned `{"status":"ok"}`, and live batch sanity passed with
  `/home/graham/workspace/experiments/scillm/.scillm/proofs/chutes/20260618T132119Z/batch_call/receipt.json`.
- Phase F progress was commented on GitHub issue #14:
  https://github.com/grahama1970/scillm/issues/14#issuecomment-4742357392.
- Live 6-concurrent rate-limit recovery remains pending.
- Real provider 429 / 90-second penalty recovery is blocked by provider
  behavior after bounded stress attempts:
  `/home/graham/workspace/experiments/scillm/.scillm/proofs/chutes/20260618T132614Z/live_rate_limit_recovery/receipt.json`
  (8/8 Qwen, all first-attempt successes),
  `/home/graham/workspace/experiments/scillm/.scillm/proofs/chutes/20260618T132735Z/live_rate_limit_recovery/receipt.json`
  (40/40 Gemma, all first-attempt successes), and
  `/home/graham/workspace/experiments/scillm/.scillm/proofs/chutes/20260618T132803Z/live_rate_limit_recovery/receipt.json`
  (120/120 Gemma, all first-attempt successes). Blocked summary:
  `/home/graham/workspace/experiments/scillm/.scillm/proofs/chutes/20260618T132803Z/live_rate_limit_recovery/blocked-summary.md`.
- The live 429 blocker was commented on GitHub issue #14:
  https://github.com/grahama1970/scillm/issues/14#issuecomment-4742418385.
- Full image rebuild/relaunch proof was performed for `scillm-proxy`.
  Docker build produced image digest
  `sha256:0832f0a6325097ff028637204dad446607dcd86ce2e67e7ea677f205cf5db37f`.
  The rebuilt `scillm-scillm-proxy-1` container was recreated with `--no-deps`,
  health returned `{"status":"ok"}`, container import confirmed
  `_AdaptiveConcurrencyLimiter`, and post-rebuild live batch sanity passed with
  `/home/graham/workspace/experiments/scillm/.scillm/proofs/chutes/20260618T133021Z/batch_call/receipt.json`.
- Rebuild/relaunch proof was commented on GitHub issue #14:
  https://github.com/grahama1970/scillm/issues/14#issuecomment-4742438655.
- Batch prompt preflight decision recorded on 2026-06-18: when a Chutes batch
  has a shared prompt/template and a known expected-output contract,
  `scillm-agent` should send a representative full prompt payload, source
  fixture, expected result, consumer schema, validation command, rejection
  criteria, and batch context to `prompt-reviewer` before launching the full
  batch. If preflight cannot establish the prompt contract, do not spend the
  large batch; run a one-item probe or return `NEEDS_CHANGES`.
- Batch prompt preflight runtime proof passed on 2026-06-18 through the
  scillm-agent/probe path. Command:
  `bash scripts/prove_chutes_batch_prompt_preflight.sh --model 'Qwen/Qwen3-32B-TEE' --prompt-reviewer-model 'Qwen/Qwen3-32B-TEE' --wall-time-s 300`.
  Receipt:
  `/home/graham/workspace/experiments/scillm/.scillm/proofs/chutes/20260618T140427Z/batch_prompt_preflight/receipt.json`
  with `status: PASS`, `reviewer_transport: scillm_chutes_batch`,
  `preflight_ok: true`, `fixed_template_has_payload_placeholder: true`,
  `batch_started_after_preflight_artifact: true`, `batch_transport_ok: true`,
  `all_batch_items_valid: true`, and `validation_count: 3`.
- Batch prompt preflight proof artifacts:
  `/home/graham/workspace/experiments/scillm/.scillm/proofs/chutes/20260618T140427Z/batch_prompt_preflight/batch-preflight-packet.json`,
  `/home/graham/workspace/experiments/scillm/.scillm/proofs/chutes/20260618T140427Z/batch_prompt_preflight/prompt-reviewer-worker-receipt.json`,
  `/home/graham/workspace/experiments/scillm/.scillm/proofs/chutes/20260618T140427Z/batch_prompt_preflight/prompt_review.json`,
  `/home/graham/workspace/experiments/scillm/.scillm/proofs/chutes/20260618T140427Z/batch_prompt_preflight/fixed_prompt_template.md`,
  `/home/graham/workspace/experiments/scillm/.scillm/proofs/chutes/20260618T140427Z/batch_prompt_preflight/fixed_prompt_template.md`.
- DeepSeek Chutes inventory drift was identified as a crucial Scillm bug on
  2026-06-18. Earlier notes proposed resolving `chutes-deepseek` and stale V3
  aliases to live DeepSeek variants, but the current decision supersedes that:
  Scillm must not silently alias Chutes chat models. It must require exact live
  `Org/Model` IDs selected with `$ops-chutes` and surface structured
  unavailable-model errors when callers pass aliases or removed provider IDs.
  `/home/graham/workspace/experiments/scillm/.scillm/proofs/chutes/20260618T140427Z/batch_prompt_preflight/preflight-order.json`,
  `/home/graham/workspace/experiments/scillm/.scillm/proofs/chutes/20260618T140427Z/batch_prompt_preflight/batch-response.json`,
  and
  `/home/graham/workspace/experiments/scillm/.scillm/proofs/chutes/20260618T140427Z/batch_prompt_preflight/batch-validations.json`.
- This initial preflight proof applied to the scillm-agent/probe control flow;
  endpoint enforcement was added and proven afterward.
- Batch preflight proof was commented on GitHub issues #14 and #15:
  https://github.com/grahama1970/scillm/issues/14#issuecomment-4742781379
  and
  https://github.com/grahama1970/scillm/issues/15#issuecomment-4742781390.
- Public endpoint-level batch prompt preflight was added on 2026-06-18 for
  callers that set `require_prompt_preflight: true` and provide a
  `prompt_preflight` packet. The endpoint runs a one-item Chutes-backed
  prompt-reviewer preflight before launching target batch items; failed preflight
  returns HTTP 422 with structured reviewer details.
- Endpoint-level preflight proof passed on 2026-06-18. Command:
  `bash scripts/prove_chutes_endpoint_batch_prompt_preflight.sh --model 'Qwen/Qwen3-32B-TEE' --prompt-reviewer-model 'Qwen/Qwen3-32B-TEE' --wall-time-s 300`.
  Receipt:
  `/home/graham/workspace/experiments/scillm/.scillm/proofs/chutes/20260618T141910Z/endpoint_batch_prompt_preflight/receipt.json`
  with `status: PASS`, `http_status: 200`, `reviewer_transport:
  scillm_chutes_batch`, `preflight_event_first: true`,
  `all_batch_items_valid: true`, `target_event_count: 2`, and
  `validation_count: 2`.
- Endpoint preflight development exposed and corrected two prompt-contract
  failures: prompt-reviewer rejected an underspecified batch prompt with HTTP
  422, then target validation rejected loose citation shape until the prompt and
  fixture required exact key=value citation strings.
- Endpoint preflight proof was commented on GitHub issues #14 and #15:
  https://github.com/grahama1970/scillm/issues/14#issuecomment-4742905272
  and
  https://github.com/grahama1970/scillm/issues/15#issuecomment-4742905323.
- Container conflict found during relaunch: two compose projects were running
  host-network Scillm proxies (`scillm-scillm-proxy-1` and
  `docker-scillm-proxy-1`). `scillm-scillm-proxy-1` owned port 4001 and served
  stale code. It was stopped, then `docker-scillm-proxy-1` was recreated from
  the rebuilt image and health returned `{"status":"ok"}`.
- `subagent_memory` is implemented in memory and proven through live `/recall`:
  collection exists, `unified_search` has a `subagent_memory` link, Qdrant
  metadata is present with `semantic_sync_state: synced`, and graph traversal
  through `subagent_memory_edges` returns positive `scores.graph`.
  Proof command on 2026-06-18:
  `POST http://127.0.0.1:8601/recall` with
  `collections=["subagent_memory"]`, `scope="scillm"`, and tags
  `["subagent:scillm-agent", "lane:chutes"]` returned 2 items with
  `scores.dense` values `0.7952355` and `0.6206107`, `scores.graph`
  `0.49714382394737167`, and one visible `subagent_memory_edges` edge on each
  item.
- OAuth GPT one-shot lane assessment and refactor ran on 2026-06-18.
  Initial receipt:
  `/home/graham/workspace/experiments/scillm/.scillm/proofs/oauth_gpt/20260618T160334Z/assessment/receipt.json`
  showed `gpt-5.5` text/JSON success and provider rejection for
  `gpt-5.3-codex` with the message that it is not supported with a ChatGPT
  account. Refactor removed `gpt-5.3-codex` from one-shot Codex OAuth
  advertising and config, made `codex-vision` use `gpt-5.5`, and added early
  validation rejection for unsupported ChatGPT Codex OAuth models. Post-refactor
  proof:
  `/home/graham/workspace/experiments/scillm/.scillm/proofs/oauth_gpt/20260618T160934Z/post_refactor/receipt.json`
  with `status: PASS`, `text_ok: true`, `json_valid: true`,
  `models_contains_gpt_5_3_codex: false`, `codex_examples: ["gpt-5.5"]`,
  `configured_codex_vision: ["gpt-5.5"]`, and HTTP 400 actionable rejection
  for `gpt-5.3-codex`.
- OAuth GPT one-shot E2E sanity suite was added on 2026-06-18. Runtime:
  `scripts/prove_oauth_gpt_oneshot.sh --timeout-s 180`. Receipt:
  `/home/graham/workspace/experiments/scillm/.scillm/proofs/oauth_gpt/20260618T162350Z/oneshot_e2e/receipt.json`
  with `status: PASS` across omitted reasoning, valid `reasoning:
  {"effort":"low"}` with `scillm_reasoning.forwarded: true`, exact JSON
  response parsing, invalid `reasoning="mustard"` structured HTTP 400,
  nonexistent GPT-like model structured provider HTTP 400, unsupported
  `gpt-5.3-codex` structured local HTTP 400, missing `X-Caller-Skill`, and
  missing model. Local checks for this slice:
  `PYTHONPATH=src python3 -m pytest -q tests/test_codex_routing.py tests/test_oauth_error_handling.py`
  returned `14 passed`; `PYTHONPATH=src python3 -m py_compile
  src/scillm/proxy/app.py scripts/prove_oauth_gpt_oneshot.py` returned
  success; `curl http://127.0.0.1:4001/health` returned `{"status":"ok"}`.
  Residual limit: the suite does not forcibly break a valid OAuth account
  token; it validates provider error shape through a real unsupported
  GPT-like-model provider response.
- OAuth GPT auth/account failure was added to the one-shot sanity receipt on
  2026-06-18 without modifying the human's real `~/.codex/auth.json`. Runtime:
  `scripts/prove_oauth_gpt_oneshot.sh --timeout-s 180`. Receipt:
  `/home/graham/workspace/experiments/scillm/.scillm/proofs/oauth_gpt/20260618T174612Z/oneshot_e2e/receipt.json`
  with `status: PASS`, `case_count: 9`, and
  `controlled_missing_codex_auth` returning HTTP 401 with
  `error.type: provider_auth_error`, `provider: codex-oauth`,
  `provider_error_code: PROVIDER_AUTH_FAILED`,
  `provider_auth_status: not_configured_or_expired`,
  `model_requested: gpt-5.5`, and a project-agent message instructing agents
  to run `codex login` and check `GET /v1/scillm/auth`.
- Chutes golden curl-shape proof was added on 2026-06-18 after the human
  identified that direct Chutes curl was reliable while Scillm was adding
  brittle behavior. Static Chutes alias-to-model mapping was removed from the
  direct Chutes path; the later exact-model-only update also disables intent
  alias resolution. Scillm startup Chutes auto-select and warmup probes are
  disabled by default; `$ops-chutes` owns model health/recommendation and batch
  feasibility checks. Runtime:
  `bash scripts/prove_chutes_golden_curl.sh --model 'Qwen/Qwen3.6-27B-TEE' --batch-size 2 --concurrency 2 --wall-time-s 180 --prompt 'Tell me a 100 word story.'`.
  Receipt:
  `/home/graham/workspace/experiments/scillm/.scillm/proofs/chutes/20260618T190539Z/golden_curl/receipt.json`
  with `status: PASS`, direct stream HTTP 200, Scillm stream HTTP 200,
  Scillm batch HTTP 200, one `[DONE]` for direct and Scillm streams,
  `batch_event_count: 2`, and `all_batch_ok: true`. `$ops-chutes`
  `budget-check`, `can-complete 2`, `model-health Qwen/Qwen3.6-27B-TEE`,
  and `recommend Qwen/Qwen3.6-27B-TEE --json` passed; `$ops-chutes status`
  still returns a management API 401 and remains a separate ops issue.
- Chutes exact-model ops integration was repaired on 2026-06-18. The direct
  Chutes lane now requires exact `Org/Model` IDs, runs `$ops-chutes`
  budget/can-complete/model-health/recommend preflight for batches, records
  `ops_chutes` plan metadata in Scillm responses/events, and wraps provider
  attempts with the ops-chutes cross-process semaphore. A live proof caught a
  Scillm streaming transport bug: `httpx.post(... stream=true in payload)` was
  waiting on the provider stream body before returning response headers. The fix
  uses `client.send(..., stream=True)` and releases the semaphore slot when the
  FastAPI stream closes. Proof receipt:
  `/home/graham/workspace/experiments/scillm/.scillm/proofs/chutes/20260618T193503Z/exact_model_ops_gate/receipt.json`.
  Evidence: direct Chutes non-stream HTTP 200 in 22.99s; Scillm single HTTP 200
  in 30.92s with `ops_plan.health: HOT`; Scillm stream HTTP 200 in 31.96s with
  one `[DONE]`; Scillm batch HTTP 200 in 154.86s with two ok events,
  `ops_chutes.health: HOT`, and adaptive concurrency reducing from 2 to 1 for
  `slow_call`; alias `chutes-qwen` returned HTTP 503 `model_unavailable`;
  `$ops-chutes slots` reported `0/5 slots` after the run.
