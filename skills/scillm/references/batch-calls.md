# Batch Calls

Extracted reference for `/scillm`. Load on demand — do not duplicate in SKILL.md.

## Batch Calls (Parallel Completions)

**Default rule: all `/scillm` batch calls MUST use `asyncio.as_completed(tasks)` unless the user explicitly asks for ordered `gather` output.** This is required so long-running items do not block completed results, failures can be recorded item-by-item, and large jobs can persist partial progress as responses arrive.

**Large QRA/default DeepSeek batches:** use the server-side pool endpoint `POST /v1/scillm/batch/completions` with `model_pool: "qra-deepseek-pool"` instead of hand-splitting Chutes/OpenCode Go yourself. This pool runs independent Chutes and OpenCode Go lanes concurrently and returns results in completion order.

Do not use `asyncio.gather` for `/scillm` batches by default. If ordered output is required, collect `as_completed` results with each item’s `id` or `scillm_metadata`, then reorder after completion.

Use `httpx.AsyncClient`, create tasks with `asyncio.create_task`, and process them with `asyncio.as_completed`. The proxy handles provider-side concurrency limits, but callers should still use a local `asyncio.Semaphore` for very large batches or quota-sensitive providers.

### Server-side DeepSeek pool (recommended for large QRA batches)

Use this when a batch has many independent QRA/extraction prompts and Chutes and
OpenCode Go quality are close enough that throughput matters more than a single
provider choice. Do **not** use it for model evals where every prompt must hit
every model; use `/llm-eval-lab` for that.

Pool contract:

| Pool | Strategy | Lanes |
|------|----------|-------|
| `qra-deepseek-pool` | weighted round-robin | Chutes `deepseek-ai/DeepSeek-V3-0324-TEE` weight 3 + OpenCode Go `opencode-go/deepseek-v4-flash` weight 2 |

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
        print(result["item_id"], result["model"], result["latency_s"])
        # result["content"] contains the assistant text
    else:
        print("FAILED", result["item_id"], result["model"], result["error"])
```

Response notes:

- Results are returned in `as_completed` order; use `item_id` to join back to inputs.
- Each inner call receives `scillm_metadata.batch_id`, `item_id`, `model_pool`, `lane`, `selected_model`, and `provider`.
- Use `GET /v1/scillm/model-pools` to inspect available pools and lane weights.
- Use `GET /v1/scillm/model-pools/qra-deepseek-pool/status` for dashboard/live pool concurrency. Use `live_in_flight` / `actual_in_flight` for progress; treat `stale_active_calls` and `registry_drift` as diagnostics only.
- Do not infer pool health from raw `/v1/scillm/active-calls`; raw active calls are a debugging view only and stale rows are separated from live work.
- OpenCode Go DeepSeek/MiniMax use an Anthropic-compatible `/messages` lane; `response_format` is translated into provider-boundary JSON instructions in the system prompt and final user turn because that endpoint does not enforce OpenAI `response_format` natively.
- Use this endpoint to raise throughput across providers; do not treat OpenCode Go as a Chutes fallback.

### httpx batch (recommended — no scillm import)

```python
import asyncio, httpx, time

URL = "http://localhost:4001/v1/chat/completions"
HEADERS = {"Authorization": "Bearer sk-dev-proxy-123"}

async def complete(client, request):
    """Fire one request, return result paired with original request."""
    t0 = time.monotonic()
    try:
        resp = await client.post(URL, headers=HEADERS, json={
            "model": request.get("model", "text"),
            "messages": [{"role": "user", "content": request["prompt"]}],
            "scillm_metadata": {"batch_id": request["batch_id"], "item_id": request["id"]},
        }, timeout=120.0)
        resp.raise_for_status()
        data = resp.json()
        return {
            "ok": True,
            "request": request,
            "content": data["choices"][0]["message"]["content"],
            "metadata": data.get("scillm_metadata"),
            "elapsed_s": round(time.monotonic() - t0, 2),
        }
    except Exception as exc:
        return {
            "ok": False,
            "request": request,
            "error": str(exc),
            "elapsed_s": round(time.monotonic() - t0, 2),
        }

async def main():
    requests = [
        {"batch_id": "math-demo", "id": "q1", "prompt": "What is 2+2?"},
        {"batch_id": "math-demo", "id": "q2", "prompt": "What is 3+3?"},
        {"batch_id": "math-demo", "id": "q3", "prompt": "What is 4+4?"},
    ]
    async with httpx.AsyncClient() as client:
        tasks = [asyncio.create_task(complete(client, request)) for request in requests]
        results = []
        for task in asyncio.as_completed(tasks):
            result = await task
            results.append(result)
            if result["ok"]:
                print(f"{result['request']['id']} done in {result['elapsed_s']}s")
            else:
                print(f"{result['request']['id']} FAILED: {result['error']}")
    return results

asyncio.run(main())
```

### Response-arrival pattern (required default)

Use `asyncio.as_completed` to handle each response the moment it arrives.
Each result carries its original request metadata for pairing:

```python
import asyncio, httpx, time

URL = "http://localhost:4001/v1/chat/completions"
HEADERS = {"Authorization": "Bearer sk-dev-proxy-123"}

async def complete(client, request):
    """Fire one request, return result paired with original request."""
    t0 = time.monotonic()
    try:
        resp = await client.post(URL, headers=HEADERS, json={
            "model": request.get("model", "text"),
            "messages": [{"role": "user", "content": request["prompt"]}],
        }, timeout=90.0)
        resp.raise_for_status()
        return {
            "ok": True,
            "request": request,
            "content": resp.json()["choices"][0]["message"]["content"],
            "elapsed_s": round(time.monotonic() - t0, 2),
        }
    except Exception as e:
        return {
            "ok": False,
            "request": request,
            "error": str(e),
            "elapsed_s": round(time.monotonic() - t0, 2),
        }

async def main():
    requests = [
        {"prompt": f"Summarize document {doc_id}", "doc_id": doc_id}
        for doc_id in ["AC-17", "AC-18", "AC-19", "AC-20"]
    ]

    async with httpx.AsyncClient() as client:
        tasks = [asyncio.create_task(complete(client, r)) for r in requests]

        # Process each result the moment it arrives
        for coro in asyncio.as_completed(tasks):
            result = await coro
            if result["ok"]:
                print(f"{result['request']['doc_id']} done in {result['elapsed_s']}s")
                # save(result["request"]["doc_id"], result["content"])
            else:
                print(f"{result['request']['doc_id']} FAILED: {result['error']}")

asyncio.run(main())
```

**Concurrency limiting** — wrap with `asyncio.Semaphore` if you want client-side
limits (the proxy also enforces its own per-provider limits):

```python
sem = asyncio.Semaphore(6)

async def complete_limited(client, request):
    async with sem:
        return await complete(client, request)
```

### OpenCode Go Large Batches

For OpenCode Go batches, use exact `opencode-go/<model-id>` names and generate the
live model list before choosing a model. Unlike Chutes, OpenCode Go should not be
treated as a warm/cold fallback pool; pick the model intentionally and cap client
concurrency to avoid burning subscription quota or creating local queue pressure.

Suggested starting concurrency:

| Model Pattern | Starting Concurrency | Notes |
|---------------|----------------------|-------|
| `opencode-go/deepseek-v4-pro` | 3–4 | Stronger, likely slower. Use for quality-sensitive coding/reasoning batches. |
| `opencode-go/deepseek-v4-flash` | 6–8 | Faster DeepSeek option. Use for throughput-sensitive batches. |
| `opencode-go/minimax-m2.7` | 4–6 | Good coding batch model. |
| `opencode-go/qwen3.6-plus` | 6–8 | OpenAI-compatible chat endpoint, good throughput candidate. |
| `opencode-go/kimi-k2.6` | 4–6 | Use for Kimi-specific coding behavior. |

```python
import asyncio
import httpx

SCILLM = "http://localhost:4001"
HEADERS = {
    "Authorization": "Bearer sk-dev-proxy-123",
    "X-Caller-Skill": "scillm-opencode-go-batch",
}

async def pick_opencode_go_model(client, prefix="opencode-go/deepseek-v4-"):
    listing = await client.get(
        f"{SCILLM}/v1/scillm/opencode-go/models",
        headers=HEADERS,
        params={"refresh": "true"},
    )
    listing.raise_for_status()
    models = listing.json()["models"]
    candidates = [
        m["id"] for m in models
        if m["id"].startswith(prefix) and m["supported"] and m["key_configured"]
    ]
    if "opencode-go/deepseek-v4-pro" in candidates:
        return "opencode-go/deepseek-v4-pro"
    if not candidates:
        raise RuntimeError("No configured OpenCode Go models available")
    return candidates[0]

async def complete_one(client, sem, model, item):
    async with sem:
        resp = await client.post(
            f"{SCILLM}/v1/chat/completions",
            headers=HEADERS,
            json={
                "model": model,
                "messages": [
                    {"role": "user", "content": item["prompt"]},
                ],
                "temperature": 0,
                "scillm_metadata": {"batch_id": item["batch_id"], "item_id": item["id"]},
            },
            timeout=180.0,
        )
        resp.raise_for_status()
        data = resp.json()
        return {
            "ok": True,
            "id": item["id"],
            "content": data["choices"][0]["message"]["content"],
            "metadata": data.get("scillm_metadata"),
        }

async def run_batch(items, concurrency=4):
    async with httpx.AsyncClient(timeout=180.0) as client:
        model = await pick_opencode_go_model(client)
        sem = asyncio.Semaphore(concurrency)
        tasks = [asyncio.create_task(complete_one(client, sem, model, item)) for item in items]
        results = []
        for task in asyncio.as_completed(tasks):
            try:
                results.append(await task)
            except Exception as exc:
                results.append({"ok": False, "error": str(exc)})
        return model, results

items = [
    {"batch_id": "demo", "id": "1", "prompt": "Summarize this requirement: ..."},
    {"batch_id": "demo", "id": "2", "prompt": "Summarize this requirement: ..."},
]
model, results = asyncio.run(run_batch(items, concurrency=4))
print(model, results)
```

For very large batches, chunk inputs at the caller level (for example, 100–500
items at a time), persist results after each chunk, and resume failed items using
the original `scillm_metadata.batch_id` and `item_id`.

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

