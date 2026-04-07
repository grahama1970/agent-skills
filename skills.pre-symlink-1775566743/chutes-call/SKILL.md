---
name: chutes-call
description: >
  Centralized Chutes.ai LLM gateway as a shared Docker service. Global 5-slot
  semaphore enforces account concurrency limit across all agents. Single and
  batch calls with tenacious retry mode, circuit breaker, fallback chain, NDJSON
  streaming, and structured request/response objects with JSON cleaning.
triggers:
  - chutes call
  - chutes api
  - chutes gateway
  - llm call
  - llm gateway
  - chutes completion
  - chutes batch
  - tenacious call
  - chutes retry
  - chutes circuit breaker
  - cheap llm
  - deepseek call
allowed-tools:
  - Bash
  - Docker
metadata:
  short-description: Shared Docker LLM gateway with global concurrency control for Chutes.ai
provides:
  - llm-completion
  - llm-batch
  - chutes-gateway
  - json-cleaning
composes:
  - ops-chutes
  - rate-limit-recovery
  - service-status
taxonomy:
  - infrastructure
  - llm-completion
---

# chutes-call

Shared Docker FastAPI service (port 8630) that centralizes ALL Chutes.ai LLM
calls. Enforces the account-wide 5-concurrent-connection limit via a global
asyncio semaphore, handles retries with tenacity, implements a circuit breaker
(CLOSED/OPEN/HALF-OPEN), and returns structured request/response objects with
cleaned JSON.

## Why

- Chutes has a hard 5-concurrent-connection limit per account.
- Without centralized coordination, multiple agents cause ~50% failure rate.
- scillm's retry logic has shared mutable state bugs and 30s timeouts.
- 31 skills make bespoke Chutes calls — one gateway replaces all of them.

## Usage

```bash
# Start the gateway
./run.sh start

# Check health + circuit states
./run.sh health

# Stop
./run.sh stop

# View logs
./run.sh logs
```

## API

### POST /chat (single call)

```bash
curl -X POST http://localhost:8630/chat \
  -H "Content-Type: application/json" \
  -d '{"messages": [{"role": "user", "content": "What is 2+2?"}]}'
```

Response:
```json
{
  "ok": true,
  "content": "2+2 = 4",
  "json_content": null,
  "raw_content": "2+2 = 4",
  "model": "deepseek-ai/DeepSeek-V3",
  "backend": "chutes",
  "retries": 0,
  "elapsed_s": 1.2,
  "tokens_in": 12,
  "tokens_out": 8,
  "cost_usd": 0.001,
  "error": null,
  "circuit_state": "CLOSED"
}
```

### POST /batch (batch calls, NDJSON streaming)

```bash
curl -N -X POST http://localhost:8630/batch \
  -H "Content-Type: application/json" \
  -d '{
    "requests": [
      {"messages": [{"role": "user", "content": "Hello"}]},
      {"messages": [{"role": "user", "content": "World"}]}
    ],
    "tenacious": true,
    "stream": true
  }'
```

Each line is a JSON object:
```
{"index": 0, "ok": true, "content": "Hi!", "backend": "chutes", "elapsed_s": 1.1}
{"index": 1, "ok": true, "content": "World!", "backend": "chutes", "elapsed_s": 0.9}
{"summary": {"total": 2, "ok": 2, "errors": 0, "retries": 0, "cost_usd": 0.002}}
```

### GET /health

Returns service health, backend availability, and circuit breaker states.

### GET /queue

Live dashboard: active calls, queue depth, error rates, cost/min, per-caller stats.

### GET /usage / DELETE /usage

Accumulated cost/token stats since container start. DELETE resets counters.

## Tenacious Mode

Two operating modes controlled by the `tenacious` field:

| Mode | Retries | Backoff | Timeout | Fallback |
|------|---------|---------|---------|----------|
| Normal (`false`) | 1 | 2s fixed | 60s | None |
| Tenacious (`true`) | 5 | 2s→60s exponential+jitter | 60→120→180s escalating | OpenRouter → Gemini Flash |

## Circuit Breaker

Per-backend state machine:
- **CLOSED**: Normal operation. 3 consecutive failures → trip to OPEN.
- **OPEN**: All requests fail immediately (no network call). After 60s → HALF-OPEN.
- **HALF-OPEN**: 1 probe request. Success → CLOSED. Failure → OPEN.

## Architecture

```
Callers (any process/container)        Docker: embry-chutes-call :8630
  host processes, subagents,     →     Global Semaphore (5 slots)
  scillm, any skill              →     Tenacity retries + backoff
                                 →     Circuit breaker per backend
                                 →     Fallback chain
                                 →     JSON cleaning
                                 →     Cost tracking + dashboard
                                        ↓
                                 Chutes API (primary)
                                 OpenRouter (fallback 1)
                                 Gemini Flash (fallback 2)
```

## Security

- API keys mounted from host env (not baked into image).
- Container runs as non-root user.
- Host network mode for consistency with Embry services.
