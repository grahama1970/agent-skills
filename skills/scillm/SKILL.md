---
name: scillm
description: >
  Universal LLM proxy on localhost:4001. One endpoint for all providers:
  Chutes, DeepSeek, Gemini, Ollama, Claude (OAuth), Codex (OAuth), GLM,
  OpenCode Go.
  Auto-routes by model name. POST /v1/chat/completions (OpenAI-compatible),
  POST /v1/images/generations for image generation, plus
  POST /v1/scillm/batch/completions for server-side model pools.
  Utilization-aware Chutes routing, ZIP explosion, PDF inlineData, fallback cascades, JSON repair.
allowed-tools: Bash, Read
triggers:
  - assess scillm usage
  - check LLM API usage
  - warm model check
  - cold model
  - batch LLM calls
  - parallel completions
  - describe image
  - describe figure
  - describe table
  - VLM call
  - multimodal
  - extract JSON from
  - analyze image
  - LLM completion
  - preflight check
  - source grounding
  - grounding verification
  - verify grounded
  - call claude
  - call codex
  - call gemini
  - call glm
  - call opencode go
  - call deepseek v4
  - call minimax
  - send zip to LLM
  - send PDF to LLM
metadata:
  short-description: scillm (universal LLM proxy — Chutes, Gemini, Claude, Codex, GLM, OpenCode Go, Ollama)
provides:
  - llm-completion
  - usage-assessment
composes: [task-monitor, create-evidence-case, analytics, create-figure, llm-eval-lab]

taxonomy:
  - inference
  - llm
---

# scillm — One Endpoint for All LLM Calls

## Architecture

```
Client → scillm :4001 (Python) → Provider API
                ↓
       utls-proxy :8444 (Codex only)
                ↓
       chatgpt.com (Chrome TLS fingerprint)
```

- **scillm** (Python): Public API, request validation, JSON guard, VLM auto-routing, OAuth token injection, retries, circuit breakers, fallback cascades. Routes directly to providers via openai SDK.
- **utls-proxy** (Go): TLS fingerprint proxy for Cloudflare-protected endpoints (Codex). Presents Chrome's JA3 fingerprint to bypass Cloudflare.

## Setup (one-time per provider)

Most providers need zero setup — scillm reads existing credentials automatically.

| Provider | Setup | How it works |
|----------|-------|--------------|
| **Claude** | Nothing if Claude Code OAuth is valid; refresh with `claude auth login --claudeai` if `/v1/scillm/auth` reports `expired` | Reads `~/.claude/.credentials.json` automatically. |
| **Codex** | `npm install -g @openai/codex && codex login` | Creates `~/.codex/auth.json`. One-time login, scillm reads it. |
| **Gemini (OAuth)** | `npm install -g @anthropic-ai/gemini-cli && gemini login` | Creates `~/.gemini/oauth_creds.json`. **Recommended**: bypasses 20 RPD API limit. |
| **Gemini (API)** | Add `GEMINI_API_KEY=your-key` to `.env` | Get key from [aistudio.google.com](https://aistudio.google.com/apikey). **Limited to 20 RPD on gemini-2.5-flash.** |
| **GLM** | Add `GLM_API_Key=your-key` to `.env` | Get key from [z.ai](https://z.ai) (Coding Lite plan or higher) |
| **Chutes** | Add `CHUTES_API_KEY` and `CHUTES_API_BASE` to `.env` | PAYG or subscription at [chutes.ai](https://chutes.ai) |
| **DeepSeek** | Add `DEEPSEEK_API` to `.env` | Get key from [platform.deepseek.com](https://platform.deepseek.com) |
| **OpenCode Go** | Add `OPENCODE_GO_API_KEY` to `.env` | Call exact models as `opencode-go/<model-id>`. Live model discovery uses Docker-installed `opencode models --refresh opencode-go` with host OpenCode auth/config/cache mounted into Docker. |
| **Ollama** | `ollama pull model:tag` | Local models, no auth needed |
| **OpenAI Images** | `codex login` OAuth; optional `OPENAI_API_KEY` override | Used only by `/v1/images/generations` for image output |

After setup, rebuild the proxy: `docker compose -p scillm -f deploy/docker/compose.scillm.core.yml up -d --build`

**Verify auth status:** `curl http://localhost:4001/v1/scillm/auth -H "Authorization: Bearer sk-dev-proxy-123" -H "X-Caller-Skill: my-skill-name"`

## Quick Health Check

```bash
# No auth needed — check if proxy is running
curl -s http://localhost:4001/health | jq .
# → {"status": "ok", "uptime_seconds": 123.4}
```

## How to Call

> **Auth header is REQUIRED.** Without `Authorization: Bearer sk-dev-proxy-123`, you get 401.

```bash
# Minimal call (works with standard OpenAI SDK; caller header is required)
curl -s http://localhost:4001/v1/chat/completions \
  -H "Authorization: Bearer sk-dev-proxy-123" \
  -H "X-Caller-Skill: your-skill-name" \
  -H "Content-Type: application/json" \
  -d '{"model": "chutes-deepseek", "messages": [{"role": "user", "content": "Hi"}]}'

# Better: include caller header for debugging
curl -s http://localhost:4001/v1/chat/completions \
  -H "Authorization: Bearer sk-dev-proxy-123" \
  -H "X-Caller-Skill: your-skill-name" \
  -H "Content-Type: application/json" \
  -d '{"model": "chutes-deepseek", "messages": [{"role": "user", "content": "Hi"}]}'
```

**POST `http://localhost:4001/v1/chat/completions`** — standard OpenAI chat format.
Use httpx, openai SDK, or curl. No pip install. No imports.

**POST `http://localhost:4001/v1/images/generations`** — standard OpenAI-shaped
image generation. This is for image output. Do not hide image generation behind
chat completions.

**Headers:**
- `Authorization: Bearer sk-dev-proxy-123` — **REQUIRED**
- `X-Caller-Skill: your-skill-name` — **REQUIRED** (enables per-skill cost tracking, dashboard registration, and useful project-agent error feedback)

The proxy handles provider cascading, retries, JSON validation, VLM auto-routing,
concurrency limits, budget tracking, and optional Redis caching.

## Image Generation

Image output is a first-class response shape:

```bash
curl -s http://localhost:4001/v1/images/generations \
  -H "Authorization: Bearer sk-dev-proxy-123" \
  -H "X-Caller-Skill: your-skill-name" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gpt-image-2",
    "prompt": "a precise architecture diagram of ask calling scillm for image generation",
    "size": "1024x1024",
    "quality": "high",
    "response_format": "b64_json"
  }'
```

Uses Codex/OpenAI OAuth credentials by default; `OPENAI_API_KEY` is only an
optional platform-key override. The normalized response has `object:
"image.generation"` and `data[]` entries containing `b64_json`, `url`, and/or
`revised_prompt` when the provider returns them. Calling skills should write
image files and manifests as their own artifacts.

## Long-Running Streaming Calls

This section is provider-agnostic. It applies to Kimi, OpenCode Go, Chutes,
Claude, Codex, Gemini, GLM, DeepSeek, and any other `/v1/chat/completions`
model that supports `stream: true`.

For long grounded/reasoning/oracle calls, use SSE streaming instead of one
blocking HTTP response:

```json
{
  "model": "opencode-go/kimi-k2.6",
  "messages": [{"role": "user", "content": "Your long task..."}],
  "stream": true,
  "stream_progress_events": true,
  "stream_heartbeat_s": 5,
  "timeout": 600
}
```

Operational contract:

- `stream: true` is the liveness path; consume the SSE socket until `data: [DONE]`.
- `timeout` is the hard wall-clock budget for the whole call, not an idle/read timeout.
- `stream_heartbeat_s` controls idle heartbeat cadence while providers are thinking silently.
- `stream_progress_events: true` adds named `started`, `heartbeat`, `done`, and `error` events for artifact writers; token chunks remain OpenAI-compatible `data:` chunks.
- Provider errors preserve OpenAI-compatible response shape and also include stable `provider_error_code` values such as `PROVIDER_AUTH_FAILED`, `PROVIDER_RATE_LIMITED`, and `PROVIDER_TIMEOUT`. Callers should branch on those codes instead of parsing provider prose.
- Logs, SSE error payloads, diagnostics, and JSONL/Arango artifacts are centrally redacted. Do not rely on raw provider payloads or OAuth token text appearing in artifacts.
- Client HTTP libraries should use a short connect timeout and no arbitrary short read cap. Do not use fixed 15s/30s read timeouts for deep-review/oracle calls.
- scillm keeps `/v1/scillm/active-calls` rows open until the stream finishes, fails, or the client disconnects.
- Active-call snapshots and Arango/JSONL logs include `stream_heartbeat_s`, `stream_progress_events`, `deadline_timeout_s`, `dynamic_timeout_s`, and `timeout_source`.

If an agent reports a Kimi, Chutes, Claude, or Codex call as stale/running, it
must inspect those active-call/log proof fields before blaming auth, routing,
or model health. Heartbeats mean the call is live; budget expiry produces an
explicit timeout/error event and terminal cleanup.

## Available Models

### Selection Contract

Project agents should choose models through this small public contract:

1. Provider-family profiles for production work: `oc-kimi`, `oc-qwen`, `oc-deepseek`, `chutes-deepseek`, `chutes-kimi`, `chutes-qwen`, `chutes-vlm`, `gemini-flash`, `gemini-flash-high`, `claude-sonnet`, `claude-sonnet-high`, `claude-opus`, `claude-opus-high`, `claude-haiku`, `codex-vision`, `gpt-5.5`.
2. Model pools for high-volume production batches: `qra-deepseek-pool` for QRA/default DeepSeek work, or another explicitly defined pool.
3. Direct provider model IDs when an exact variant matters: `opencode-go/deepseek-v4-flash`, `deepseek-ai/DeepSeek-R1-0528-TEE`, `claude-sonnet-4-20250514`, `gemini-2.5-flash`, or any other supported direct provider ID.
4. Generic aliases: `text` and `vlm` are acceptable for smoke tests, ad hoc exploration, or low-stakes utilities. Do not use `text` for production prompt contracts, schema-sensitive extraction, QRA generation, evidence-case generation, review artifacts, or repeatable batch work unless the caller explicitly accepts cross-family fallback variability.

Do not invent aliases for variants. If a project agent is unsure, it must call:

```bash
curl http://localhost:4001/v1/scillm/models \
  -H "Authorization: Bearer sk-dev-proxy-123" \
  -H "X-Caller-Skill: your-skill-name"
```

Retired or confusing aliases return a 400 with `project_agent_message`, a replacement model, and the same `/v1/scillm/models` discovery instruction.

`/v1/scillm/models` also returns a flattened `models` map with per-name
`capabilities`. Project agents must inspect these fields instead of inferring
multimodal support from the name. Use `?include_capacity=true` when concurrency
matters; records then include `provider_concurrency_key`, `capacity`, and
`recommended_max_concurrency`. Capacity includes current slots plus rolling
`avg_in_flight_5m` and `avg_utilization_5m`. Use `?include_models_dev=true` only when
advisory public catalog metadata is needed; it enriches callable records from
`https://models.dev/api.json` but does not make external catalog models
callable through scillm.

```json
{
  "models": {
    "oc-kimi": {
      "target": "opencode-go/kimi-k2.6",
      "endpoint": "/v1/chat/completions",
      "capabilities": {
        "text_input": true,
        "image_input": true,
        "pdf_input": false,
        "image_output": false,
        "streaming": true,
        "tools": true
      }
    },
    "gpt-image-2": {
      "endpoint": "/v1/images/generations",
      "capabilities": {
        "text_input": true,
        "image_output": true,
        "image_input": false
      }
    }
  }
}
```

For direct catalog inspection without mixing in scillm routing state:

```bash
curl -s "http://localhost:4001/v1/scillm/models-dev?provider=opencode-go&model=kimi-k2.6" \
  -H "Authorization: Bearer $SCILLM_API_KEY" \
  -H "X-Caller-Skill: your-skill-name"
```

### Public Names

| Model | Backend | Use Case | Fallback |
|-------|---------|----------|----------|
| `text` | Chutes DeepSeek (chutes_router) | Ad hoc/smoke text only; avoid for production prompt contracts because it may cross model families | → V3.1-TEE → R1-0528-TEE → text-kimi → text-qwen3 → text-qwen3-large |
| `chutes-deepseek` | Chutes DeepSeek cascade | Public provider-family alias for the default Chutes DeepSeek lane | internal cascade |
| `chutes-kimi` | Chutes Kimi K2.5-TEE | Public provider-family alias for Kimi on Chutes | internal cascade |
| `chutes-qwen` | Chutes Qwen3 thinking | Public provider-family alias for Qwen on Chutes | internal cascade |
| `chutes-vlm` | Chutes GLM-4.6V | Higher-throughput Chutes image calls | (none) |
| `vlm` | Gemini 2.5 Flash (free key) | Image/PDF/screenshot description | → vlm-paid → claude-sonnet → codex-vision |
| `local-text` | Ollama qwen2.5:0.5b (local) | Smoke tests, always-on fallback | (none) |
| `moonshot-text` | Moonshot Kimi K2 | Alternative text provider | (none) |
| `gemini-flash-oauth` | Gemini via CLI subprocess | **Recommended**: 1M context, no RPD limit | (none) |
| `gemini-flash` | Gemini 2.5 Flash (free key) | Fast, 1M context | → gemini-flash-free2 → gemini-flash-paid |
| `gemini-flash-high` | Gemini 3 Flash Preview (free key) | Thinking model, default high reasoning | → gemini-flash-high-free2 → gemini-flash-high-paid |
| `claude-sonnet` | Claude Sonnet (`claude-sonnet-4-20250514`) OAuth | General Claude tasks — **NOT for batch** | (none) |
| `claude-sonnet-high` | Claude Sonnet (`claude-sonnet-4-20250514`) OAuth | Sonnet with default high reasoning — **NOT for batch** | (none) |
| `claude-opus` | Claude Opus (`claude-opus-4-20250514`) OAuth | Complex reasoning — **NOT for batch** | (none) |
| `claude-opus-high` | Claude Opus (`claude-opus-4-20250514`) OAuth | Opus with default high reasoning — **NOT for batch** | (none) |
| `claude-haiku` | Claude Haiku 4.5 (OAuth) | Fast, cheap — **NOT for batch** | (none) |
| `gpt-5.5` | OpenAI Codex (OAuth) | Direct high-reasoning text + image calls — **NOT for batch** | (none) |
| `opencode-go/deepseek-v4-flash` | OpenCode Go `/messages` | Faster DeepSeek V4; preferred OpenCode batch lane | (none) |
| `opencode-go/deepseek-v4-pro` | OpenCode Go `/messages` | Stronger/slower DeepSeek V4; quality spot checks | (none) |
| `opencode-go/minimax-m2.7` | OpenCode Go `/messages` | MiniMax coding model | (none) |
| `oc-kimi` | OpenCode Go Kimi | Memorable alias for `opencode-go/kimi-k2.6` | (none) |
| `oc-qwen` | OpenCode Go Qwen | Memorable alias for `opencode-go/qwen3.6-plus` | (none) |
| `oc-deepseek` | OpenCode Go DeepSeek V4 Pro | Memorable alias for `opencode-go/deepseek-v4-pro` | (none) |
| `codex-vision` | GPT-5.3 Codex (OAuth) | Codex VLM fallback lane; image delivery must pass a smoke test before use | (none) |
| Any `gemini-*` | Google | Auto-routed to Gemini API | (none) |
| Any `claude-*` | Anthropic | Auto-routed via Claude Code OAuth | (none) |
| Any `gpt-*`/`codex-*` | OpenAI | Auto-routed via Codex CLI OAuth | (none) |
| Any `Org/Model` | Chutes | Auto-routed to Chutes API | (none) |
| Any `model:tag` | Ollama | Auto-routed to local Ollama | (none) |

**Use the model or family profile directly.** Prefer provider-family profiles or
exact model IDs for production prompts and code. Broad generic aliases such as
`text` are smoke/ad hoc conveniences, not repeatable workflow defaults.

| Pattern | Provider | Auth | Example |
|---------|----------|------|---------|
| `claude` / `sonnet` | Anthropic Claude Sonnet | Claude Code Max OAuth | `claude-sonnet` |
| `opus` | Anthropic Claude Opus | Claude Code Max OAuth | `claude-opus` |
| `haiku` | Anthropic Claude Haiku | Claude Code Max OAuth | `claude-haiku` |
| `claude-*` | Anthropic | Claude Code Max OAuth | `claude-sonnet-4-20250514` |
| `gpt-*` / `codex-*` | OpenAI Codex | ChatGPT OAuth | `gpt-5.5` |
| `gemini-flash-oauth` | Google | Gemini CLI OAuth | Uses `gemini -p` subprocess, bypasses API limits |
| `gemini-*` | Google | API key | `gemini-2.0-flash` (1500 RPD), `gemini-2.5-flash` (20 RPD) |
| `glm-*` (via `text-glm`) | Z.AI GLM | API key | `text-glm` → glm-5.1 |
| `opencode-go/*` | OpenCode Go | `OPENCODE_GO_API_KEY` | `opencode-go/deepseek-v4-flash` |
| `Org/Model` | Chutes | API key | `Qwen/Qwen3-30B-A3B` |
| `model:tag` | Ollama (local) | none | `qwen2.5:7b` |

**OpenCode Go capability contract:** inspect `/v1/scillm/opencode-go/models` and use each model's `input` object (`text`, `image`, `pdf`) as the routing contract. Current verified behavior: `opencode-go/kimi-k2.6` accepts normal PNG/JPEG `image_url` data URIs through `/chat/completions`; `opencode-go/deepseek-v4-*` and `opencode-go/minimax-*` are text-only through `/messages`; OpenCode Go PDF input is not enabled. Do not use 1x1/tiny PNG fixtures for Kimi VLM smoke tests: Moonshot behind OpenCode Go can reject those with `failed to decode image` even though larger PNG/JPEG data URIs work. Use a real page crop/screenshot or a fixture at least tens of pixels wide. Do not use `opencode run --file` as a headless multimodal workaround yet: upstream OpenCode issues #16723 and #20802 are open for broken MIME/file attachment handling in CLI/custom-provider paths.

Internal fallback groups such as `text-kimi`, `text-qwen3`, `text-qwen3-large`, `text-research`, `vlm-chutes`, and `gemini-flash-paid` may appear in `/v1/scillm/models`. They are supported for debugging and explicit routing, but project agents should prefer the public names above or direct provider IDs.

**Image routing separation:**
- `/scillm` HTTP VLM calls use image-capable model routes such as `model: "vlm"` or a verified direct VLM lane. If using `model: "vlm-chutes"` for bulk/high-throughput VLM, run a smoke test first; stale Chutes model IDs can return `model not found`.
- `gpt-5.5` high-reasoning image analysis can go directly through `/scillm` using OpenAI-compatible `image_url` parts or convenience fields such as `file_path`, `path`, `url`, and `urls`.
- Use `codex exec --image ...` only when the task specifically needs a full project-agent session with workspace tools, not for ordinary image analysis through the proxy.

**PDF Lab second-pass batch guidance:**
- For PDF Lab visual second-pass over 50-100 candidate regions, prefer bounded `POST /v1/chat/completions` calls with `model: "oc-kimi"` or direct `model: "opencode-go/kimi-k2.6"` after `/v1/scillm/opencode-go/models` confirms `input.image=true`.
- Attach the annotated page/crop PNG as an OpenAI-style `image_url` data URI. Do not send only filesystem paths and claim visual review.
- Use `asyncio.create_task` + `asyncio.as_completed` with low concurrency, usually 2 unless `/v1/scillm/concurrency?model=oc-kimi` proves more capacity.
- Include stable `scillm_metadata.batch_id` and `scillm_metadata.item_id` for every candidate so model responses can be joined back to artifacts and retried.
- Do not use text-only DeepSeek (`model: "text"` or `deepseek-ai/*`) for decisions that require inspecting page images, bbox overlays, crops, or visual table structure.
- Do not use OAuth-heavy `claude-opus-high` or `gpt-5.5` as a large batch lane. Reserve them for a few hard adjudication cases or explicit high-reasoning image analysis.

**Legacy broad fallback chain for ad hoc chat routing** (not model pools):

This section applies to ordinary `/v1/chat/completions` calls such as
`model: "text"`. Treat this as a convenience/smoke path, not the production
default. Most repeatable work should stay inside one model family or one
explicit model pool for prompt/response consistency.

This section does **not** apply to `/v1/scillm/batch/completions` or
`/v1/scillm/batch/completions/stream` model pools. QRA corpus repair uses
`model_pool: "qra-deepseek-pool"`, whose lanes must be validated through the
pool status and provider catalog checks in the batch section below.

For ad hoc single-call `model: "text"` requests, scillm:

1. Fetches utilization data from Chutes API (cached 5 minutes)
2. Discovers all available models in the `deepseek-large` family
3. Scores each: `util% * 80`, penalizes >25% rate-limit (score=100) or >95% util (score=90)
4. Sorts all models by score (lowest = best)
5. Appends static fallbacks: `text-kimi`, `text-qwen3`, `text-qwen3-large`
6. Injects full chain via `_dynamic_fallback_chain` to the router

**Example chain** (actual 2026-04-15):
```
Chimera-TEE (25% util) → V3.1-TEE (37%) → R1-0528-TEE (90%) → V3.2-TEE (saturated) → text-kimi → text-qwen3 → text-qwen3-large
```

This can keep exploratory calls alive under rate limits, but it can also change
response style and schema behavior across runs. Production callers should use a
family-specific profile or exact model instead. OAuth providers (Codex, Claude)
are excluded to avoid account bans.

**Chutes cold-start handling**: Non-TEE tried first (1 retry), falls through to TEE on 503. Warmup API fires in background on cold detect — miners notified to spin up. Next call may hit warm non-TEE.

> **`text-research` — Harvard Research Endpoint (25% off)**
>
> Chutes is running a research collaboration with Harvard to build a caching algorithm. Use `model: "text-research"` to opt in:
> - **25% discount** on inference costs
> - Same models, same API, same quality
> - **Prompts and responses are logged** for research
>
> **DO NOT use for sensitive data** — SPARTA extractions, compliance docs, credentials, PII. Keep those on `text` (standard endpoint).
>
> Good for: batch processing, summarization, general extraction, non-sensitive workloads.

**Discover all available models:** `GET /v1/scillm/providers` returns every provider, its auto-routing pattern, available models, and auth status.

---

## Single Call

**scillm is an HTTP API, not a Python package. Do NOT `import scillm`. Use httpx.**

**REQUIRED: Always include `X-Caller-Skill` header** — identifies who made the call for debugging, cost tracking, and error correlation. Use your skill name or project name (derived from pwd).

```python
import httpx

resp = httpx.post(
    "http://localhost:4001/v1/chat/completions",
    headers={
        "Authorization": "Bearer sk-dev-proxy-123",
        "X-Caller-Skill": "my-skill-name",  # REQUIRED: your skill or project name
    },
    json={"model": "chutes-deepseek", "messages": [{"role": "user", "content": "What is 2+2?"}]},
    timeout=30.0,
)
content = resp.json()["choices"][0]["message"]["content"]
```

### With openai SDK

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://localhost:4001/v1",
    api_key="sk-dev-proxy-123",
    default_headers={"X-Caller-Skill": "my-skill-name"},  # REQUIRED
)
resp = client.chat.completions.create(
    model="chutes-deepseek",
    messages=[{"role": "user", "content": "Hello"}],
)
print(resp.choices[0].message.content)
```

## JSON Response

Add `response_format` — the proxy auto-validates and retries on broken JSON:

```python
resp = httpx.post(
    "http://localhost:4001/v1/chat/completions",
    headers={
        "Authorization": "Bearer sk-dev-proxy-123",
        "X-Caller-Skill": "my-skill-name",
    },
    json={
        "model": "chutes-deepseek",
        "messages": [{"role": "user", "content": "Return {name, age} for Alice who is 25"}],
        "response_format": {"type": "json_object"},
    },
    timeout=30.0,
)
data = json.loads(resp.json()["choices"][0]["message"]["content"])
```

## Reasoning Effort

Send top-level `reasoning_effort` for reasoning-capable models. Do not hide it
inside `scillm_metadata`; metadata is only for correlation and never reaches the
provider.

```python
resp = httpx.post(
    "http://localhost:4001/v1/chat/completions",
    headers={
        "Authorization": "Bearer sk-dev-proxy-123",
        "X-Caller-Skill": "my-skill-name",
    },
    json={
        "model": "gpt-5.5",
        "messages": [{"role": "user", "content": "What is 2 + 2?"}],
        "reasoning_effort": "high",
    },
    timeout=120.0,
)
data = resp.json()
print(data["scillm_reasoning"])
```

Canonical public field: `reasoning_effort`.

Compatibility aliases accepted and normalized: `reasoning: "high"`,
`reasoning: {"effort": "high"}`, and matching `extra_body` shapes. New callers
should use `reasoning_effort`.

| Provider | Public levels | Provider field |
|----------|---------------|----------------|
| Codex (`gpt-*`, `codex-*`) | `none`, `minimal`, `low`, `medium`, `high`, `xhigh` | `reasoning.effort` |
| Claude Sonnet/Opus | `low`, `medium`, `high`, `xhigh`, `max` | `thinking: {"type": "enabled", "budget_tokens": ...}` |
| Gemini 3.x | `minimal`, `low`, `medium`, `high` (`none` maps to `minimal`) | `generationConfig.thinkingConfig.thinkingLevel` |

Proof surfaces:

- Non-streaming responses include `scillm_reasoning`.
- Codex/Claude final SSE chunks include `scillm_reasoning`.
- HTTP responses include `x-scillm-reasoning-*` headers.
- Arango/JSONL logs include `reasoning_effort_requested`,
  `reasoning_effort_applied`, `reasoning_forwarded`,
  `reasoning_provider_field`, and `reasoning_ignored_reason`.

If a valid public level is unsupported by the selected provider, scillm does not
silently pretend it worked: proof metadata shows `forwarded=false` and
`ignored_reason=unsupported_effort_for_provider`.

## Image Analysis (VLM Auto-Routing)

Send images with an image-capable family profile such as `chutes-vlm`,
`gemini-flash`, `claude-sonnet`, or `gpt-5.5`. The legacy `text` route can
auto-detect image parts and reroute to VLM, but production image workflows
should choose the intended model family explicitly:

```python
import base64, httpx

with open("photo.png", "rb") as f:
    b64 = base64.b64encode(f.read()).decode()

resp = httpx.post(
    "http://localhost:4001/v1/chat/completions",
    headers={
        "Authorization": "Bearer sk-dev-proxy-123",
        "X-Caller-Skill": "my-skill-name",
    },
    json={
        "model": "chutes-vlm",
        "messages": [{"role": "user", "content": [
            {"type": "text", "text": "Describe this image"},
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}},
        ]}],
    },
    timeout=60.0,
)
description = resp.json()["choices"][0]["message"]["content"]
```

For least cognitive load on high-reasoning image calls, send the image directly
to `model: "gpt-5.5"`. Local paths are accepted through convenience fields and
are normalized to OpenAI-compatible `image_url` parts by the proxy:

`file_path`/`path` are resolved by the running proxy process. In Docker, that
means the path must be mounted into the container. For arbitrary host-only paths,
inline the image as a data URI or use a client helper that does the base64
encoding before sending the HTTP request.

```python
resp = httpx.post(
    "http://localhost:4001/v1/chat/completions",
    headers={
        "Authorization": "Bearer sk-dev-proxy-123",
        "X-Caller-Skill": "my-skill-name",
    },
    json={
        "model": "gpt-5.5",
        "reasoning_effort": "high",
        "messages": "Analyze this screenshot and identify the likely issue.",
        "file_path": "/absolute/path/to/screenshot.png",
    },
    timeout=120.0,
)
data = resp.json()
print(data["choices"][0]["message"]["content"])
print(data["scillm_multimodal"]["image_seen_by"])  # codex-oauth
```

Use `codex exec --image` only when the requirement is a full Codex project-agent
session over the workspace, not for ordinary HTTP image analysis.

### Multiple Images

Attach multiple images by adding multiple `image_url` parts to the same user
message. This is the preferred project-agent pattern for arbitrary host files,
because the agent inlines the bytes before sending the HTTP request:

```python
import base64, mimetypes, httpx

def image_part(path: str) -> dict:
    mime = mimetypes.guess_type(path)[0] or "image/png"
    with open(path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode()
    return {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}}

paths = ["/absolute/path/before.png", "/absolute/path/after.png"]

resp = httpx.post(
    "http://localhost:4001/v1/chat/completions",
    headers={
        "Authorization": "Bearer sk-dev-proxy-123",
        "X-Caller-Skill": "my-skill-name",
    },
    json={
        "model": "gpt-5.5",
        "reasoning_effort": "high",
        "messages": [{
            "role": "user",
            "content": [
                {"type": "text", "text": "Compare these screenshots and identify what changed."},
                *[image_part(path) for path in paths],
            ],
        }],
    },
    timeout=180.0,
)
data = resp.json()
assert data["scillm_multimodal"]["image_seen_by"] == "codex-oauth"
```

If every path is visible inside the proxy container, the convenience form also
supports multiple paths:

```python
json={
    "model": "gpt-5.5",
    "reasoning_effort": "high",
    "messages": "Compare these screenshots.",
    "paths": ["/container-visible/before.png", "/container-visible/after.png"],
}
```

## Message Formats

scillm accepts three forms for `messages` — use whichever is simplest for your use case:

| Form | When to use | Example |
|------|-------------|---------|
| **Plain string** | Single-turn text prompts | `"messages": "What is 2+2?"` |
| **Convenience fields** | Images/files (auto VLM routing) | `"messages": "Describe this", "file_path": "photo.png"` |
| **OpenAI array** | Multi-turn, system prompts, multimodal | `"messages": [{"role": "system", ...}, {"role": "user", ...}]` |

Plain strings are auto-wrapped as `[{"role": "user", "content": str}]`.
Convenience fields (`url`, `urls`, `file_path`, `paths`) auto-detect images, base64-encode local files, and route to VLM.
OpenAI-style arrays pass through unchanged — full control for multi-turn, system prompts, and explicit `image_url` parts.

## Batch Calls (Parallel Completions)

**NO IMPORT REQUIRED.** scillm is an HTTP endpoint; do not import provider SDKs or call providers directly.

There are two valid batch patterns:

1. **Large QRA/default DeepSeek work:** use `POST /v1/scillm/batch/completions` with `model_pool: "qra-deepseek-pool"`, a stable `batch_id`, and stable item ids. This is mandatory for `create-qras` and `create-evidence-case`.
2. **Other non-QRA workloads:** use bounded `asyncio.create_task` + `asyncio.as_completed(tasks)` with explicit concurrency limits.

**Default rule: all `/scillm` batch calls MUST use `asyncio.create_task` + `asyncio.as_completed(tasks)` unless the user explicitly asks for strict input-order completion.** Do not use `asyncio.gather` by default just because it is shorter. If ordered output is needed, collect `as_completed` results with each item’s `id`/`scillm_metadata`, then reorder after completion.

**Large QRA/default DeepSeek batches:** use the server-side pool endpoint `POST /v1/scillm/batch/completions` with `model_pool: "qra-deepseek-pool"` instead of hand-splitting Chutes/OpenCode Go yourself. This pool runs independent Chutes and OpenCode Go lanes concurrently and returns results in completion order.

**CRITICAL: Batch size limits.** The proxy queues requests internally (4-8 slots depending on provider). For batches of **50+ requests**, you MUST pace your HTTP calls — otherwise requests queue up, hit the 600s queue timeout, and fail before they ever reach the LLM.

**Batch Reliability (2026-04-15):**
- **Queue timeout:** 600s (10 min) — large batches drain rather than fail
- **Queue rejection:** Disabled — all requests queue indefinitely (no upfront 429s)
- **Abuse guard:** Disabled for authenticated callers — no cascade failures from transient errors
- **Error semantics:** 503 = queue exhaustion (proxy overloaded), 429 = upstream provider rate limit only
- **The only failure mode:** 503 after 600s queue wait = batch too large; use the server-side pool for QRA/default DeepSeek work or bounded `as_completed` for other workloads

| Batch size | Pattern | Why |
|------------|---------|-----|
| 1-10 | `create_task` + `as_completed` | Same simplicity, better failure/progress behavior |
| 10-50 | `Semaphore(8)` + `as_completed` | Prevents queue buildup while preserving arrival-order handling |
| 50+ | Server-side pool or chunked `as_completed` | REQUIRED — queue timeout will kill unbounded requests |

**WRONG** (fires 400 HTTP requests at once — most will timeout in queue):
```python
tasks = [call_proxy(p) for p in all_400_prompts]
results = await asyncio.gather(*tasks)  # DON'T DO THIS
```

**RIGHT** (processes results as they arrive):
```python
tasks = [asyncio.create_task(call_proxy(p)) for p in prompts]
for task in asyncio.as_completed(tasks):
    result = await task
    save(result["item_id"], result)
```

### Server-side DeepSeek pool (recommended for large QRA batches)

Use this when a batch has many independent QRA/extraction prompts and Chutes and
OpenCode Go quality are close enough that throughput matters more than a single
provider choice. Do **not** use it for model evals where every prompt must hit
every model; use `/llm-eval-lab` for that.

Pool contract:

| Pool | Strategy | Lanes |
|------|----------|-------|
| `qra-deepseek-pool` | weighted round-robin | Chutes `deepseek-ai/DeepSeek-V3.2-TEE` weight 3 + OpenCode Go `opencode-go/deepseek-v4-flash` weight 2 |

Before launching a large QRA/default DeepSeek batch, verify the pool uses a
currently callable Chutes model:

```bash
curl -s http://localhost:4001/v1/scillm/model-pools/qra-deepseek-pool/status \
  -H "Authorization: Bearer sk-dev-proxy-123" \
  -H "X-Caller-Skill: create-qras" | jq '.lanes[] | {provider, model, available}'
```

If the Chutes lane points at a retired DeepSeek model, the run is not allowed to
proceed. Update the pool to the current same-family DeepSeek model reported by
`ops-chutes models --query DeepSeek --modality text`, rebuild/restart scillm,
and re-check the pool status. Do not work around a stale Chutes lane by silently
running everything sequentially or by bypassing the server-side pool.

```python
import httpx

SCILLM = "http://localhost:4001"
HEADERS = {
    "Authorization": "Bearer sk-dev-proxy-123",
    "X-Caller-Skill": "create-qras",
}

items = [
    {"id": "cwe20-ex0002", "prompt": "Create QRAs for CWE-20 and EX-0002 ..."},
    {"id": "cwe287-ia0001", "prompt": "Create QRAs for CWE-287 and IA-0001 ..."},
]

with httpx.Client(timeout=900) as client:
    resp = client.post(
        f"{SCILLM}/v1/scillm/batch/completions",
        headers=HEADERS,
        json={
            "model_pool": "qra-deepseek-pool",
            "batch_id": "create-qras-20260425",
            "temperature": 0,
            "items": items,
        },
    )
    resp.raise_for_status()
    data = resp.json()

for result in data["results"]:  # completion order, not input order
    if result["ok"]:
        print(result["item_id"], result["provider"], result["model"], result["latency_s"])
        # result["content"] contains the assistant text
    else:
        print("FAILED", result["item_id"], result["model"], result["error"])
```

Response notes:

- Results are returned in `as_completed` order; use `item_id` to join back to inputs.
- Each inner call receives `scillm_metadata.batch_id`, `item_id`, `model_pool`, `lane`, `selected_model`, and `provider`.
- A `batch_id` is bound to one exact item-id set. If a caller intentionally submits client-side chunks, each chunk must use a stable child `batch_id` such as `<parent>-chunk-0004`; never reuse the parent `batch_id` for different subsets.
- Use `GET /v1/scillm/model-pools` to inspect available pools and lane weights.
- Use `GET /v1/scillm/model-pools/qra-deepseek-pool/status` for dashboard/live pool concurrency. It returns aggregate `in_flight`, `limit`, `queued`, `available`, and per-lane `registry_in_flight`, `semaphore_in_flight`, and `drift`.
- Do not infer pool health from raw `/v1/scillm/active-calls`; raw active calls are a debugging view only.
- OpenCode Go DeepSeek/MiniMax use an Anthropic-compatible `/messages` lane; `response_format` is translated into provider-boundary JSON instructions in the system prompt and final user turn because that endpoint does not enforce OpenAI `response_format` natively.
- Use this endpoint to raise throughput across providers; do not treat OpenCode Go as a Chutes fallback.

### Small batches (1-10): asyncio.as_completed

For small batches, fire all at once and process each result when it arrives:

```python
import asyncio, httpx

HEADERS = {
    "Authorization": "Bearer sk-dev-proxy-123",
    "X-Caller-Skill": "my-skill-name",  # REQUIRED
}

async def complete(client, prompt):
    resp = await client.post(
        "http://localhost:4001/v1/chat/completions",
        headers=HEADERS,
        json={
            "model": "chutes-deepseek",
            "messages": [{"role": "user", "content": prompt}],
        },
        timeout=45.0,
    )
    return resp.json()["choices"][0]["message"]["content"]

async def main():
    async with httpx.AsyncClient() as client:
        tasks = [
            asyncio.create_task(complete(client, "What is 2+2?")),
            asyncio.create_task(complete(client, "What is 3+3?")),
            asyncio.create_task(complete(client, "What is 4+4?")),
        ]
        results = []
        for task in asyncio.as_completed(tasks):
            results.append(await task)
    return results
```

### Medium batches (10-50): Semaphore

Limit in-flight requests to avoid queue buildup:

```python
import asyncio, httpx

HEADERS = {
    "Authorization": "Bearer sk-dev-proxy-123",
    "X-Caller-Skill": "my-skill-name",  # REQUIRED
}

async def complete(client, semaphore, prompt):
    async with semaphore:
        resp = await client.post(
            "http://localhost:4001/v1/chat/completions",
            headers=HEADERS,
            json={"model": "chutes-deepseek", "messages": [{"role": "user", "content": prompt}]},
            timeout=60.0,
        )
        return resp.json()["choices"][0]["message"]["content"]

async def main():
    semaphore = asyncio.Semaphore(8)  # Match provider slot count
    async with httpx.AsyncClient() as client:
        tasks = [
            asyncio.create_task(complete(client, semaphore, f"Prompt {i}"))
            for i in range(50)
        ]
        results = []
        for task in asyncio.as_completed(tasks):
            results.append(await task)
    return results
```

### Large batches (50+): server-side pool or chunked as_completed

For QRA/default DeepSeek work, use `POST /v1/scillm/batch/completions` with
`model_pool: "qra-deepseek-pool"`, a stable `batch_id`, and stable item ids.
For other workloads, process bounded windows with `as_completed`:

```python
import asyncio, httpx

CHUNK_SIZE = 8  # Check `/v1/scillm/concurrency` or pool status for current capacity

async def complete(client, prompt):
    resp = await client.post(
        "http://localhost:4001/v1/chat/completions",
        headers={
            "Authorization": "Bearer sk-dev-proxy-123",
            "X-Caller-Skill": "my-skill-name",
        },
        json={"model": "chutes-deepseek", "messages": [{"role": "user", "content": prompt}]},
        timeout=120.0,  # Generous timeout per request
    )
    return resp.json()["choices"][0]["message"]["content"]

async def main(prompts: list[str]):
    all_results = []
    async with httpx.AsyncClient() as client:
        for chunk_start in range(0, len(prompts), CHUNK_SIZE):
            chunk = prompts[chunk_start:chunk_start + CHUNK_SIZE]
            print(f"Processing chunk {chunk_start // CHUNK_SIZE + 1}...")
            tasks = [asyncio.create_task(complete(client, p)) for p in chunk]
            chunk_results = []
            for task in asyncio.as_completed(tasks):
                chunk_results.append(await task)
            all_results.extend(chunk_results)
    return all_results

# 400 prompts processed 4 at a time — no queue timeout issues
asyncio.run(main([f"Prompt {i}" for i in range(400)]))
```

**Why chunking is required:** Firing 400 requests at once puts 396 in the proxy queue. The queue has a 300s timeout. By the time slot #200 opens up, the request has already timed out. Chunking ensures each request gets a slot immediately.

For image/VLM tasks, use `model: "vlm"` or just include image content — auto-detected and routed:

```python
# Local file paths — auto base64-encoded, auto-routed to VLM
requests = [
    {"messages": "Describe this image", "file_path": "/path/to/photo.png"},
    {"messages": "What's in this diagram?", "paths": ["fig1.jpg", "fig2.png"]},
]

# URLs — auto-detected as image content
requests = [
    {"messages": "Describe this image", "url": "https://example.com/photo.jpg"},
]

# OpenAI-style image_url parts also work (for full control)
requests = [
    {"messages": [{"role": "user", "content": [
        {"type": "text", "text": "Describe this image"},
        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}},
    ]}]}
]
```

Each yielded `result`:

| Field | What it is |
|-------|-----------|
| `index` | Position in original list (for ordering) |
| `request` | Your original request dict, including any metadata you attached |
| `ok` | Success boolean |
| `response` / `error` | The OpenAI response or error message |
| `attempts` | Retry count |
| `elapsed_s` | Wall-clock time |

## Source Grounding Verification

Pass a `source` field and scillm verifies the response is grounded using fuzzy token matching.
If the response doesn't meet the threshold, scillm retries with progressive prompts:

```python
from scillm.batch import parallel_acompletions

requests = [
    {
        "messages": "Summarize AC-17 requirements",
        "source": "findings/ac17_control.txt",  # file path or inline text
        "grounding_threshold": 0.7,              # default 0.7
        "grounding_retries": 2,                  # default 2
    }
]

results = await parallel_acompletions(requests, source="global_source.txt")
# result["grounding_score"] → 0.85
# result["grounding_attempts"] → 1
```

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `source` | `str \| list[str]` | None | File path(s) or inline text. Per-request overrides batch-level. |
| `grounding_threshold` | `float` | 0.7 | Minimum fuzzy match score (0.0-1.0) to accept. |
| `grounding_retries` | `int` | 2 | Max retry attempts with progressive grounding prompts. |

Progressive retry strategy:
1. **Try 1:** Normal completion
2. **Try 2:** Appends "Base your answer strictly on the provided source text."
3. **Try 3:** Appends "Base your answer strictly on the provided source text. Quote directly from the source."

Results carry `grounding_score` (float) and `grounding_attempts` (int). Uses `rapidfuzz.fuzz.token_set_ratio` (~1ms per check).

## Hedged Calls (Race Two Models)

Client-side — fire two models, take the first response:

```python
async def hedged_call(client, prompt, primary="chutes-deepseek", backup="oc-deepseek"):
    async def call(model):
        resp = await client.post(
            "http://localhost:4001/v1/chat/completions",
            headers={
                "Authorization": "Bearer sk-dev-proxy-123",
                "X-Caller-Skill": "my-skill-name",
            },
            json={"model": model, "messages": [{"role": "user", "content": prompt}]},
            timeout=30.0,
        )
        return resp.json()["choices"][0]["message"]["content"]

    done, pending = await asyncio.wait(
        [asyncio.create_task(call(primary)), asyncio.create_task(call(backup))],
        return_when=asyncio.FIRST_COMPLETED,
    )
    for t in pending:
        t.cancel()
    return await next(iter(done))
```

---

## Sending Multiple Files / Documents

Two approaches depending on file types and target provider.

### Option A: Concatenated Text (all providers)

Extract text client-side and concatenate into one prompt. Choose the intended
model family explicitly:

```python
texts = []
for path in file_paths:
    texts.append(f"=== {path.name} ===\n{path.read_text()}")
combined = "\n\n".join(texts)

resp = httpx.post(
    "http://localhost:4001/v1/chat/completions",
    headers={
        "Authorization": "Bearer sk-dev-proxy-123",
        "X-Caller-Skill": "my-skill-name",
    },
    json={
        "model": "chutes-deepseek",
        "messages": [{"role": "user", "content": f"{combined}\n\nYour question here"}],
    },
    timeout=120.0,
)
```

Gemini Flash has 1M context — 26 documents as plain text will fit unless they're each book-length.

### Option B: Binary files via inlineData (Gemini only)

Send PDFs, images, audio, and video directly to Gemini without client-side extraction. The proxy auto-detects `inlineData` parts and calls Gemini's native API instead of the OpenAI-compat layer. Gemini reads the binary format itself.

```python
import base64, httpx

with open("document.pdf", "rb") as f:
    pdf_b64 = base64.b64encode(f.read()).decode()

resp = httpx.post(
    "http://localhost:4001/v1/chat/completions",
    headers={
        "Authorization": "Bearer sk-dev-proxy-123",
        "X-Caller-Skill": "my-skill-name",
    },
    json={
        "model": "gemini-flash",  # MUST target Gemini directly
        "messages": [{"role": "user", "content": [
            {"type": "text", "text": "Summarize this document"},
            {"inlineData": {"mimeType": "application/pdf", "data": pdf_b64}},
        ]}],
    },
    timeout=120.0,
)
```

Multiple files — just add more `inlineData` parts:

```python
parts = [{"type": "text", "text": "Compare these documents"}]
for path in pdf_paths:
    with open(path, "rb") as f:
        parts.append({"inlineData": {
            "mimeType": "application/pdf",
            "data": base64.b64encode(f.read()).decode(),
        }})

resp = httpx.post(
    "http://localhost:4001/v1/chat/completions",
    headers={
        "Authorization": "Bearer sk-dev-proxy-123",
        "X-Caller-Skill": "my-skill-name",
    },
    json={
        "model": "gemini-flash",
        "messages": [{"role": "user", "content": parts}],
    },
    timeout=120.0,
)
```

**Supported MIME types** (Gemini native): `application/pdf`, `image/png`, `image/jpeg`, `image/webp`, `image/gif`, `audio/*`, `video/*`, `text/plain`, `text/csv`, `text/html`.

**ZIP files**: Supported! The proxy auto-explodes ZIP archives — unpacks each file and sends it as its own part (text files as text, images/PDFs as `inlineData`). Just send `mimeType: "application/zip"` and the proxy handles the rest. Tested: 64KB ZIP with 8 files (code, markdown, PNG) → 2.78s, 14K tokens.

**WARNING**: `inlineData` only works with `model: "gemini-flash"` or `"gemini-flash-high"` (direct). Using `model: "text"` will fail on Chutes/DeepSeek before reaching Gemini. The proxy only switches to the native Gemini API when the deployment targets `generativelanguage.googleapis.com`.

**`gemini-flash-high`** (Gemini 3 Flash Preview) is a thinking model — better for complex analysis of PDFs/images but uses internal reasoning tokens. Do NOT set `max_tokens` — reasoning models consume tokens internally and a low limit produces empty output.

### Option C: Images via image_url (VLM providers)

For images (not PDFs), use the OpenAI-compat `image_url` format. Prefer
`model: "vlm"` for general image descriptions because it is the configured image
cascade. If Gemini quota limits matter and a Chutes VLM lane is configured, use
`model: "vlm-chutes"` only after a smoke test confirms the configured Chutes
model exists:

```python
with open("screenshot.png", "rb") as f:
    img_b64 = base64.b64encode(f.read()).decode()

resp = httpx.post(url, json={
    "model": "vlm-chutes",  # bulk/high-throughput VLM; verify this lane first
    "messages": [{"role": "user", "content": [
        {"type": "text", "text": "Describe this screenshot"},
        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{img_b64}"}},
    ]}],
}, headers=headers, timeout=120)
```

For high-reasoning image analysis, use `gpt-5.5` directly through `/scillm`:

```python
resp = httpx.post(url, json={
    "model": "gpt-5.5",
    "reasoning_effort": "high",
    "messages": "Analyze the attached image. Describe what matters and identify any issues.",
    "file_path": "/absolute/path/to/screenshot.png",
}, headers=headers, timeout=120)
```

### Option D: PDFs via Claude OAuth

Claude reads PDF binaries natively. Two formats work through scillm:

```python
# Format 1: data URI via image_url (same as Gemini, auto-converted)
{"type": "image_url", "image_url": {"url": f"data:application/pdf;base64,{pdf_b64}"}}

# Format 2: Anthropic-native document block (passed through directly)
{"type": "document", "source": {"type": "base64", "media_type": "application/pdf", "data": pdf_b64}}
```

Both work with any `claude-*` model. The VLM cascade now handles PDFs on the Claude fallback path.

### Decision Table

| Situation | Format | Model | Cascade? |
|-----------|--------|-------|----------|
| Text files, any provider | Concatenated text | `text` | YES (full) |
| Images only, need cascade | `image_url` base64 | `vlm` | YES → Claude → Codex |
| PDFs, Gemini | `inlineData` parts | `gemini-flash` or `gemini-flash-high` | Gemini free → paid |
| PDFs, Claude | `image_url` data URI or `document` block | `claude-sonnet-4-6` | Claude direct |
| PDFs, full cascade | `image_url` data:application/pdf | `vlm` | YES → Gemini → Claude |
| PDFs + images, Gemini | `inlineData` per file | `gemini-flash` or `gemini-flash-high` | Gemini free → paid |
| Mixed PDF+images, Claude | `image_url` for both | `claude-sonnet-4-6` | Claude direct |

---

## Ollama Auto-Routing

Any locally-pulled Ollama model works through the proxy without a config entry. Just use the Ollama model:tag name directly:

```python
resp = httpx.post(
    "http://localhost:4001/v1/chat/completions",
    headers={
        "Authorization": "Bearer sk-dev-proxy-123",
        "X-Caller-Skill": "my-skill-name",
    },
    json={"model": "qwen2.5:7b", "messages": [{"role": "user", "content": "hi"}]},
)
```

The proxy auto-detects unknown model names and routes them to the local Ollama instance. `response_format` is automatically stripped for Ollama models (Ollama doesn't support it).

Available Ollama models: anything you've pulled with `ollama pull`. Check with `ollama list`.

---

## Claude OAuth (Anthropic Max Subscription)

Call Claude models through the proxy using your Max subscription — no API key needed.

### Profile and Direct Model Names

| Use this | Maps to | Notes |
|----------|---------|-------|
| `claude-sonnet` | claude-sonnet-4-20250514 | Default Sonnet profile |
| `claude-sonnet-high` | claude-sonnet-4-20250514 + high reasoning | Sonnet reasoning profile |
| `claude-opus` | claude-opus-4-20250514 | Default Opus profile |
| `claude-opus-high` | claude-opus-4-20250514 + high reasoning | Opus reasoning profile |
| `claude-haiku` | claude-haiku-4-5-20251001 | Fast Claude profile |

Profile names and direct Anthropic IDs both start with `claude-`. Names like `anthropic-sonnet` or `sonnet-4-6` will not route to Claude.

### Copy-paste example

```python
import httpx

resp = httpx.post(
    "http://localhost:4001/v1/chat/completions",
    headers={
        "Authorization": "Bearer sk-dev-proxy-123",
        "X-Caller-Skill": "my-skill-name",
        "Content-Type": "application/json",
    },
    json={
        "model": "claude-sonnet-4-20250514",   # exact Anthropic API snapshot ID
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
    "model": "chutes-deepseek",
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

### Automatic Batch Resume

For large batches that might fail mid-way, use `batch_id` + `item_id` in `scillm_metadata`. The proxy automatically skips already-completed items on retry:

```python
# Skill submits batch with unique item identifiers
requests = [
    {
        "model": "chutes-deepseek",
        "messages": [{"role": "user", "content": f"Process {cwe_id}"}],
        "scillm_metadata": {
            "batch_id": "cwe-qra-batch-2026-04-13",  # unique per batch run
            "item_id": cwe_id,                        # unique per work item
        },
    }
    for cwe_id in all_cwe_ids
]

# If batch fails at 500/1000, re-run entire batch — proxy auto-skips completed items
# Response header x-batch-resumed: true indicates a cached hit
```

**How it works:**
1. Every completion is logged to ArangoDB `llm_call_log` with the metadata
2. On subsequent calls, proxy queries for existing success with same `(batch_id, item_id)`
3. If found: returns cached response instantly (no LLM call), sets `x-batch-resumed: true` header
4. If not found: normal LLM call, logged for future resume

**Progress contract:** skills must use stable `batch_id` + `item_id` and monitor `GET /v1/scillm/batches/{batch_id}` or the dashboard’s canonical batch state. A `batch_id` may only be retried with the same item ids; if the caller chunks work, use a new stable child `batch_id` per chunk. Do not infer batch progress from raw active calls.

### Skill Identification (x-caller-skill header)

Skills should identify themselves for debugging and analytics:

```python
resp = await client.post(url, json=body, headers={
    "Authorization": "Bearer sk-dev-proxy-123",
    "x-caller-skill": "create-qras",  # your skill name
})
```

The header is logged to `llm_call_log.caller` for per-skill usage tracking and error correlation.

### Common mistakes that cause 500s

1. **Wrong model name**: `sonnet-4-6` → use `claude-sonnet` or a direct Anthropic ID such as `claude-sonnet-4-20250514`
2. **Setting `max_tokens` too low**: reasoning models consume tokens internally — a low `max_tokens` means zero output. Omit it and let the proxy default.
3. **Sending `response_format: {"type": "json_object"}`**: Claude rejects this — instead say "Return valid JSON" in the prompt
4. **Timeout too short**: Claude can take 10-30s for complex prompts — use `timeout=60.0`

### Auth (automatic — no setup needed)

The proxy reads OAuth tokens from `~/.claude/.credentials.json` (managed by Claude Code) and falls back to `~/.pi/agent/auth.json` (Pi CLI). OAuth can be configured but expired/invalid; project agents must check `/v1/scillm/auth` and read provider-auth log fields before blaming routing.

### Verify OAuth before calling

Claude provider-auth failures are logged with `error_type`, `error_status_code`, `provider_auth_status`, and `project_agent_message` in Arango/JSONL. If `/v1/scillm/auth` reports `expired`, run `claude auth login --claudeai` on the host, complete the browser flow, and restart scillm only if the mounted credential file did not update.


Check token health before making calls — avoids 500 errors from expired tokens:

```python
auth = httpx.get(
    "http://localhost:4001/v1/scillm/auth",
    headers={
        "Authorization": "Bearer sk-dev-proxy-123",
        "X-Caller-Skill": "my-skill-name",
    },
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
    headers={
        "Authorization": "Bearer sk-dev-proxy-123",
        "X-Caller-Skill": "my-skill-name",
    },
    json={
        "model": "gpt-5.5",
        "messages": [{"role": "user", "content": "Explain quicksort"}],
    },
    timeout=120.0,
)
```

**Supported models:** `gpt-5.5`, `gpt-5.2-codex`, `gpt-5.3-codex`. `gpt-5.5`
accepts OpenAI-compatible `image_url` content parts and top-level image
convenience fields (`file_path`, `path`, `paths`, `url`, `urls`) through
`/scillm`; use it directly for high-reasoning image calls. PDF input is not
supported on the Codex OAuth route; use Gemini or Claude for PDFs. Other
platform GPT models (for example `gpt-4o`) are NOT supported via ChatGPT OAuth —
they require a platform API key.

**Streaming:** Both Claude and Codex support `"stream": true`. The proxy translates provider-specific SSE events into OpenAI-compatible delta chunks (`data: {"choices":[{"delta":{"content":"..."}}]}`). Works with any SSE client including `httpx.stream()` and the OpenAI SDK.

For long grounded/reasoning calls, prefer streaming instead of one blocking HTTP response. Use:
- `timeout`: overall wall-clock budget, e.g. 300–600s.
- `stream_heartbeat_s`: heartbeat cadence for idle liveness, default 15s.
- Short client connect timeout, but no arbitrary 15s read cap.

The proxy keeps SSE connections live with heartbeat comments while providers are silent and fails only when the overall budget expires. If a caller needs named progress events for artifact writers, pass `stream_progress_events: true`; normal token chunks remain OpenAI-compatible `data:` chunks.

Operationally, SSE is the liveness mechanism and `timeout` is the hard wall-clock budget. scillm keeps `/v1/scillm/active-calls` rows open until the stream finishes or fails, and active-call plus Arango/JSONL records include `stream_heartbeat_s`, `stream_progress_events`, `deadline_timeout_s`, `dynamic_timeout_s`, and `timeout_source`. If an agent reports a stale Kimi, Claude, or Codex run, inspect those fields before blaming provider routing.

**Note:** `max_tokens` is ignored for Codex (the ChatGPT backend doesn't support it).

**Credential priority:** `~/.codex/auth.json` (Codex CLI) > `~/.pi/agent/auth.json` (Pi CLI).

---

## Middleware Stack

The proxy runs these middleware components on every request:

| Middleware | File | Purpose |
|-----------|------|---------|
| **Timeout Estimator** | `timeout_estimator.py` | Estimates dynamic timeout from historical latency (p95 from `/latency-stats`). Sets provider timeout per-call. |
| **JSON Guard** | `json_guard.py` | Validates JSON when `response_format.type == "json_object"`. Attempts repair (brace trim + json_repair lib) before rejecting. Failed validation triggers cascade to next provider. |
| **Concurrency Guard** | `concurrency_guard.py` | Per-provider semaphore (chutes=4, ollama=1, etc). Queues excess requests instead of 429. Prevents Chutes 90s penalty. |
| **VLM Auto-Router** | `vlm_router.py` | Detects `image_url` parts in messages, rewrites text model to `vlm`. Callers don't need to know model names. |
| **Cache Init** | `cache_init.py` | Auto-detects Redis at startup (via REDIS_HOST/REDIS_URL). Enables caching if available, no-op otherwise. |
| **Budget Guard** | `budget_guard.py` | Tracks Chutes daily usage. Classifies 429s as budget vs throttle. |
| **Pricing** | `pricing.py` | Per-1k token cost estimation. |
| **Metrics** | `metrics.py` | Prometheus counters: calls, 429s, budget limits, retries. |
| **ArangoDB Log** | `arango_log.py` | Logs every LLM call to `llm_call_log` collection. Stores request prompt, response content, tokens, cost, latency. |

## Fallback Cascade

When a provider fails on the ordinary chat route, the proxy cascades to the next
group:

```
text:          Chutes V3.2-TEE → V3.1-TEE → R1-0528-TEE → Kimi → Qwen3 → Qwen3.5
gemini-flash: Gemini free → Gemini free2 → Gemini paid
vlm:           Gemini free → Gemini paid → Claude OAuth → Codex OAuth
gemini-flash-high: Gemini 3 free → Gemini 3 free2 → Gemini 3 paid
```

**Important:** this fallback table is not the QRA model-pool contract. Server-side
model pools use explicit provider lanes for throughput. For QRA repair, inspect
`/v1/scillm/model-pools/qra-deepseek-pool/status`; do not infer pool safety from
the `text` fallback chain.

**Same-family fallback for chat routing**: DeepSeek comes before Gemini so a
cold Chutes model cascades to warm DeepSeek on the ordinary chat route before
falling back to a different model family.

**Gemini free/paid are separate groups** — 429 on free cascades immediately to paid (no wasted retries on an exhausted key).

**Cold model fast-fail**: When Chutes returns 503 "No instances available" (cold model), the proxy **skips all retries** and cascades immediately to the fallback chain. No point retrying — miners need minutes to spin up. The warmup API fires in background to notify miners for next time.

**Detecting fallback**: The response `model` field shows which model actually served the request. Compare to what you requested — if different, a fallback occurred.

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

Multi-model groups (non-TEE + TEE in same group) use 1 retry per deployment for
fast fallthrough. Broad cross-family cascades are for ad hoc resiliency, not
production prompt contracts.

## Caching

Redis caching is auto-enabled when `REDIS_HOST` or `REDIS_URL` is set:
- Deploy with `compose.scillm.stack.yml` (includes Redis)
- TTL: `SCILLM_CACHE_TTL_SEC` (default 3600s)
- Namespace: `SCILLM_CACHE_NAMESPACE` (default "scillm")
- Core compose (no Redis) works fine — caching is optional

## Logging (ArangoDB)

All LLM calls are logged to the `llm_call_log` collection in ArangoDB (via memory service):

| Field | Type | Description |
|-------|------|-------------|
| `ts` | ISO8601 | Timestamp |
| `date` | YYYY-MM-DD | Date partition key |
| `model_requested` | string | What caller asked for (e.g., `text`) |
| `model_served` | string | What actually served (e.g., `deepseek-ai/DeepSeek-V3.2-TEE`) |
| `provider` | string | Inferred provider (chutes, gemini, anthropic, etc.) |
| `duration_ms` | int | Total call time |
| `prompt_tokens` | int | Input tokens |
| `completion_tokens` | int | Output tokens |
| `cost_usd` | float | Estimated cost (from x-cost-usd header) |
| `status` | string | `ok` or `error` |
| `error` | string | Error type if failed |
| `request_prompt` | string | Last user message (truncated to 4000 chars) |
| `response_content` | string | Raw response content for debugging |
| `caller` | string | x-caller-skill header value |
| `reasoning_effort_requested` | string | Caller-requested `reasoning_effort`, if any |
| `reasoning_effort_applied` | string | Provider-applied/mapped effort, if forwarded |
| `reasoning_forwarded` | bool | Whether scillm sent a provider-native reasoning field |
| `reasoning_provider_field` | string | Provider-native field path, e.g. `reasoning.effort` |
| `reasoning_ignored_reason` | string | Why reasoning was not forwarded, if applicable |

**No Redis for logging.** Redis is ONLY for optional caching. All persistent logging goes to ArangoDB.

**JSONL Backup** — every call is also appended to `/mnt/storage12tb/scillm-logs/` (or `$SCILLM_LOG_BACKUP_DIR`):
- **Independent of ArangoDB** — survives database wipes
- **Append-only** — daily files, monthly directories (`YYYY-MM/calls-YYYY-MM-DD.jsonl`)
- **Same fields as ArangoDB** — can rebuild `llm_call_log` collection from JSONL if needed

Query logs via memory service:
```bash
curl -X POST http://localhost:8601/query -H "Content-Type: application/json" -d '{
  "aql": "FOR doc IN llm_call_log FILTER doc.date == \"2026-04-13\" SORT doc.ts DESC LIMIT 10 RETURN doc"
}'
```

## Automatic Timeout Estimation

**Agents don't need to estimate timeouts.** scillm automatically sets per-call provider timeouts based on historical latency data.

How it works:
1. Middleware queries `/latency-stats` (memory service) for p95 latency and throughput
2. Estimates timeout based on model, provider, and token count
3. Sets internal provider timeout (clients use generous 5-min HTTP timeout)
4. Returns timeout info in response headers

**Response headers** (always present):

| Header | Value | Example |
|--------|-------|---------|
| `x-scillm-timeout-ms` | Timeout used for provider call (ms) | `45000` |
| `x-scillm-timeout-source` | How timeout was determined | `p95`, `estimated`, `default` |
| `x-scillm-timeout-samples` | Historical samples used (if available) | `127` |

**Timeout sources:**
- `estimated` — Token-aware calculation: `(prompt_tokens + completion_tokens) / throughput_tps * 1.2`
- `p95` — 95th percentile from historical calls for this model/provider
- `default` — No historical data; using 120s fallback

**Bounds:** 10s minimum, 10min maximum. Clamped automatically.

**Data source:** `/latency-stats` in memory service queries `llm_call_log` for duration, tokens, and throughput. Stats cached 5 minutes.

---

## Self-Correction

scillm is designed to self-correct common issues so agents don't need to be scillm experts:

| Issue | Self-Correction |
|-------|-----------------|
| Deprecated model names (e.g. `deepseek-ai/DeepSeek-V3`) | Rejected or remapped with an actionable replacement; production callers should update to a current family profile or exact model |
| Provider rate limits (429) | Handled via fallback chain — not counted against client |
| JSON fence wrapping (```json...```) | Auto-stripped when `response_format: {"type": "json_object"}` set |
| Malformed JSON | Auto-repaired via json_repair lib before rejection |

**Agents should call the proxy with the intended family profile, exact model ID,
or explicit model pool.** Use `text`/`vlm` only for smoke tests, ad hoc
exploration, or low-stakes utilities where cross-family variability is
acceptable.

---

## Troubleshooting

**BEFORE calling scillm, check if the proxy is running:**

```python
import httpx

def check_proxy() -> bool:
    """Returns True if scillm proxy is up."""
    try:
        resp = httpx.get("http://localhost:4001/health", timeout=2.0)
        return resp.status_code == 200
    except httpx.ConnectError:
        return False

if not check_proxy():
    raise RuntimeError(
        "scillm proxy not running. Start it with: "
        "docker compose -p scillm -f deploy/docker/compose.scillm.core.yml up -d"
    )
```

### Common Errors and Fixes

| Error | Cause | Fix |
|-------|-------|-----|
| `Connection refused` | Proxy not running | `docker compose -p scillm ... up -d` |
| `404 /health` | Wrong endpoint | Use `/health` (no auth) or `/v1/scillm/health` (with auth and `X-Caller-Skill`) |
| `BATCH MISUSE: N requests queued` | Firing 100+ requests at once | Use server-side pool for QRA/default DeepSeek work; otherwise bounded `as_completed` |
| `503 SERVICE_BUSY` | Queue timeout after 600s | Batch too large for capacity. Use pool status/concurrency to reduce the window. |
| `429 Rate limit` | Upstream provider exhausted | For production work, stay on the intended family profile or explicit pool and inspect provider/pool status before changing models. |
| `Unknown model 'foo'` | Model name not in config | Use a current family profile, exact model ID, explicit pool, or check `/v1/scillm/models` |
| `401 Unauthorized` | Missing/wrong auth header | Use `Bearer sk-dev-proxy-123` |
| `JSON validation failed` | Provider returned prose | Already auto-repaired; if persistent, prompt needs "Return valid JSON" |
| `Empty response` | max_tokens set too low | Remove max_tokens (auto-stripped, but don't set it) |
| `Stored 0/N` with no errors | Schema mismatch in response parsing | Check field names match LLM output (e.g., `reason` vs `abstain_reason`). Query `llm_call_log` for raw `response_content`. |
| `Silent batch failure` | 0% success but no actionable error | FORBIDDEN. Batch code must log first failure with expected vs actual schema. |
| `Missing x-caller-skill header` | Can't identify which skill made the call | Add `"x-caller-skill": "your-skill-name"` header. Without it, only `user_agent` is logged as fallback. |
| `Manual batch progress tracking` | Skill tracks completed items itself | WRONG. Use `scillm_metadata: {"batch_id": X, "item_id": Y}` — scillm auto-resumes on retry. |
| `Re-running entire batch from scratch` | Batch failed, skill starts over | Use batch_id + item_id. scillm skips completed items automatically (x-batch-resumed header). |
| `Deprecated model 'X' requested` | Using deprecated model name | Update to a current family profile, exact model ID, or explicit pool. Do not hide this behind `text` unless it is only a smoke/ad hoc call. |
| `abuse_guard: blocking key` | 5+ client errors (400/401/422) in 30s | Fix the underlying error (bad model, auth issue). Note: 429 rate limits don't trigger blocking. |

### Preflight Check (scripts)

Add this at the top of any script that makes LLM calls:

```python
import sys
import httpx

def scillm_preflight():
    """Check scillm proxy health before making calls."""
    try:
        resp = httpx.get(
            "http://localhost:4001/v1/scillm/health",
            headers={
                "Authorization": "Bearer sk-dev-proxy-123",
                "X-Caller-Skill": "my-skill-name",
            },
            timeout=5.0,
        )
        if resp.status_code != 200:
            print(f"scillm proxy unhealthy: {resp.status_code}", file=sys.stderr)
            sys.exit(1)
        health = resp.json()
        if health.get("status") != "ok":
            print(f"scillm proxy status: {health.get('status')}", file=sys.stderr)
            sys.exit(1)
    except httpx.ConnectError:
        print(
            "scillm proxy not running. Start with:\n"
            "  docker compose -p scillm -f deploy/docker/compose.scillm.core.yml up -d",
            file=sys.stderr,
        )
        sys.exit(1)

scillm_preflight()  # Fails fast if proxy is down
```

---

## Skill Commands

```bash
# Check external code for correct scillm usage patterns
./run.sh assess /path/to/script.py          # Human-readable
./run.sh assess /path/to/script.py --json   # JSON for automation

# Check if configured Chutes DeepSeek model is hot (warm variant discovery)
./run.sh warm-check                          # Check configured Chutes DeepSeek model
./run.sh warm-check <model_id>               # Check specific model
./run.sh warm-check --json                   # JSON output
```

**assess** detects common misuse patterns:
- `max_tokens` (FORBIDDEN — causes empty/truncated output)
- Fire-all-at-once batching (>4 requests via `asyncio.gather` causes timeout)
- Generic `text` usage in production-shaped code and retired/confusing model names
- Missing family-specific profile, exact model ID, or explicit model pool for repeatable prompt/code workflows
- Direct provider URLs (bypasses proxy cascade and caching)
- Missing `response_format` for JSON output
- **Silent batch failures** (0% success rate without actionable error messages)
- **Schema mismatch** (checking wrong field names in LLM responses, e.g., `reason` vs `abstain_reason`)
- **No response logging** (batch operations must log raw responses for post-mortem debugging)
- **Redis for logging** (WRONG — use ArangoDB via arango_log.py, Redis is caching only)

**warm-check** queries `/ops-chutes recommend` to find hot model variants. Use before batch operations to avoid cold model timeouts.

---

## Ops Endpoints

| Endpoint | Method | Purpose |
|---|---|---|
| `/health` | GET | Is the proxy alive? |
| `/v1/scillm/health` | GET | Router health + fallback config + concurrency status |
| `/v1/scillm/concurrency` | GET | **Dynamic batch sizing** — get optimal chunk_size for a model |
| `/v1/scillm/model-pools` | GET | Server-side pool definitions plus live lane status |
| `/v1/scillm/model-pools/{pool}/status` | GET | Dashboard contract for aggregate/per-lane pool concurrency |
| `/v1/scillm/batches/{batch_id}` | GET | Canonical durable server-side batch status and item records |
| `/v1/scillm/batches/doctor?quarantine=true` | GET | Detect and quarantine corrupt/impossible durable batch records |
| `/v1/scillm/active-calls` | GET | Raw active calls for debugging; not pool source of truth |
| `/v1/scillm/active-calls/purge` | POST | Purge stale in-memory active-call rows |
| `/v1/scillm/models` | GET | Model groups, deployments, aliases, and per-name capabilities |
| `/v1/scillm/providers` | GET | **All available providers, auto-routing patterns, and examples** |
| `/v1/scillm/auth` | GET | **OAuth token health** — Claude/Codex token status, expiry, subscription tier |
| `/v1/models` | GET | OpenAI-compatible model list (includes auto-routable models) |
| `/v1/budget` | GET | Current daily spend and remaining budget |
| `/metrics` | GET | Prometheus counters (requests, errors, latency by group) |

```bash
curl http://localhost:4001/v1/scillm/health -H "Authorization: Bearer sk-dev-proxy-123" -H "X-Caller-Skill: my-skill-name"
curl http://localhost:4001/v1/scillm/models -H "Authorization: Bearer sk-dev-proxy-123" -H "X-Caller-Skill: my-skill-name"
curl http://localhost:4001/v1/budget -H "Authorization: Bearer sk-dev-proxy-123" -H "X-Caller-Skill: my-skill-name"
curl http://localhost:4001/metrics
```

### Dynamic Concurrency for Batch Sizing

Query `/v1/scillm/concurrency?model=<model>` to get the optimal `chunk_size` for batch processing.
The endpoint returns the **effective limit** — accounting for adaptive backoff when 429s occur.

```bash
curl "http://localhost:4001/v1/scillm/concurrency?model=chutes-deepseek" -H "Authorization: Bearer sk-dev-proxy-123" -H "X-Caller-Skill: my-skill-name"
```

Response:
```json
{
  "model": "chutes-deepseek",
  "provider": "chutes",
  "chunk_size": 4,
  "configured_limit": 4,
  "effective_limit": 4,
  "in_flight": 0,
  "available": 4,
  "backoff_active": false
}
```

**Use `chunk_size` for batch processing:**

```python
import httpx

def get_chunk_size(model: str = "chutes-deepseek") -> int:
    """Query proxy for optimal batch chunk size."""
    try:
        resp = httpx.get(
            f"http://localhost:4001/v1/scillm/concurrency?model={model}",
            headers={
                "Authorization": "Bearer sk-dev-proxy-123",
                "X-Caller-Skill": "my-skill-name",
            },
            timeout=5.0,
        )
        if resp.status_code == 200:
            return resp.json().get("chunk_size", 4)
    except Exception:
        pass
    return 4  # Default fallback

# Use in batch processing
chunk_size = get_chunk_size("chutes-deepseek")
for i in range(0, len(prompts), chunk_size):
    chunk = prompts[i:i + chunk_size]
    tasks = [asyncio.create_task(call_proxy(p)) for p in chunk]
    for task in asyncio.as_completed(tasks):
        result = await task
        save(result)
```

**Key fields:**
- `chunk_size` — Use this for batch sizing (equals effective_limit)
- `effective_limit` — May be lower than configured if 429 backoff is active
- `backoff_active` — True if the proxy reduced concurrency due to rate limits
- `available` — Slots currently free (effective_limit - in_flight)

---

## Composable Skills

scillm integrates with these skills via the proxy endpoint:

| Skill | Integration | Example |
|-------|-------------|---------|
| `/create-evidence-case` | LLM completions for claim generation | Evidence case authoring |
| `/analytics` | LLM completions for data analysis | Statistical analysis |
| `/create-figure` | LLM completions for chart descriptions | Publication figures |
| `/task-monitor` | Health endpoint monitoring | Progress tracking |
| `/lean4-prove` | Separate skill with own bridge | Formal theorem proving (not via scillm proxy) |

Composable skills call scillm HTTP endpoints — no direct provider access, no SDK
imports, no API keys needed beyond the proxy master key.

- Single calls: `POST http://localhost:4001/v1/chat/completions`
- Large QRA/default DeepSeek batches: `POST http://localhost:4001/v1/scillm/batch/completions` with `model_pool: "qra-deepseek-pool"`

## Common Mistakes

### WRONG: Calling without Authorization header
```bash
curl http://localhost:4001/v1/chat/completions \
  -d '{"model": "chutes-deepseek", "messages": [...]}'
# → 401 Unauthorized: Missing Bearer token
```

### RIGHT: Always include Bearer token
```bash
curl http://localhost:4001/v1/chat/completions \
  -H "Authorization: Bearer sk-dev-proxy-123" \
  -H "X-Caller-Skill: my-skill" \
  -d '{"model": "chutes-deepseek", "messages": [...]}'
```

### WRONG: Checking wrong health endpoint
```bash
curl http://localhost:4001/v1/scillm/health  # requires auth
# → 401 Unauthorized
```

### RIGHT: Use /health for quick liveness check (no auth)
```bash
curl http://localhost:4001/health
# → {"status": "ok", "uptime_seconds": 123.4}
```

### WRONG: Using OAuth models (Claude/Codex) in batch operations
```python
# Risk of account ban from automated high-volume requests
for prompt in 1000_prompts:
    call_proxy(model="claude-sonnet", ...)  # DON'T
```

### RIGHT: Stay inside an intended model family for batch work
```python
for prompt in 1000_prompts:
    call_proxy(model="chutes-deepseek", ...)  # Stays in Chutes DeepSeek family
```

### WRONG: Firing 400+ requests at once (queue timeout)
```python
results = await asyncio.gather(*[call_proxy(p) for p in all_400])  # DON'T
```

### RIGHT: Use the server-side pool for large QRA/default DeepSeek batches
```python
resp = await client.post(
    "http://localhost:4001/v1/scillm/batch/completions",
    headers=headers,
    json={
        "model_pool": "qra-deepseek-pool",
        "batch_id": batch_id,
        "items": [{"id": item_id, "prompt": prompt} for item_id, prompt in prompts],
    },
)
```

### RIGHT: Or chunk non-QRA batches with as_completed
```python
for chunk in chunks(prompts, 4):
    tasks = [asyncio.create_task(call_proxy(p)) for p in chunk]
    for task in asyncio.as_completed(tasks):
        result = await task
        save(result)
```
