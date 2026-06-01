# Chat Calls

Extracted reference for `/scillm`. Load on demand — do not duplicate in SKILL.md.

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

