# Files Multimodal

Extracted reference for `/scillm`. Load on demand — do not duplicate in SKILL.md.

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
    },
    timeout=120.0,
)
```

**Supported MIME types** (Gemini native): `application/pdf`, `image/png`, `image/jpeg`, `image/webp`, `image/gif`, `audio/*`, `video/*`, `text/plain`, `text/csv`, `text/html`.

**ZIP files**: Supported! The proxy auto-explodes ZIP archives — unpacks each file and sends it as its own part (text files as text, images/PDFs as `inlineData`). Just send `mimeType: "application/zip"` and the proxy handles the rest. Tested: 64KB ZIP with 8 files (code, markdown, PNG) → 2.78s, 14K tokens.

**WARNING**: `inlineData` only works with `model: "text-gemini"` or `"text-gemini-3"` (direct). Using `model: "text"` will fail on Chutes/DeepSeek before reaching Gemini. The proxy only switches to the native Gemini API when the deployment targets `generativelanguage.googleapis.com`.

**`text-gemini-3`** (Gemini 3 Flash Preview) is a thinking model — better for complex analysis of PDFs/images but uses internal reasoning tokens. Do NOT set `max_tokens` — reasoning models consume tokens internally and a low limit produces empty output.

### Option C: Images via image_url (all VLM providers)

For images (not PDFs), use the OpenAI-compat `image_url` format. For this project, prefer direct `model: "gpt-5.5"` for high-reasoning image calls or `model: "vlm-chutes"` for higher-throughput VLM calls. Avoid generic `model: "vlm"` when Gemini quota limits matter, because the configured cascade starts with Gemini:

```python
with open("screenshot.png", "rb") as f:
    img_b64 = base64.b64encode(f.read()).decode()

resp = httpx.post(url, json={
    "model": "gpt-5.5",  # direct Codex OAuth; avoids Gemini VLM quota
    "messages": [{"role": "user", "content": [
        {"type": "text", "text": "Describe this screenshot"},
        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{img_b64}"}},
    ]}],
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

