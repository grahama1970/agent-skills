# Ops Endpoints

Extracted reference for `/scillm`. Load on demand — do not duplicate in SKILL.md.

## Ops Endpoints

| Endpoint | Method | Purpose |
|---|---|---|
| `/health/liveliness` | GET | Is the proxy alive? |
| `/v1/scillm/health` | GET | Router health + fallback config + concurrency status |
| `/v1/scillm/model-pools` | GET | Server-side pool definitions plus live lane status |
| `/v1/scillm/model-pools/{pool}/status` | GET | Dashboard contract with live/stale pool concurrency |
| `/v1/scillm/active-calls` | GET | Live active calls plus stale diagnostics; not pool source of truth |
| `/v1/scillm/active-calls/purge` | POST | Purge stale in-memory active-call rows |
| `/v1/scillm/models` | GET | Model groups, deployments, aliases |
| `/v1/scillm/providers` | GET | **All available providers, auto-routing patterns, and examples** |
| `/v1/scillm/auth` | GET | **OAuth token health** — Claude/Codex token status, expiry, subscription tier |
| `/v1/models` | GET | OpenAI-compatible model list (includes auto-routable models) |
| `/v1/budget` | GET | Current daily spend and remaining budget |
| `/v1/scillm/agents/registry` | GET | Standing worker registry (check `workers` length; empty list = no workers) |
| `/v1/scillm/agents/{worker_id}/status` | GET | Worker idle/leased/running state |
| `/v1/scillm/agents/{worker_id}/handoffs` | POST | Prepare handoff envelope (requires `X-Caller-Skill`) |
| `/v1/scillm/agents/{worker_id}/leases` | POST | Acquire single-writer lease |
| `/v1/scillm/agents/{worker_id}/turn` | POST | Deliver handoff to Codex app-server |
| `/v1/scillm/agents/{worker_id}/events` | GET | Replay persisted protocol/events |
| `/v1/scillm/agents/{worker_id}/result` | GET | Read terminal turn result artifact |
| `/v1/scillm/agents/{worker_id}/cleanup` | POST | Release lease after terminal state |
| `/v1/scillm/opencode/health` | GET | OpenCode serve connectivity |
| `/v1/scillm/opencode/agents` | GET | OpenCode agent profiles on serve |
| `/v1/scillm/opencode/runs` | POST | Bounded OpenCode agent run (main multi-step entry) |
| `/v1/scillm/opencode/transport/runs` | POST | Transport run (DAG / collaboration) |
| `/v1/scillm/opencode/transport/runs/{id}/message` | POST | Transport message (**SSE** default) |
| `/v1/scillm/opencode/transport/runs/{id}/events/stream` | GET | Tail transport event stream |
| `/v1/scillm/opencode/events` | GET | Live OpenCode SSE bus |
| `/metrics` | GET | Prometheus counters (requests, errors, latency by group) |

```bash
curl http://localhost:4001/v1/scillm/health -H "Authorization: Bearer sk-dev-proxy-123"
curl http://localhost:4001/v1/scillm/models -H "Authorization: Bearer sk-dev-proxy-123"
curl http://localhost:4001/v1/budget -H "Authorization: Bearer sk-dev-proxy-123"
curl http://localhost:4001/metrics
```

---

