# Proxy Internals

Extracted reference for `/scillm`. Load on demand — do not duplicate in SKILL.md.

## Middleware Stack

The proxy runs these middleware components on every request:

| Middleware | File | Purpose |
|-----------|------|---------|
| **JSON Guard** | `json_guard.py` | Validates JSON when `response_format.type == "json_object"`. Attempts repair (brace trim + json_repair lib) before rejecting. Failed validation triggers cascade to next provider. |
| **Concurrency Guard** | `concurrency_guard.py` | Per-provider semaphore (chutes=4, ollama=1, etc). Queues excess requests instead of 429. Prevents Chutes 90s penalty. |
| **VLM Auto-Router** | `vlm_router.py` | Detects `image_url` parts in messages, rewrites text model to `vlm`. Callers don't need to know model names. |
| **Cache Init** | `cache_init.py` | Auto-detects Redis at startup (via REDIS_HOST/REDIS_URL). Enables caching if available, no-op otherwise. |
| **Budget Guard** | `budget_guard.py` | Tracks Chutes daily usage. Classifies 429s as budget vs throttle. |
| **Pricing** | `pricing.py` | Per-1k token cost estimation. |
| **Metrics** | `metrics.py` | Prometheus counters: calls, 429s, budget limits, retries. |

## Fallback Cascade

When a provider fails, the proxy cascades to the next group:

```
text:          Chutes V3 (non-TEE, 1 retry) → V3.1-TEE → Gemini free → Gemini paid → DeepSeek
text-gemini:   Gemini free → Gemini paid → DeepSeek
vlm:           Gemini free → Gemini paid → Claude OAuth → Codex OAuth
text-gemini-3: Gemini 3 free → Gemini 3 paid
```

**Gemini free/paid are separate groups** — 429 on free cascades immediately to paid (no wasted retries on an exhausted key).

**Chutes cold-start**: Non-TEE deployment tried first with 1 retry (fast-fail). On 503, warmup API fires in background to notify miners. Falls through to TEE which is hot. Multi-model groups preserve config order (non-TEE before TEE).

Circuit breaker: 3 consecutive failures trigger a 20-second cooldown per group.

## Retry Policy

Per-exception-type retries across the cascade:

| Exception | Retries | Rationale |
|-----------|---------|-----------|
| 5xx (InternalServerError) | 8 | Provider will recover |
| 429 (RateLimit) | 6 | Back off but persist |
| Timeout | 6 | Retry aggressively |
| Auth (401/403) | 0 | Don't retry |
| BadRequest (400) | 0 | Don't retry |
| ContentPolicy | 0 | Don't retry |

Multi-model groups (non-TEE + TEE in same group) use 1 retry per deployment for fast fallthrough. With 4 groups in cascade (text → gemini-free → gemini-paid → deepseek), effective retry budget is ~24+ attempts before final failure.

## Caching

Redis caching is auto-enabled when `REDIS_HOST` or `REDIS_URL` is set:
- Deploy with `compose.scillm.stack.yml` (includes Redis)
- TTL: `SCILLM_CACHE_TTL_SEC` (default 3600s)
- Namespace: `SCILLM_CACHE_NAMESPACE` (default "scillm")
- Core compose (no Redis) works fine — caching is optional

---


