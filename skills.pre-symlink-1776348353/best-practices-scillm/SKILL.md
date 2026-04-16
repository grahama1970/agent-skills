---
name: best-practices-scillm
description: >
  Error recovery and anti-patterns for scillm LLM proxy. Load this when scillm calls fail,
  timeout, or return unexpected results. Covers batch sizing, header requirements, model
  selection, and debugging workflow.
triggers:
  - scillm error
  - scillm timeout
  - scillm best practices
  - llm call failed
  - 429 rate limit
  - queue timeout
  - batch processing scillm
license: MIT
metadata:
  category: debugging
  proxy_port: 4001
  debug_endpoint: /v1/scillm/debug

provides:
  - best-practices-scillm
composes:
  - scillm
---

# scillm Best Practices — Error Recovery & Anti-Patterns

Load this skill when scillm calls fail. It covers common mistakes and how to fix them.

## Quick Debugging

**Self-diagnose your failures:**
```bash
# Get LLM-powered analysis of your recent calls
curl "http://localhost:4001/v1/scillm/debug?caller=YOUR_SKILL_NAME&limit=3" \
  -H "Authorization: Bearer sk-dev-proxy-123"

# Or analyze a specific call by ID
curl "http://localhost:4001/v1/scillm/debug/CALL_ID" \
  -H "Authorization: Bearer sk-dev-proxy-123"
```

The debug endpoint returns:
- **Diagnosis:** What happened
- **Root Cause:** Why it happened
- **Fix:** Specific code change
- **Best Practice:** Which rule applies

---

## Anti-Patterns (Don't Do This)

### 1. Firing 50+ Requests at Once

**WRONG:**
```python
# DON'T - fires 400 requests, most will timeout in queue
tasks = [call_proxy(p) for p in all_400_prompts]
results = await asyncio.gather(*tasks)
```

**RIGHT:**
```python
# Process in chunks of 4 (matches provider concurrency)
CHUNK_SIZE = 4
for i in range(0, len(prompts), CHUNK_SIZE):
    chunk = prompts[i:i + CHUNK_SIZE]
    results = await asyncio.gather(*[call_proxy(p) for p in chunk])
```

**Why:** The proxy has a 600s queue timeout. Firing 100+ requests through 4 slots takes ~750s minimum (100 ÷ 4 × 30s). Later requests timeout waiting.

---

### 2. Missing X-Caller-Skill Header

**WRONG:**
```python
resp = httpx.post(url, json={"model": "text", ...})
```

**RIGHT:**
```python
resp = httpx.post(
    url,
    headers={
        "Authorization": "Bearer sk-dev-proxy-123",
        "X-Caller-Skill": "your-skill-name",  # REQUIRED
    },
    json={"model": "text", ...},
)
```

**Why:** Without this header, errors can't be traced back to your skill. The dashboard shows "no header" in amber.

---

### 3. Short Timeouts

**WRONG:**
```python
resp = httpx.post(url, timeout=5.0)  # Too short for LLM calls
```

**RIGHT:**
```python
resp = httpx.post(url, timeout=60.0)  # Generous timeout
# Or for batch: timeout=120.0
```

**Why:** LLM calls can take 10-30s. The proxy handles retries internally — let it work.

---

### 4. Using max_tokens

**WRONG:**
```python
json={"model": "text", "max_tokens": 100, ...}
```

**RIGHT:**
```python
json={"model": "text", ...}  # Omit max_tokens entirely
```

**Why:** `max_tokens` causes truncation and downstream failures. The proxy manages token limits.

---

### 5. Direct Provider Calls

**WRONG:**
```python
from openai import OpenAI
client = OpenAI(api_key="sk-...")  # Direct to OpenAI
```

**RIGHT:**
```python
from openai import OpenAI
client = OpenAI(
    base_url="http://localhost:4001/v1",
    api_key="sk-dev-proxy-123",
)
```

**Why:** Direct calls bypass the proxy's retries, fallbacks, logging, and cost tracking.

---

## Error Semantics (Updated 2026-04-15)

scillm uses specific HTTP codes to communicate different failure modes:

| Code | Meaning | What to Do |
|------|---------|------------|
| **429** | **Upstream provider rate limit** — Chutes/Gemini/etc rejected the request | Proxy auto-retries via fallback chain; if persistent, provider is saturated. Wait 60s or let queue drain. |
| **503** | **Proxy capacity exhausted** — Request waited 600s in queue but couldn't get a slot | Your batch is too large for available capacity. Use chunked processing (CHUNK_SIZE=4). |
| **400** | **Bad request** — Missing header, invalid model name, malformed JSON | Check X-Caller-Skill header (required), model alias, request format |
| **502** | **Provider error** — Upstream returned non-JSON or connection dropped | Transient; proxy will retry. If persistent, provider may be down. |

**Key distinction:** 429 = "provider says slow down" (external). 503 = "proxy queue full" (internal).

---

## Why Batch Operations Fail (Root Causes)

scillm was originally designed for single-call use cases. When batch jobs fire 100+ concurrent requests, protective mechanisms can turn hostile:

| Problem | Root Cause | Fix (2026-04-15) |
|---------|------------|------------------|
| **Cascade failure after errors** | Abuse guard blocked callers after 5 transient errors | Disabled — authenticated callers always pass |
| **Queue timeout after 60s** | Short timeout couldn't handle 100+ requests through 4 slots | Extended to 600s (10 min) |
| **Wrong error semantics** | Queue exhaustion returned 429 ("too fast") instead of 503 ("overloaded") | Returns 503 now |
| **Event loop blocked** | `threading.Lock` in async middleware blocked the event loop | Changed to `asyncio.Lock` |
| **Zombie slots persisted** | Background cleanup could die silently; 300s stale detection too slow | Auto-restart + 90s stale threshold |

**The math that kills unbounded batches:**
```
100 requests ÷ 4 slots × 30s/request = 750s minimum
With 60s queue timeout → requests #25+ die before reaching LLM
```

**The only remaining failure mode:** 503 after 600s queue wait. This means chunked processing is required.

---

## Error Patterns & Quick Fixes

| Error | Cause | Fix |
|-------|-------|-----|
| `503 SERVICE_BUSY` | Queue timeout after 600s | Use CHUNK_SIZE=4 for batches |
| `429 Rate limit` | Upstream provider exhausted | Proxy auto-retries; let fallback chain work |
| `Connection refused :4001` | Proxy not running | `docker compose -p scillm up -d` |
| `400 Missing X-Caller-Skill` | Required header missing | Add header to all requests |
| `401 Unauthorized` | Missing/wrong auth | Use `Bearer sk-dev-proxy-123` |
| `Empty response` | Model returned nothing | Check prompt; try different model |
| `TRUNCATED status` | Low completion tokens | Normal for short prompts; ignore |
| `FALLBACK status` | Unexpected model routing | Check cascade in `/v1/scillm/providers` |

---

## Automatic Error Guidance

When scillm calls fail, the proxy returns enriched error JSON with LLM-powered analysis:

```json
{
  "error": {
    "message": "Queue timeout after 60s",
    "type": "timeout_error",
    "code": 504,
    "advice": "Your batch of 400 requests caused queue timeout. Process in chunks of 4.",
    "recommendation": "CHUNK_SIZE = 4\nresults = []\nfor i in range(0, len(prompts), CHUNK_SIZE):\n    chunk = prompts[i:i + CHUNK_SIZE]\n    chunk_results = await asyncio.gather(*[call_proxy(p) for p in chunk])\n    results.extend(chunk_results)",
    "skill": "/best-practices-scillm",
    "debug_url": "http://localhost:4001/v1/scillm/debug/abc123",
    "analysis": "llm"
  }
}
```

| Field | Description |
|-------|-------------|
| `advice` | One-sentence fix description |
| `recommendation` | Copy-paste Python code to fix the issue (for batch errors) |
| `skill` | Load this skill for full best practices |
| `debug_url` | API endpoint to get detailed call analysis |
| `analysis` | "llm" if advice was generated by LLM analysis |

**Agents should check `error.recommendation`** — if present, it's executable code to fix the batch.

---

## Model Selection

| Use Case | Model | Notes |
|----------|-------|-------|
| General text | `text` | Cascades: Chutes → Gemini → DeepSeek |
| Images/PDFs | `vlm` | Auto-detected from image_url content |
| Fast/cheap | `text-gemini` | 1M context, free tier |
| Always-on | `local-text` | Ollama, no cost, for testing |
| High quality | `claude-sonnet-4-6` | OAuth via Claude Code subscription |

---

## Check Proxy Health

Before debugging errors, check proxy state:

```bash
# Full health check
curl -s -H "Authorization: Bearer sk-dev-proxy-123" \
  "http://localhost:4001/v1/scillm/health" | jq '.concurrency.chutes'

# Response shows:
# {
#   "in_flight": 2,       # Currently processing
#   "queued": 5,          # Waiting for slots
#   "available": 2,       # Slots open
#   "backoff_active": false,
#   "recent_429s": 0      # Provider rate limits hit
# }
```

| Field | Healthy | Problem |
|-------|---------|---------|
| `in_flight` | 0-4 | If stuck at limit with `queued > 0`, slots may be zombies |
| `queued` | 0-10 | If > 50, batch is too large |
| `backoff_active` | false | If true, provider hit rate limit — proxy is backing off |
| `recent_429s` | 0 | If > 0, provider is rate limiting — let fallback chain work |

**Reset stuck state:**
```bash
curl -X POST -H "Authorization: Bearer sk-dev-proxy-123" \
  "http://localhost:4001/v1/scillm/concurrency/reset"
```

---

## Debugging Workflow

1. **Check the dashboard:** `http://localhost:5183` → scillm tab
2. **Expand your job** to see individual calls
3. **Click a failed call** to open Call Trace
4. **Click "Analyze Call"** for LLM-powered diagnosis
5. **Click "Copy for Agent"** to get actionable fix

Or programmatically:
```python
# In your error handler
async def debug_my_call(call_id: str) -> str:
    resp = await httpx.get(
        f"http://localhost:4001/v1/scillm/debug/{call_id}",
        headers={"Authorization": "Bearer sk-dev-proxy-123"},
    )
    return resp.json().get("analysis", "No analysis")
```

---

## Checklist Before Calling scillm

```
[ ] Using httpx or openai SDK (NOT requests)
[ ] base_url = "http://localhost:4001/v1"
[ ] Authorization: Bearer sk-dev-proxy-123
[ ] X-Caller-Skill header set
[ ] timeout >= 60s
[ ] NO max_tokens in request
[ ] Batch size <= 4 concurrent (or chunked)
[ ] response_format: {"type": "json_object"} for JSON output
```
