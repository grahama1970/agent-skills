---
name: scillm
description: >
  Universal LLM proxy on localhost:4001. One endpoint for all providers:
  Chutes, DeepSeek, Gemini, Ollama, Claude (OAuth), Codex (OAuth), GLM.
  Auto-routes by model name. POST /v1/chat/completions (OpenAI-compatible).
  ZIP explosion, PDF inlineData, fallback cascades, JSON repair.
allowed-tools: Bash, Read
triggers:
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
  - send zip to LLM
  - send PDF to LLM
metadata:
  short-description: scillm (universal LLM proxy — Chutes, Gemini, Claude, Codex, GLM, Ollama)
provides:
  - llm-completion
composes: [task-monitor, create-evidence-case, analytics, create-figure, llm-eval-lab]

taxonomy:
  - inference
  - llm
---

# scillm — One Endpoint for All LLM Calls

## Setup (one-time per provider)

Most providers need zero setup — scillm reads existing credentials automatically.

| Provider | Setup | How it works |
|----------|-------|--------------|
| **Claude** | None (if using Claude Code) | Reads `~/.claude/.credentials.json` automatically. Already there if you're in Claude Code. |
| **Codex** | `npm install -g @openai/codex && codex login` | Creates `~/.codex/auth.json`. One-time login, scillm reads it. |
| **Gemini** | Add `GEMINI_API_KEY=your-key` to `.env` | Get key from [aistudio.google.com](https://aistudio.google.com/apikey) |
| **GLM** | Add `GLM_API_Key=your-key` to `.env` | Get key from [z.ai](https://z.ai) (Coding Lite plan or higher) |
| **Chutes** | Add `CHUTES_API_KEY` and `CHUTES_API_BASE` to `.env` | PAYG or subscription at [chutes.ai](https://chutes.ai) |
| **DeepSeek** | Add `DEEPSEEK_API` to `.env` | Get key from [platform.deepseek.com](https://platform.deepseek.com) |
| **Ollama** | `ollama pull model:tag` | Local models, no auth needed |

After setup, rebuild the proxy: `docker compose -p scillm -f deploy/docker/compose.scillm.core.yml up -d --build`

**Verify auth status:** `curl http://localhost:4001/v1/scillm/auth -H "Authorization: Bearer sk-dev-proxy-123"`

## How to Call

**POST `http://localhost:4001/v1/chat/completions`** — standard OpenAI format.
Use httpx, openai SDK, or curl. No pip install. No custom endpoints. No imports.

Auth: `Bearer sk-dev-proxy-123` (dev master key).

The proxy handles provider cascading, retries, JSON validation, VLM auto-routing,
concurrency limits, budget tracking, and optional Redis caching.

## Available Models

| Model | Backend | Use Case | Fallback |
|-------|---------|----------|----------|
| `text` | Chutes DeepSeek-V3 (non-TEE → V3.1-TEE) | General text, extraction, summarization | → text-gemini → text-gemini-paid → text-deepseek |
| `vlm` | Gemini 2.5 Flash (free key) | Image/PDF/screenshot description | → vlm-paid → vlm-claude → vlm-codex |
| `local-text` | Ollama qwen2.5:0.5b (local) | Smoke tests, always-on fallback | (none) |
| `moonshot-text` | Moonshot Kimi K2 | Alternative text provider | (none) |
| `text-gemini` | Gemini 2.5 Flash (free key) | Fast, 1M context | → text-gemini-paid → text-deepseek |
| `text-gemini-paid` | Gemini 2.5 Flash (paid key) | Paid fallback when free exhausted | (none) |
| `text-gemini-3` | Gemini 3 Flash Preview (free key) | Thinking model, 1M context | → text-gemini-3-paid |
| `claude-sonnet-4-6` | Anthropic Claude Sonnet (OAuth) | Max subscription via ~/.claude | (none) |
| `claude-haiku-4-5` | Anthropic Claude Haiku (OAuth) | Fast, cheap via Max subscription | (none) |
| `gpt-5.3-codex` | OpenAI Codex (OAuth) | High-reasoning via ~/.codex | (none) |
| `vlm-claude` | Claude Sonnet (OAuth) | VLM fallback (images + PDFs) | (none) |
| `vlm-codex` | GPT-5.3 Codex (OAuth) | VLM fallback (images + PDFs) | (none) |
| Any `gemini-*` | Google | Auto-routed to Gemini API | (none) |
| Any `claude-*` | Anthropic | Auto-routed via Claude Code OAuth | (none) |
| Any `gpt-*`/`codex-*` | OpenAI | Auto-routed via Codex CLI OAuth | (none) |
| Any `Org/Model` | Chutes | Auto-routed to Chutes API | (none) |
| Any `model:tag` | Ollama | Auto-routed to local Ollama | (none) |

**Use the model name directly** — no aliases needed. The proxy auto-routes based on the name:

| Pattern | Provider | Auth | Example |
|---------|----------|------|---------|
| `claude-*` | Anthropic | Claude Code Max OAuth | `claude-sonnet-4-6` |
| `gpt-*` / `codex-*` | OpenAI Codex | ChatGPT OAuth | `gpt-5.3-codex` |
| `gemini-*` | Google | API key | `gemini-2.5-flash` |
| `glm-*` (via `text-glm`) | Z.AI GLM | API key | `text-glm` → glm-5.1 |
| `Org/Model` | Chutes | API key | `Qwen/Qwen3-30B-A3B` |
| `model:tag` | Ollama (local) | none | `qwen2.5:7b` |

Cascade aliases still work: `text` (Chutes → Gemini free → Gemini paid → DeepSeek), `vlm` (Gemini free → Gemini paid → Claude → Codex).

**Chutes cold-start handling**: Non-TEE tried first (1 retry), falls through to TEE on 503. Warmup API fires in background on cold detect — miners notified to spin up. Next call may hit warm non-TEE.

**Discover all available models:** `GET /v1/scillm/providers` returns every provider, its auto-routing pattern, available models, and auth status.

---

## Single Call (Paved Path)

The easiest way — zero boilerplate:

```python
from scillm.paved import chat, chat_json, analyze_image, analyze_image_json

# Text
answer = await chat("What is the capital of France?")

# With system prompt
answer = await chat("Summarize AC-17", system="You are a compliance analyst.")

# JSON response (auto-validated, auto-repaired)
data = await chat_json("Return {name, age} for Alice who is 25")

# Image analysis (local file or URL — auto base64-encoded)
desc = await analyze_image("/path/to/diagram.png", "What does this show?")
desc = await analyze_image("https://example.com/chart.jpg", "Describe this chart")

# Image → structured JSON
data = await analyze_image_json("receipt.jpg", 'Extract {"total": number, "items": [...]}')
```

Defaults to `localhost:4001` + `sk-dev-proxy-123`. Override via env vars (`SCILLM_API_BASE`, `SCILLM_PROXY_KEY`, `SCILLM_MODEL`) or function kwargs.

### With httpx (no scillm import)

```python
import httpx

resp = httpx.post(
    "http://localhost:4001/v1/chat/completions",
    headers={"Authorization": "Bearer sk-dev-proxy-123"},
    json={"model": "text", "messages": [{"role": "user", "content": "What is 2+2?"}]},
    timeout=30.0,
)
content = resp.json()["choices"][0]["message"]["content"]
```

### With openai SDK

```python
from openai import OpenAI

client = OpenAI(base_url="http://localhost:4001/v1", api_key="sk-dev-proxy-123")
resp = client.chat.completions.create(
    model="text",
    messages=[{"role": "user", "content": "Hello"}],
    max_tokens=64,
)
print(resp.choices[0].message.content)
```

## JSON Response

Add `response_format` — the proxy auto-validates and retries on broken JSON:

```python
resp = httpx.post(
    "http://localhost:4001/v1/chat/completions",
    headers={"Authorization": "Bearer sk-dev-proxy-123"},
    json={
        "model": "text",
        "messages": [{"role": "user", "content": "Return {name, age} for Alice who is 25"}],
        "response_format": {"type": "json_object"},
        "max_tokens": 64,
    },
    timeout=30.0,
)
data = json.loads(resp.json()["choices"][0]["message"]["content"])
```

## Image Analysis (VLM Auto-Routing)

Send images with `model: "text"` — the proxy auto-detects `image_url` parts and
routes to VLM providers. No need to know the model name:

```python
import base64, httpx

with open("photo.png", "rb") as f:
    b64 = base64.b64encode(f.read()).decode()

resp = httpx.post(
    "http://localhost:4001/v1/chat/completions",
    headers={"Authorization": "Bearer sk-dev-proxy-123"},
    json={
        "model": "text",  # auto-routed to vlm when image detected
        "messages": [{"role": "user", "content": [
            {"type": "text", "text": "Describe this image"},
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}},
        ]}],
        "max_tokens": 512,
    },
    timeout=60.0,
)
description = resp.json()["choices"][0]["message"]["content"]
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

### Simple: asyncio.gather

Call the same endpoint concurrently. The proxy handles concurrency internally:

```python
import asyncio, httpx

async def complete(client, prompt):
    resp = await client.post(
        "http://localhost:4001/v1/chat/completions",
        headers={"Authorization": "Bearer sk-dev-proxy-123"},
        json={
            "model": "text",
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 256,
        },
        timeout=45.0,
    )
    return resp.json()["choices"][0]["message"]["content"]

async def main():
    async with httpx.AsyncClient() as client:
        results = await asyncio.gather(
            complete(client, "What is 2+2?"),
            complete(client, "What is 3+3?"),
            complete(client, "What is 4+4?"),
        )
    return results
```

### Advanced: parallel_acompletions_iter (request-response pairing)

Async iterator that yields results as they complete, with every result carrying its original request.
`messages` accepts a plain string (auto-wrapped as `[{"role": "user", "content": str}]`) or
an OpenAI-style message array (required for multi-turn, system prompts, or multimodal/VLM content):

```python
from scillm.batch import parallel_acompletions_iter

requests = [
    {"messages": f"Summarize document {doc_id}", "metadata": {"doc_id": doc_id}}
    for doc_id in document_ids
]

async for result in parallel_acompletions_iter(requests, concurrency=6):
    doc_id = result["request"]["metadata"]["doc_id"]
    if result["ok"]:
        save(doc_id, result["response"])
    else:
        retry_queue.append(doc_id)
```

For multimodal (VLM), use convenience fields — scillm auto-detects images and routes to VLM:

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
async def hedged_call(client, prompt, primary="text", backup="text-gemini"):
    async def call(model):
        resp = await client.post(
            "http://localhost:4001/v1/chat/completions",
            headers={"Authorization": "Bearer sk-dev-proxy-123"},
            json={"model": model, "messages": [{"role": "user", "content": prompt}], "max_tokens": 256},
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

Extract text client-side and concatenate into one prompt. Works with every model alias and the full fallback cascade:

```python
texts = []
for path in file_paths:
    texts.append(f"=== {path.name} ===\n{path.read_text()}")
combined = "\n\n".join(texts)

resp = httpx.post(
    "http://localhost:4001/v1/chat/completions",
    headers={"Authorization": "Bearer sk-dev-proxy-123"},
    json={
        "model": "text",  # works with any provider in the cascade
        "messages": [{"role": "user", "content": f"{combined}\n\nYour question here"}],
        "max_tokens": 4096,
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
    headers={"Authorization": "Bearer sk-dev-proxy-123"},
    json={
        "model": "text-gemini",  # MUST target Gemini directly
        "messages": [{"role": "user", "content": [
            {"type": "text", "text": "Summarize this document"},
            {"inlineData": {"mimeType": "application/pdf", "data": pdf_b64}},
        ]}],
        "max_tokens": 4096,
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
    headers={"Authorization": "Bearer sk-dev-proxy-123"},
    json={
        "model": "text-gemini",
        "messages": [{"role": "user", "content": parts}],
        "max_tokens": 4096,
    },
    timeout=120.0,
)
```

**Supported MIME types** (Gemini native): `application/pdf`, `image/png`, `image/jpeg`, `image/webp`, `image/gif`, `audio/*`, `video/*`, `text/plain`, `text/csv`, `text/html`.

**ZIP files**: Supported! The proxy auto-explodes ZIP archives — unpacks each file and sends it as its own part (text files as text, images/PDFs as `inlineData`). Just send `mimeType: "application/zip"` and the proxy handles the rest. Tested: 64KB ZIP with 8 files (code, markdown, PNG) → 2.78s, 14K tokens.

**WARNING**: `inlineData` only works with `model: "text-gemini"` or `"text-gemini-3"` (direct). Using `model: "text"` will fail on Chutes/DeepSeek before reaching Gemini. The proxy only switches to the native Gemini API when the deployment targets `generativelanguage.googleapis.com`.

**`text-gemini-3`** (Gemini 3 Flash Preview) is a thinking model — better for complex analysis of PDFs/images but uses internal reasoning tokens. Set `max_tokens` higher (4096+) to avoid budget exhaustion.

### Option C: Images via image_url (all VLM providers)

For images (not PDFs), use the OpenAI-compat `image_url` format. This works across the full VLM cascade (Gemini → Claude → Codex):

```python
with open("screenshot.png", "rb") as f:
    img_b64 = base64.b64encode(f.read()).decode()

resp = httpx.post(url, json={
    "model": "vlm",  # cascade: Gemini free → paid → Claude → Codex
    "messages": [{"role": "user", "content": [
        {"type": "text", "text": "Describe this screenshot"},
        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{img_b64}"}},
    ]}],
    "max_tokens": 2048,
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
| PDFs, Gemini | `inlineData` parts | `text-gemini` or `text-gemini-3` | Gemini free → paid |
| PDFs, Claude | `image_url` data URI or `document` block | `claude-sonnet-4-6` | Claude direct |
| PDFs, full cascade | `image_url` data:application/pdf | `vlm` | YES → Gemini → Claude |
| PDFs + images, Gemini | `inlineData` per file | `text-gemini` or `text-gemini-3` | Gemini free → paid |
| Mixed PDF+images, Claude | `image_url` for both | `claude-sonnet-4-6` | Claude direct |

---

## Ollama Auto-Routing

Any locally-pulled Ollama model works through the proxy without a config entry. Just use the Ollama model:tag name directly:

```python
resp = httpx.post(
    "http://localhost:4001/v1/chat/completions",
    headers={"Authorization": "Bearer sk-dev-proxy-123"},
    json={"model": "qwen2.5:7b", "messages": [{"role": "user", "content": "hi"}]},
)
```

The proxy auto-detects unknown model names and routes them to the local Ollama instance. `response_format` is automatically stripped for Ollama models (Ollama doesn't support it).

Available Ollama models: anything you've pulled with `ollama pull`. Check with `ollama list`.

---

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
        "max_tokens": 4096,
    },
    timeout=60.0,
)
content = resp.json()["choices"][0]["message"]["content"]
```

### What works and what doesn't

| Parameter | Supported? | Notes |
|-----------|-----------|-------|
| `messages` | YES | Standard OpenAI format |
| `max_tokens` | YES | Required — Claude needs this |
| `temperature` | YES | 0.0-1.0 |
| `top_p` | YES | |
| `stop` | YES | String or list |
| `system` role in messages | PARTIAL | Injected as user message (OAuth locks system prompt) |
| `response_format` | NO | Claude doesn't support json_object — ask for JSON in the prompt |
| `tools` / `tool_choice` | YES | Full tool use: Claude (Anthropic format translation), Codex (Responses API format), Gemini (native passthrough) |
| `stream` | YES | SSE streaming with OpenAI delta format (`data: {"choices":[{"delta":{"content":"..."}}]}`) |
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
2. **Missing `max_tokens`**: defaults to 4096 but include it explicitly
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
        "model": "gpt-5.3-codex",
        "messages": [{"role": "user", "content": "Explain quicksort"}],
    },
    timeout=120.0,
)
```

**Supported models:** `gpt-5.2-codex`, `gpt-5.3-codex`. Standard GPT models (gpt-4o, etc.) are NOT supported via ChatGPT OAuth — they require a platform API key.

**Streaming:** Both Claude and Codex support `"stream": true`. The proxy translates provider-specific SSE events into OpenAI-compatible delta chunks (`data: {"choices":[{"delta":{"content":"..."}}]}`). Works with any SSE client including `httpx.stream()` and the OpenAI SDK.

**Note:** `max_tokens` is ignored for Codex (the ChatGPT backend doesn't support it).

**Credential priority:** `~/.codex/auth.json` (Codex CLI) > `~/.pi/agent/auth.json` (Pi CLI).

---

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

## Ops Endpoints

| Endpoint | Method | Purpose |
|---|---|---|
| `/health/liveliness` | GET | Is the proxy alive? |
| `/v1/scillm/health` | GET | Router health + fallback config + concurrency status |
| `/v1/scillm/models` | GET | Model groups, deployments, aliases |
| `/v1/scillm/providers` | GET | **All available providers, auto-routing patterns, and examples** |
| `/v1/scillm/auth` | GET | **OAuth token health** — Claude/Codex token status, expiry, subscription tier |
| `/v1/models` | GET | OpenAI-compatible model list (includes auto-routable models) |
| `/v1/budget` | GET | Current daily spend and remaining budget |
| `/metrics` | GET | Prometheus counters (requests, errors, latency by group) |

```bash
curl http://localhost:4001/v1/scillm/health -H "Authorization: Bearer sk-dev-proxy-123"
curl http://localhost:4001/v1/scillm/models -H "Authorization: Bearer sk-dev-proxy-123"
curl http://localhost:4001/v1/budget -H "Authorization: Bearer sk-dev-proxy-123"
curl http://localhost:4001/metrics
```

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

All composable skills call `http://localhost:4001/v1/chat/completions` — no direct
provider access, no SDK imports, no API keys needed beyond the proxy master key.
