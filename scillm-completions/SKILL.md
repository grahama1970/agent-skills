---
name: scillm-completions
description: Make LLM completions via scillm - text, JSON, vision/images, and batch processing. Use for any LLM call, API integration, or multi-modal analysis.
allowed-tools: Read, Bash, Grep, Glob
metadata:
  short-description: LLM completions (text, JSON, vision, batch)
---

# scillm Completions

Call LLMs for text, JSON, vision, and batch processing.

## Simplest Usage

```python
from scillm.paved import chat, chat_json, analyze_image

# Text completion
answer = await chat("What is the capital of France?")
# "Paris"

# JSON response
data = await chat_json('Return {"name": "Alice", "age": 25}')
# {"name": "Alice", "age": 25}

# Image analysis
desc = await analyze_image("https://example.com/photo.jpg", "Describe this")
```

## Common Patterns

### Text with system prompt
```python
from scillm.paved import chat

answer = await chat(
    "Explain quantum computing",
    system="You are a physics teacher. Keep explanations simple.",
    temperature=0.5,
)
```

### JSON structured output
```python
from scillm.paved import chat_json

data = await chat_json(
    'Extract entities from: "John works at Acme Corp in NYC". Return {"person": str, "company": str, "location": str}',
    temperature=0.2,  # Lower = more deterministic
)
# {"person": "John", "company": "Acme Corp", "location": "NYC"}
```

### Analyze image URL
```python
from scillm.paved import analyze_image

description = await analyze_image(
    "https://example.com/chart.png",
    "What does this chart show? Summarize the key insights."
)
```

### Analyze local image file
```python
from scillm.paved import analyze_image

# Works with file paths directly - handles base64 encoding automatically
description = await analyze_image(
    "/path/to/photo.jpg",
    "Describe what you see in this image"
)
```

### Extract structured data from image
```python
from scillm.paved import analyze_image_json

data = await analyze_image_json(
    "receipt.jpg",
    'Extract {"total": number, "items": [{"name": str, "price": number}]}'
)
# {"total": 42.50, "items": [{"name": "Coffee", "price": 4.50}, ...]}
```

## Batch Processing

For processing many items in parallel, use the lower-level API:

```python
from scillm.batch import parallel_acompletions_iter
import os

requests = [
    {"model": "openrouter/openai/gpt-4o-mini",
     "messages": [{"role": "user", "content": f"Summarize: {doc}"}]}
    for doc in documents
]

results = []
async for r in parallel_acompletions_iter(
    requests,
    api_base="https://openrouter.ai/api/v1",
    api_key=os.environ["OPENROUTER_API_KEY"],
    custom_llm_provider="openrouter",
    concurrency=6,      # Parallel requests
    timeout=30,         # Per-request timeout
):
    if r["ok"]:
        results.append({"index": r["index"], "summary": r["content"]})
    else:
        print(f"Error at {r['index']}: {r['error']}")
```

### Batch with JSON validation
```python
schema = {
    "type": "object",
    "properties": {"summary": {"type": "string"}, "score": {"type": "number"}},
    "required": ["summary", "score"],
}

async for r in parallel_acompletions_iter(
    requests,
    api_base="https://openrouter.ai/api/v1",
    api_key=os.environ["OPENROUTER_API_KEY"],
    custom_llm_provider="openrouter",
    schema=schema,           # Validate JSON
    retry_invalid_json=2,    # Retry on bad JSON
    concurrency=6,
):
    if r["ok"]:
        data = r["content"]  # Validated dict
```

## API Reference

### Simple wrappers (scillm.paved)

| Function | Purpose |
|----------|---------|
| `chat(prompt)` | Text completion, returns string |
| `chat_json(prompt)` | JSON completion, returns dict |
| `analyze_image(image, prompt)` | Vision analysis, returns string |
| `analyze_image_json(image, prompt)` | Vision + JSON, returns dict |

All accept optional: `model`, `system`, `api_base`, `api_key`, `temperature`, `max_tokens`

### Batch response fields

```python
r = {
    "ok": True,              # Success?
    "index": 0,              # Request index
    "content": "...",        # Response (string or dict if JSON)
    "status": 200,           # HTTP status
    "elapsed_s": 1.2,        # Time taken
    "error": None,           # Error message if failed
}
```

## Models (via OpenRouter)

| Model | Use Case |
|-------|----------|
| `openrouter/openai/gpt-4o-mini` | Fast, cheap (default for chat) |
| `openrouter/anthropic/claude-sonnet-4-20250514` | Best for code/vision (default for images) |
| `openrouter/openai/gpt-4o` | Smarter, vision capable |
| `openrouter/deepseek/deepseek-prover-v2` | Mathematical proofs |

## Environment Variables

| Variable | Required | Purpose |
|----------|----------|---------|
| `OPENROUTER_API_KEY` | Yes | OpenRouter API access |
| `SCILLM_MODEL` | No | Override default text model |
| `SCILLM_VISION_MODEL` | No | Override default vision model |

## Troubleshooting

| Problem | Solution |
|---------|----------|
| `AuthenticationError` | Check `OPENROUTER_API_KEY` |
| `RateLimitError` | Reduce `concurrency` in batch |
| `Timeout` | Increase `timeout` param |
| Invalid JSON | Use `chat_json()` or add `response_format` |
| Vision not working | Use vision-capable model |
