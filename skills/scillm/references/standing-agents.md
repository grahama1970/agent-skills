# Standing Agents

Extracted reference for `/scillm`. Load on demand — do not duplicate in SKILL.md.

**Canonical repo doc:** [`docs/interactive-agents/routing.md`](../../../../docs/interactive-agents/routing.md)

### Scillm Interactive Agents (`/v1/scillm/agents/*`)

Standing interactive subagents are **not** the same surface as chat completions or
`scillm exec`:

| Surface | Endpoint family | What it is |
|---------|-----------------|------------|
| Chat / batch | `/v1/chat/completions`, `/v1/scillm/batch/completions` | One-shot model calls |
| Exec workers | `/v1/scillm/exec*` | Bounded Pi/OpenCode/Codex/Cursor/local-command workers |

Exec profiles (`codex-gpt-5.5`, `pi-chutes-kimi`, `cursor-auto`, etc.) are documented in **Scillm Exec Workers** above.

| Interactive agents | `/v1/scillm/agents/*` | Long-lived Codex app-server workers with handoff → lease → turn → events → result → cleanup |

**Decision rule:** use agents when a project agent needs a standing Codex-backed
collaborator across multiple turns (reviewer, implementation worker, UI reviewer).
Use exec for bounded one-shot workers. Use chat for ordinary LLM calls.

**Prerequisite:** `GET /v1/scillm/agents/registry` must include your worker id.
An empty `workers: []` array means no standing workers are registered yet
(`config/scillm-agents.yaml` or `SCILLM_AGENT_REGISTRY`). The registry endpoint
still returns `status: "configured"` even when the list is empty — check
`.workers | length`, not `.status`.

**Required headers on mutating calls:** `Authorization`, `Content-Type: application/json`,
and `X-Caller-Skill`.

**Mandatory workflow order:**

1. `GET /v1/scillm/agents/registry` — confirm worker exists
2. `GET /v1/scillm/agents/{worker_id}/status` — check idle/leased/running
3. `POST /v1/scillm/agents/{worker_id}/handoffs` — prepare canonical handoff envelope
4. `POST /v1/scillm/agents/{worker_id}/leases` — acquire single-writer lease
5. `POST /v1/scillm/agents/{worker_id}/turn` — deliver to Codex app-server Unix socket
6. `GET /v1/scillm/agents/{worker_id}/events?handoff_id=...` — replay protocol/events
7. `GET /v1/scillm/agents/{worker_id}/result?handoff_id=...` — read persisted turn result
8. `POST /v1/scillm/agents/{worker_id}/cleanup` — release lease after terminal state

Optional controls: `POST .../steer`, `POST .../interrupt`, `GET .../events/stream`.

```bash
BASE=http://127.0.0.1:4001
KEY=sk-dev-proxy-123
CALLER=my-project-agent
WORKER=pdf-oxide-reviewer
HANDOFF=phase-12-review
LEASE=${HANDOFF}-lease

curl -sf "$BASE/v1/scillm/agents/registry"   -H "Authorization: Bearer $KEY" -H "X-Caller-Skill: $CALLER" | jq .

curl -sf -X POST "$BASE/v1/scillm/agents/$WORKER/handoffs"   -H "Authorization: Bearer $KEY" -H "Content-Type: application/json" -H "X-Caller-Skill: $CALLER"   -d '{
    "handoff_id": "'"$HANDOFF"'",
    "phase_id": "phase-12",
    "goal": "Review the bounded patch and return scillm.agent_worker_result.v1 JSON.",
    "validation_expectations": ["structured worker result", "no undeclared writes"],
    "memory_context": [{"key": "plan", "summary": "phase context from project agent"}]
  }' | jq .

curl -sf -X POST "$BASE/v1/scillm/agents/$WORKER/leases"   -H "Authorization: Bearer $KEY" -H "Content-Type: application/json" -H "X-Caller-Skill: $CALLER"   -d '{"handoff_id": "'"$HANDOFF"'", "lease_id": "'"$LEASE"'", "owner": "'"$CALLER"'"}' | jq .

curl -sf -X POST "$BASE/v1/scillm/agents/$WORKER/turn"   -H "Authorization: Bearer $KEY" -H "Content-Type: application/json" -H "X-Caller-Skill: $CALLER"   -d '{
    "handoff_id": "'"$HANDOFF"'",
    "lease_id": "'"$LEASE"'",
    "service_name": "'"$CALLER"'",
    "approval_policy": "never",
    "wait_for_result": true,
    "result_timeout_seconds": 600
  }' | jq .
```

Turn delivery sets `contacts_codex: true` when the proxy actually talks to the worker's
Codex app-server socket. Reviewer workers may omit `memory_context` when
`memory_mode: optional`; implementation workers need `worker_worktree` and
`declared_write_set` in the registry.

Structured contracts live under `docs/interactive-agents/` (API, registry, worker
worktrees, result schemas). Live proof uses the project-agent sample module (real Codex, real review task):

```bash
./scripts/start_scillm_standing_agent.sh
./examples/standing-agent-sample/run.sh
# or: ./scripts/sanity_agents_endpoints.sh
```

The sample lives at `examples/standing-agent-sample/`. `project_agent_client.py`
is the consumer: it hands a review packet to worker `scillm-reviewer`, waits for
the standing Codex worker to inspect `sample_module/greeter.py`, and pass/fails
from the persisted result artifact. Mock Codex is not valid proof.

