# Opencode Transport

Extracted reference for `/scillm`. Load on demand — do not duplicate in SKILL.md.

**Canonical repo doc:** [`docs/SCILLM_OPENCODE_TRANSPORT_V1.md`](../../../docs/SCILLM_OPENCODE_TRANSPORT_V1.md)

### OpenCode transport v1 (DAG + collaboration)

> **Project-agent rule:** DAG execution, `/ask` opencode workers, and `/agent-debugger` use **`/v1/scillm/opencode/transport/*`**, not legacy blocking-only `/opencode/runs`. Monitor **reasoning and permissions on the SSE stream** — do not wait on a silent HTTP body or infer success from empty `assistant_text`.

Deep reference: [`docs/SCILLM_OPENCODE_TRANSPORT_V1.md`](../../../docs/SCILLM_OPENCODE_TRANSPORT_V1.md).

#### Good vs bad (transport)

| Situation | ✅ Good | ❌ Bad |
|-----------|---------|--------|
| Launch/steer a patches-only worker with course correction | `POST .../transport/runs` + `children` + `message` with `"stream": true`; watch `reasoning_delta`, `permission_requested` | Single blocking `POST .../message` with 600s read timeout and no event tail |
| Detect a stuck run | Read SSE or `events.jsonl` for heartbeats + reasoning; `waiting_permission` means real blocker | Assume failure only when HTTP returns |
| One-shot chat | `POST /v1/chat/completions` | Transport |
| Full tool loop in one artifact dir | `POST /v1/scillm/opencode/runs` | Transport (unless you intentionally use transport topology) |

#### API (headers on every call)

`Authorization: Bearer sk-dev-proxy-123`, `X-Caller-Skill: <skill-or-project>`.

| Method | Path |
|--------|------|
| `GET` | `/v1/scillm/opencode/transport/capabilities` |
| `POST` | `/v1/scillm/opencode/transport/runs` |
| `POST` | `/v1/scillm/opencode/transport/runs/{id}/children` |
| `POST` | `/v1/scillm/opencode/transport/runs/{id}/message` (**SSE default**) |
| `GET` | `/v1/scillm/opencode/transport/runs/{id}` |
| `GET` | `/v1/scillm/opencode/transport/runs/{id}/events/stream` |
| `POST` | `/v1/scillm/opencode/transport/runs/{id}/fork-supersede` |

#### `POST .../message` — streaming (default)

```bash
curl -N -X POST "http://127.0.0.1:4001/v1/scillm/opencode/transport/runs/$RUN_ID/message"   -H "Authorization: Bearer sk-dev-proxy-123"   -H "X-Caller-Skill: agent-debugger"   -H "Content-Type: application/json"   -d '{
    "prompt": "Propose patch only for the stated file.",
    "agent": "scillm-debugger",
    "role": "patch",
    "stream": true,
    "timeout_s": 600,
    "heartbeat_s": 15
  }'
```

| Field | Default | Notes |
|-------|---------|-------|
| `stream` | `true` | `false` → legacy blocking JSON (discouraged for project agents) |
| `timeout_s` | `600` | Overall stream budget |
| `heartbeat_s` | `15` | Idle liveness on SSE |
| `fork_supersede` | `false` | `true` on steer when forking child |

**Monitor events** (`data:` JSON lines, schema `scillm.opencode_transport.event.v1`):

| `event_type` | Action |
|--------------|--------|
| `reasoning_delta` | Model is thinking — use to spot confusion or loops |
| `permission_requested` | Worker blocked — intervene |
| `tool_call` | Tool progress; `status: error` is a real failure |
| `session_error` | Terminal problem |
| `heartbeat` | Alive; inspect `delivery_state` and `reasoning_excerpt` |
| `message.completed` | Final `result` with `assistant_text`, `diff`, `reasoning_excerpt` |

Artifacts: `.scillm/opencode-transport/<transport_run_id>/events.jsonl`. `/agent-debugger` also writes `monitor_events.jsonl` under `.scillm/agent-debugger/<run_id>/`.


