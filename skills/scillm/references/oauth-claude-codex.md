# Oauth Claude Codex

Extracted reference for `/scillm`. Load on demand — do not duplicate in SKILL.md.

## Claude OAuth (Anthropic Max Subscription)

Call Claude models through the proxy using your Max subscription — no API key needed.

### Exact model names (COPY THESE EXACTLY)

| Use this | NOT this | Maps to |
|----------|----------|---------|
| `claude-sonnet-4-6` | ~~text-claude-sonnet~~ | claude-sonnet-4-20250514 |
| `claude-opus-4-6` | ~~text-claude-opus~~ | claude-opus-4-20250514 |
| `claude-haiku-4-5` | ~~text-claude-haiku~~ | claude-haiku-4-5-20251001 |
| `claude-sonnet-4-5` | ~~claude-sonnet~~ | claude-sonnet-4-5-20250514 |

**The model name MUST start with `claude-`**. Names like `text-claude-sonnet`, `anthropic-sonnet`, or `sonnet-4-6` will NOT route to Claude — they will 500.

### Copy-paste example

```python
import httpx

resp = httpx.post(
    "http://localhost:4001/v1/chat/completions",
    headers={
        "Authorization": "Bearer sk-dev-proxy-123",
        "Content-Type": "application/json",
    },
    json={
        "model": "claude-sonnet-4-6",   # EXACTLY this string
        "messages": [
            {"role": "user", "content": "Your prompt here"}
        ],
    },
    timeout=60.0,
)
content = resp.json()["choices"][0]["message"]["content"]
```

### What works and what doesn't

| Parameter | Supported? | Notes |
|-----------|-----------|-------|
| `messages` | YES | Standard OpenAI format |
| `max_tokens` | OPTIONAL | Proxy defaults to 4096 for Claude. Omit for all other providers — most ignore it, some reject it. Only set it when you need a specific limit. |
| `temperature` | YES | 0.0-1.0 |
| `top_p` | YES | |
| `stop` | YES | String or list |
| `system` role in messages | YES | Native system prompt array for Claude OAuth (matches Pi CLI). Codex uses `instructions` field. |
| `response_format` | NO | Claude doesn't support json_object — ask for JSON in the prompt |
| `tools` / `tool_choice` | YES | Full tool use with streaming. Claude (Anthropic format), Codex (Responses API + reasoning + parallel_tool_calls), Gemini (native). Codex forces `tool_choice: "auto"` (no `"required"`). |
| `stream` | YES | SSE streaming with OpenAI delta format, including streaming tool call deltas |
| `scillm_metadata` | YES | Opaque passthrough — see below |

### scillm_metadata (opaque round-trip)

Send any dict as `scillm_metadata` in the request body. The proxy strips it before the LLM sees it, then staples it back onto the response unchanged. The LLM cannot fabricate or hallucinate these values.

**Use case**: In large async batches, pass the ArangoDB `_key` so you can join responses back to source documents without index tracking.

```python
# Request
resp = await client.post(url, json={
    "model": "text",
    "messages": [{"role": "user", "content": "Assess this control..."}],
    "scillm_metadata": {
        "_key": "sparta_controls/12345",
        "collection": "sparta_qra",
        "stage": "S12",
    },
}, headers=headers)

# Response — scillm_metadata round-trips untouched
data = resp.json()
data["scillm_metadata"]["_key"]  # → "sparta_controls/12345"
```

Works with all providers (Chutes, Gemini, Claude, Codex, Ollama, DeepSeek). The field is an arbitrary dict — add whatever fields you need. Non-streaming only (streaming responses don't carry it).

### Common mistakes that cause 500s

1. **Wrong model name**: `text-claude-sonnet` → use `claude-sonnet-4-6`
2. **Setting `max_tokens` too low**: reasoning models consume tokens internally — a low `max_tokens` means zero output. Omit it and let the proxy default.
3. **Sending `response_format: {"type": "json_object"}`**: Claude rejects this — instead say "Return valid JSON" in the prompt
4. **Timeout too short**: Claude can take 10-30s for complex prompts — use `timeout=60.0`

### Auth (automatic — no setup needed)

The proxy reads OAuth tokens from `~/.claude/.credentials.json` (managed by Claude Code, always fresh). Falls back to `~/.pi/agent/auth.json` (Pi CLI). No API key or manual token management needed — if Claude Code is running, Claude calls work.

### Verify OAuth before calling

Check token health before making calls — avoids 500 errors from expired tokens:

```python
auth = httpx.get(
    "http://localhost:4001/v1/scillm/auth",
    headers={"Authorization": "Bearer sk-dev-proxy-123"},
).json()

# Check Claude
if auth["claude"]["status"] == "valid":
    print(f"Claude OK — expires in {auth['claude']['expires_in_s']}s, tier: {auth['claude']['rate_tier']}")
else:
    print(f"Claude {auth['claude']['status']} — re-login needed")

# Check Codex
if auth["codex"]["status"] == "configured":
    print("Codex OK")
```

---

## Codex OAuth (OpenAI ChatGPT Subscription)

Call Codex/GPT models through the proxy using your ChatGPT Plus/Pro subscription. The proxy reads OAuth tokens from `~/.codex/auth.json` (managed by Codex CLI).

```python
resp = httpx.post(
    "http://localhost:4001/v1/chat/completions",
    headers={"Authorization": "Bearer sk-dev-proxy-123"},
    json={
        "model": "gpt-5.5",
        "messages": [{"role": "user", "content": "Explain quicksort"}],
    },
    timeout=120.0,
)
```

**Supported models:** `gpt-5.5`, `gpt-5.2-codex`, `gpt-5.3-codex`. `gpt-5.5` accepts OpenAI-compatible `image_url` content parts through `/scillm`; use it directly for high-reasoning image calls. Other platform GPT models (for example `gpt-4o`) are NOT supported via ChatGPT OAuth — they require a platform API key.

**Streaming:** Both Claude and Codex support `"stream": true`. The proxy translates provider-specific SSE events into OpenAI-compatible delta chunks (`data: {"choices":[{"delta":{"content":"..."}}]}`). Works with any SSE client including `httpx.stream()` and the OpenAI SDK.

For long grounded/reasoning **chat** calls, prefer streaming instead of one blocking HTTP response. Use:
- `timeout`: overall wall-clock budget, e.g. 300–600s.
- `stream_heartbeat_s`: heartbeat cadence for idle liveness, default 15s.
- Short client connect timeout, but no arbitrary 15s read cap.

The proxy keeps SSE connections live with heartbeat comments while providers are silent and fails only when the overall budget expires. If a caller needs named progress events for artifact writers, pass `stream_progress_events: true`; normal token chunks remain OpenAI-compatible `data:` chunks.

**Note:** `max_tokens` is ignored for Codex (the ChatGPT backend doesn't support it).

**Credential priority:** `~/.codex/auth.json` (Codex CLI) > `~/.pi/agent/auth.json` (Pi CLI).

---

