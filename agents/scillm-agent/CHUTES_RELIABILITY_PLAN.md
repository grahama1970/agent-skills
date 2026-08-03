# scillm-agent Plan: Reliable Chutes Calls

**Status:** Pending implementation and proof
**Primary goal:** make Chutes calls through Scillm at least as reliable and
observable as direct Chutes curl before expanding any other Scillm call type.

## 1. Operating Principles

- Treat Scillm like a library first: small public surface, stable contracts,
  clear examples, explicit errors, and real integration proof.
- Build one call lane at a time. The first lane is reliable Chutes text and
  batch calls.
- Prefer direct, boring code over abstraction. Do not add middleware, DAG
  routing, cache, generic model router, or harness layers unless a failing E2E
  sanity check proves the simple lane cannot satisfy the contract.
- Keep one `scillm-agent` control surface for the Chutes lane. Do not split
  into `scillm-debugger`, `scillm-coder`, `scillm-caller`, or similar helper
  agents unless the single-agent path is proven overloaded by concrete receipts.
  Splitting roles too early risks reintroducing the complexity Scillm is trying
  to remove.
- Self-healing must be bounded and side-effect aware: classify failures as
  retriable or non-retriable, use backoff, preserve idempotency where possible,
  stop after N attempts, and report `NEEDS_CHANGES` or `BLOCKED` rather than
  looping indefinitely.
- Handoffs and specialist roles are allowed only when the lane grows beyond one
  agent's safe operating boundary. They must reduce ambiguity or risk, not
  merely distribute a simple call path across more participants.
- Compare Scillm behavior against direct provider behavior. If direct Chutes
  succeeds and Scillm fails, Scillm owns the defect.
- Every endpoint needs real-world sanity checks. Unit tests and mocked tests are
  useful but cannot promote an endpoint to usable.
- Closure is proof-gated. No ticket closes from prose, reviewer confidence, or
  absence of errors.

## 2. Subagent Role

`scillm-agent` owns the Scillm library control surface for one lane at a time.

It owns:

- reliable Chutes call lane definition
- memory-first recall before repair
- Chutes operational checks through `ops-chutes`
- GitHub ticket creation, lease, progress comments, and proof-gated closure
- scoped `$loop` repair in a disposable worktree
- targeted tests and real-world endpoint sanity scripts
- explicit deploy mode for Scillm container rebuild/relaunch
- proof artifact collection and final status recommendation

It does not own:

- global Scillm project completion
- final merge decision without project-agent adoption
- broad provider redesign
- unrelated refactors
- memory promotion without proof
- direct raw ArangoDB or Qdrant mutation
- hiding simple call failures behind new orchestration
- creating specialist Scillm subagents before the current lane proves that a
  separate role is necessary

## 3. Required Skills

- `memory`: recall before scanning or patching; recall again on new error
  patterns.
- `ops-chutes`: Chutes health, quota, model list, model health,
  recommendation, concurrency facts, budget checks.
- `debugger`: runtime-state proof for routing, async scheduling, retry state,
  request parsing, response parsing, middleware interference, or container
  behavior.
- `brave-search`: external provider/API research only when local docs,
  `ops-chutes`, and memory are insufficient.
- `loop`: bounded one-artifact repair transaction.
- `ops-docker`: safe explicit stack deploy/rebuild operations.
- `best-practices-subagent`: role, tool, memory, retry, and artifact contract.
- `best-practices-github-ticket`: issue lifecycle and proof-gated closure.
- `best-practices-python`: `httpx`, async discipline, visible errors, tests,
  module hygiene.
- `best-practices-arangodb`: required for future `subagent_memory`.

Specialist helper policy:

- Default: one `scillm-agent` owns the lane.
- Allowed helper: `$loop` internal explorer/coder/reviewer roles for one
  bounded artifact transaction.
- Optional reviewer: `prompt-reviewer` for prompt contracts, structured error
  wording, and proof-bundle wording. It is read/propose-only and must not add a
  required handoff to ordinary Chutes repairs.
- Batch prompt preflight: if a Chutes batch uses a shared prompt/template and
  the caller has a known expected-output contract, `scillm-agent` must send a
  representative prompt-review packet to `prompt-reviewer` before launching the
  full batch. The packet must include:
  - representative full rendered system/user prompt payload
  - source fixture or input payload
  - expected result object for that fixture
  - consumer schema/model name and validation command
  - rejection criteria for gibberish, generic prose, markdown wrappers,
    missing fields, wrong fields, hallucinated fields, and ungrounded output
  - batch context: item count, shared template, and variable fields
- If batch preflight returns a fixed prompt/template, `scillm-agent` must use
  that fixed template before the full batch. If preflight cannot establish the
  expected contract, the full batch must not run; run a one-item probe or
  return `NEEDS_CHANGES` with the prompt-review artifact.
- Pydantic/schema validation failure handoff: if Chutes transport succeeds but
  the response fails the caller's Pydantic or schema check, `scillm-agent`
  creates a prompt-review packet for `prompt-reviewer` containing:
  - full rendered system/user prompt payload
  - source fixture or input payload
  - expected result object
  - actual provider response
  - exact Pydantic/schema validation errors
  - consumer schema/model name and validation command
  - non-goal note that prompt-reviewer must not debug Chutes transport
- Sanity fixture: run a successful Chutes call with a deliberately vague prompt
  that violates `best-practices-prompt`, then require Pydantic/schema
  validation to fail and require a complete prompt-reviewer handoff packet.
- Batch preflight sanity fixture: build a representative batch prompt template
  with one concrete input fixture and expected output. Prove that
  `scillm-agent` can obtain a prompt-review proposal before launching a full
  batch and that the eventual batch uses the reviewed prompt/template.
- Not allowed by default: persistent Scillm-specific helper agents such as
  `scillm-debugger`, `scillm-coder`, or `scillm-caller`.
- Split only if receipts show the single-agent contract is too large to verify
  or operate safely, and the split reduces handoffs rather than adding them.
- If a split is proposed, require a ticketed design decision with evidence:
  what failure the split prevents, which handoffs it removes or clarifies, what
  new latency/state risks it adds, and how proof remains simpler than the
  single-agent mode.

## 4. First Lane Contract

Lane id: `reliable_chutes_text_and_batch`

Public Scillm endpoints:

- `POST /v1/scillm/chutes/completions`
- `POST /v1/scillm/chutes/batch`
- `GET /v1/scillm/chutes/models`

Required behaviors:

- Direct single Chutes call returns assistant text for a known-good prompt.
- Scillm single Chutes call returns assistant text for the same model/prompt.
- Chutes batch returns one result object per input item.
- Batch preserves caller-provided `item_id`.
- Batch uses `asyncio.create_task`.
- Batch collects via `asyncio.as_completed`, not default `gather`.
- Batch uses `asyncio.Semaphore` to bound local concurrency.
- Batch dynamically adjusts effective concurrency from `ops-chutes` facts,
  observed model family concurrency, 429/penalty signals, latency, and receipt
  history. Static concurrency is a caller/test request, not an unconditional
  provider pressure level.
- Batch with a known expected-output contract preflights the shared
  prompt/template through `prompt-reviewer` before launching the full batch.
  This preflight prevents spending many Chutes calls on a prompt that is likely
  to produce gibberish, generic prose, invalid JSON, or schema-incompatible
  output.
- Batch respects the Chutes 5-connection practical limit where it applies and
  avoids cross-process self-DoS where feasible.
- Transient 429/5xx/network failures retry with Tenacity-style exponential
  backoff and stop after a bounded budget.
- 429 handling respects Chutes' 90-second penalty behavior; no fast retry loop.
- Live rate-limit recovery is tested separately by running 6 concurrent Chutes
  calls and requiring receipt evidence that retry/recovery waits through the
  Chutes penalty window instead of spinning quickly.
- Dynamic concurrency must be receipt-backed: after a 429 or penalty signal,
  the lane lowers effective concurrency and records the adjustment; after
  stable success, it may cautiously raise concurrency only within provider and
  `ops-chutes` evidence.
- Cold/down model handling records model health and recommendation evidence.
- Cold/down model recovery is tested explicitly with `ops-chutes model-health`
  and `ops-chutes recommend`, then a Scillm call against the cold/down model
  must either recover to a usable sibling or return an actionable structured
  error.
- Partial failures are explicit per item; no silent dropped items.
- Wrong auth/model returns actionable structured error.
- Healthy direct provider responses must not be blocked by Scillm middleware.

Non-goals for first lane:

- generic provider abstraction
- image generation
- exec workers
- standing agents
- DAG viewer/editor
- memory harness
- cache redesign
- global fallback framework

## 5. GitHub Ticket Lifecycle

For the first lane, create a GitHub issue with:

- type: `bug` or `optimization`
- target: Chutes text and batch call reliability
- route: `backend_python_or_skill_runtime`
- agent: `scillm-agent`
- current state: Scillm has become less reliable than direct curl for some LLM
  calls and needs a provider-equivalent Chutes lane
- requested outcome: reliable Chutes single and batch calls with real-world
  sanity checks
- non-goals: no generic routing or agent/DAG expansion
- required proof:
  - `ops-chutes status`
  - `ops-chutes model-health <model>`
  - `ops-chutes recommend <model> --json`
  - `ops-chutes budget-check`
  - `ops-chutes can-complete <batch_size>`
  - cold/down model recovery receipt using `ops-chutes`
  - direct Chutes baseline response
  - Scillm Chutes single-call response
  - Scillm Chutes batch response
  - monkeypatched transient failure retry/backoff proof
  - live 6-concurrent-call rate-limit recovery receipt
  - dynamic concurrency adjustment proof after 429/latency/provider health
    signals
  - batch prompt-review preflight proof before any large batch with a known
    expected-output contract
  - vague-prompt plus Pydantic failure handoff proof for `prompt-reviewer`
  - monkeypatched per-item partial failure proof
  - wrong auth/model error-shape proof
  - focused pytest output
  - `$loop` final receipt
  - container rebuild/relaunch proof
  - post-container endpoint sanity proof

The ticket must be leased before patching. It must remain open until all closure
proof is attached or a blocker is explicitly recorded.

## 6. Worktree and Loop Plan

Run repair in a disposable worktree.

Node file:

```text
.loop/nodes/reliable_chutes_text_and_batch.json
```

Suggested node fields:

```json
{
  "node_type": "loop",
  "node_id": "reliable_chutes_text_and_batch",
  "objective": "Make Chutes single and batch calls through Scillm reliable, direct-provider comparable, and proof-backed.",
  "allowed_globs": [
    "src/scillm/proxy/chutes_direct.py",
    "src/scillm/proxy/app.py",
    "src/scillm/proxy/router.py",
    "tests/test_chutes*.py",
    "tests/test_*chutes*.py",
    "scripts/prove_chutes_*.sh"
  ],
  "required_changed_globs": [
    "scripts/prove_chutes_text_call.sh",
    "scripts/prove_chutes_batch_call.sh"
  ],
  "checks": [
    "python -m pytest -q tests/test_chutes_direct.py",
    "bash scripts/prove_chutes_text_call.sh",
    "bash scripts/prove_chutes_batch_call.sh",
    "bash scripts/prove_chutes_error_shapes.sh",
    "bash scripts/prove_chutes_retry_backoff.sh"
  ],
  "max_attempts": 3,
  "check_timeout": 600,
  "agent_config": "skills/loop/examples/agents.scillm.toml",
  "worktree": {"mode": "existing"}
}
```

Stop immediately if:

- direct Chutes baseline fails
- provider auth is missing
- quota/budget blocks the run
- model health is down and no allowed sibling fallback exists
- the same failure repeats twice
- patch requires files outside `allowed_globs`
- no final loop receipt is produced
- container relaunch fails health checks

## 7. Sanity Scripts

Create real-world scripts that write JSON receipts under:

```text
.scillm/proofs/chutes/<timestamp>/
```

Required scripts:

```text
scripts/prove_chutes_text_call.sh
scripts/prove_chutes_batch_call.sh
scripts/prove_chutes_error_shapes.sh
scripts/prove_chutes_retry_backoff.sh
```

Each script should record:

- command line
- timestamp
- model requested
- model served, if available
- request JSON with secrets redacted
- response JSON
- status: `PASS`, `NEEDS_CHANGES`, or `BLOCKED`
- reason
- artifacts

### `prove_chutes_text_call.sh`

Must prove:

- `ops-chutes` health/preflight captured
- direct Chutes provider call returns assistant text
- Scillm Chutes endpoint returns assistant text
- Scillm does not rewrite a healthy provider call into failure

### `prove_chutes_batch_call.sh`

Must prove:

- batch size at least 5
- every input item appears in output
- `item_id` is preserved
- no item is silently dropped
- partial failures, if present, are explicit
- concurrency is bounded

### `prove_chutes_error_shapes.sh`

Must prove:

- wrong model produces actionable error
- wrong/missing auth produces actionable error without leaking secrets
- malformed request produces actionable validation error

### `prove_chutes_retry_backoff.sh`

Can monkeypatch failures. It should not rely on provoking expensive real 429s.
It must prove:

- transient 429 triggers retry/backoff
- transient 5xx triggers retry/backoff
- retry budget is bounded
- final per-item status is explicit
- no fast retry loop

## 8. Monkeypatch Failure Testing

Sanity checks may monkeypatch controlled failures to prove the repair logic.

Allowed monkeypatch cases:

- first N provider calls return HTTP 429, then success
- first N provider calls return HTTP 500/503, then success
- one batch item returns transient failure while others succeed
- one batch item returns permanent invalid model error
- provider response is malformed
- timeout/cancellation path

Required monkeypatch proof:

- injected failure type
- number of injected failures
- observed retry count
- observed backoff schedule or minimum elapsed delay
- final item status
- no dropped item ids

Do not monkeypatch the only success proof. Real direct-provider and real Scillm
endpoint sanity are still required for promotion.

## 9. Deploy Mode

Deploy mode is allowed only after local checks or when the defect is explicitly
container/config related.

Allowed stack:

```text
deploy/docker/compose.scillm.core.yml
```

Allowed deploy commands:

```bash
docker compose -p scillm -f deploy/docker/compose.scillm.core.yml config
docker compose -p scillm -f deploy/docker/compose.scillm.core.yml ps
docker compose -p scillm -f deploy/docker/compose.scillm.core.yml up -d --build
docker compose -p scillm -f deploy/docker/compose.scillm.core.yml restart scillm
curl -s http://127.0.0.1:4001/health/liveliness
```

Denied by default:

- `docker compose down`
- `docker system prune`
- `docker volume rm`
- `systemctl`
- `crontab`
- `git push`

Post-deploy proof:

- compose config command captured
- build/relaunch command exit code captured
- `docker compose ps` captured
- `/health/liveliness` returns healthy response
- Chutes text sanity passes against container
- Chutes batch sanity passes against container
- proof artifacts attached to GitHub ticket

## 10. `subagent_memory`

The memory-owned baseline is implemented. Scillm-agent can now write
proof-backed repair records through `/upsert` and recall them through the normal
`/recall` path.

Proposed collection:

```text
subagent_memory
```

Required memory/ArangoDB properties:

- document collection in the `memory` database: implemented
- `subagent_memory_edges` edge collection for repair-path graph traversal:
  implemented
- added to the ArangoSearch View used by `/recall`: implemented through
  `unified_search`
- added to recall source routing: implemented as the `subagent_memory`
  supplemental source
- semantically synced to Qdrant by memory, not Scillm: implemented
- Qdrant payload includes `arango_collection="subagent_memory"` and matching
  `arango_key`
- no raw Arango or Qdrant writes from subagents
- graph promotion is memory-owned and source-grounded: implemented through
  `subagent_memory_edges`
- recall sanity test proves a natural-language query finds a known record:
  live proof returned Chutes canaries with positive dense and graph scores

Example record:

```json
{
  "_key": "scillm-agent:chutes:issue-123:loop-run-abc",
  "kind": "subagent_repair_lesson",
  "agent_id": "scillm-agent",
  "project": "scillm",
  "lane": "chutes_text_batch",
  "issue_url": "https://github.com/<owner>/<repo>/issues/123",
  "loop_receipt": ".loop/runs/<run_id>/final-receipt.json",
  "problem": "Scillm Chutes batch dropped item errors under transient 429 retry.",
  "solution": "Bounded concurrency with semaphore, as_completed collection, and per-item error receipts.",
  "status": "verified",
  "evidence": {
    "commands": [],
    "artifacts": []
  },
  "tags": [
    "project:scillm",
    "agent:scillm-agent",
    "lane:chutes",
    "provider:chutes",
    "repair:batch"
  ]
}
```

## 11. Promotion Gate

The Chutes lane can be marked usable only when all of these artifacts exist and
pass:

- GitHub ticket exists and is leased during repair
- `$loop` final receipt validates
- focused pytest passes
- direct Chutes text proof passes
- Scillm Chutes text proof passes
- Scillm Chutes batch proof passes
- monkeypatched retry/backoff proof passes
- monkeypatched partial-failure proof passes
- error-shape proof passes
- container rebuild/relaunch proof passes, if code/config changed
- post-container endpoint sanity proof passes
- proof file is commented on the GitHub ticket
- ticket closure uses proof file, not prose

Until then, status remains `PENDING`, `NEEDS_CHANGES`, or `BLOCKED`.
