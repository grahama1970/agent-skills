# SciLLM Paved‑Path Contract

## Which Pattern Should I Use? (Read This First)

```
Can you `from scillm import acompletion`?
  YES → You’re inside scillm’s venv. Use the SDK (Section A below).
  NO  → Use the Docker proxy directly via HTTP (Section B below).
```

**The Docker proxy at `http://localhost:4001` is always the correct answer for
code that cannot import the scillm pip package.** This is not a hack or bypass
-- it IS the centralized service that all scillm SDK calls route through anyway.

### Section B: Proxy-First (For Code Outside scillm’s Venv)

This applies to: memory project, horus, pi-mono, any skill, any project that
does not have scillm pip-installed. **This is the most common case.**

```python
import httpx

SCILLM_BASE = os.getenv("SCILLM_API_BASE", "http://localhost:4001")
SCILLM_KEY = os.getenv("SCILLM_PROXY_KEY", "sk-dev-proxy-123")

# Sync
resp = httpx.post(
    f"{SCILLM_BASE}/v1/chat/completions",
    headers={"Authorization": f"Bearer {SCILLM_KEY}"},
    json={
        "model": "text",  # or "vlm", "local-text"
        "messages": [{"role": "user", "content": prompt}],
        "response_format": {"type": "json_object"},
        "max_tokens": 1024,
        "temperature": 0.2,
    },
    timeout=30.0,
)
content = resp.json()["choices"][0]["message"]["content"]

# Async
async with httpx.AsyncClient(base_url=SCILLM_BASE) as client:
    resp = await client.post(
        "/v1/chat/completions",
        headers={"Authorization": f"Bearer {SCILLM_KEY}"},
        json={"model": "text", "messages": [{"role": "user", "content": prompt}]},
        timeout=30.0,
    )
    content = resp.json()["choices"][0]["message"]["content"]
```

Also works with the `openai` SDK:
```python
from openai import OpenAI
client = OpenAI(base_url="http://localhost:4001/v1", api_key="sk-dev-proxy-123")
```

**Rules for proxy callers:**
- DO use `httpx`, `openai` SDK, or `curl` to call `localhost:4001`
- DO set `Authorization: Bearer sk-dev-proxy-123` (the proxy master key)
- DO use model names `text`, `vlm`, or `local-text` (proxy-managed aliases)
- DON’T call Chutes/OpenRouter/DeepSeek directly -- the proxy handles routing
- DON’T build your own retry/fallback logic -- the proxy cascade handles it

### Section C: Batch Calls via `parallel_acompletions_proxy` (Recommended)

For batch/parallel completions through the Docker proxy, use `parallel_acompletions_proxy`.
It defaults to `localhost:4001` + `sk-dev-proxy-123` — no api_base/api_key boilerplate.

**Message formats** — scillm accepts three forms:

| Form | When to use | Example |
|------|-------------|---------|
| **Plain string** | Single-turn text prompts | `"messages": "What is 2+2?"` |
| **Convenience fields** | Images/files (auto VLM routing) | `"messages": "Describe this", "file_path": "photo.png"` |
| **OpenAI array** | Multi-turn, system prompts, multimodal | `"messages": [{"role": "system", ...}, {"role": "user", ...}]` |

Plain strings are auto-wrapped as `[{"role": "user", "content": str}]`.
Convenience fields (`url`, `urls`, `file_path`, `paths`) auto-detect images, base64-encode local files, and route to VLM.
OpenAI-style arrays pass through unchanged.

```python
from scillm.batch_wrappers import parallel_acompletions_proxy

# Simple text batch — plain strings
requests = [
    {"messages": "Summarize AC-17 requirements"},
    {"messages": "What are NIST 800-53 encryption controls?"},
]
async for result in parallel_acompletions_proxy(requests):
    if result["ok"]:
        print(result["response"])

# With images — auto VLM routing via convenience fields
requests = [
    {"messages": "Describe this diagram", "file_path": "/path/to/diagram.png"},
    {"messages": "What’s in this photo?", "url": "https://example.com/photo.jpg"},
]
async for result in parallel_acompletions_proxy(requests):
    print(result["response"])

# With source grounding verification
requests = [
    {
        "messages": "Summarize AC-17 requirements",
        "source": "findings/ac17_control.txt",  # file path or inline text
        "grounding_threshold": 0.7,
        "grounding_retries": 2,
    }
]
async for result in parallel_acompletions_proxy(requests, source="global_source.txt"):
    print(result["grounding_score"], result["response"])

# With JSON validation
async for result in parallel_acompletions_proxy(
    requests,
    response_format={"type": "json_object"},
    retry_invalid_json=2,
    repair_invalid_json=True,
):
    print(result["response"])
```

Each yielded `result` carries:
- `index` — position in original list
- `request` — your original request dict (with any metadata you attached)
- `ok` — success boolean
- `response` / `error` — the response or error message
- `attempts` — retry count
- `elapsed_s` — wall-clock time
- `grounding_score` / `grounding_attempts` — when source grounding is active

---

### Section A: SDK Path (For Code Inside scillm’s Venv)

This document defines rules for how code in `experiments/litellm/` (and
`experiments/devops/**`) must call SciLLM and Chutes via the pip package.
It exists to prevent regressions back to bespoke wrappers or manual headers.

Scope
- Applies to code where `from scillm import acompletion` works (scillm is pip-installed).
- Documentation may include `curl` examples for ops visibility, but executable code must follow this contract.

Canonical surfaces (to reduce confusion)
- Single model: `completion(...)` / `acompletion(...)`
- Batch: `batch_acompletions(...)` or `batch_acompletions_iter(...)` (aliases for `parallel_*`)
- Formal proofs: `certainly_prove(...)` / `completion(... custom_llm_provider="certainly" ...)`
- Multi‑model routing: **only** `Router(model_list=...)` (avoid custom fallback loops)

Hard Rules (Do / Don’t)
- DO use SciLLM directly:
  - `from scillm import acompletion, completion`
  - For large batch fan-out: `from scillm import batch_acompletions, batch_acompletions_iter` (aliases for the parallel_* APIs)
  - `from scillm.paved import sanity_preflight, list_models_openai_like, chutes_chat_json`
- DO pass credentials via `api_key=`; SciLLM canonicalizes headers for Chutes.
- DO request strict JSON when applicable: `response_format={"type":"json_object"}`.
- DO use paved preflight + discovery:
  - List models: `list_models_openai_like(api_base, api_key)` (Bearer → x‑api‑key fallback handled internally)
  - Preflight (sync helper): `sanity_preflight(api_base=..., api_key=..., model=..., parallel=3, wall_time_s=30)`
    - If you are already inside an event loop (async code), run it in a thread: `await asyncio.to_thread(sanity_preflight, api_base=..., api_key=..., model=...)`
- DO use Router only via SciLLM helpers (never reimplement):
  - `from scillm import Router` or `from scillm.paved import chutes_router_json`

- DON’T set auth headers manually **when using the scillm SDK** (use `api_key=` instead):
  - Don’t pass `extra_headers={"Authorization": "Bearer …"}` or `extra_headers={"x-api-key": …}`
- DON’T call Chutes/providers directly from SDK code -- route through the proxy (`api_base="http://localhost:4001"`)
- DON’T implement client‑side alternates/fallbacks for Step 07; preflight must fail fast so operators can fix routing/quota. Use Router flows only where explicitly intended.
- DON’T swallow preflight errors. Surface structured details (`exc_type`, `message`, `status`) to the caller.

Note: The old rule banning `httpx.post(...chat/completions)` applied only to SDK code that should use `acompletion()` instead. Calling the proxy via HTTP from non-SDK code is explicitly allowed (Section B).

JSON validation (strict mode)
- Opt in with `SCILLM_JSON_STRICT=1` (or `strict_json=True` on the call). When enabled and `response_format={"type":"json_object"}` is set, SCILLM raises `JsonParseError` on empty/non‑JSON content and attaches `scillm_meta` with `reason=json_parse_failed`, `sample`, `raw_len`, `model`, and `provider`. This keeps errors actionable without bespoke wrappers.

Parallel batch (openai_like / Chutes)
- Signature (v1.77.4): `parallel_acompletions(requests, *, api_base, api_key, custom_llm_provider='openai_like', concurrency=6, timeout=20, wall_time_s=900, default_max_tokens=None, default_temperature=None, response_format=None, tenacious=True, …)`
- Each request dict may contain: `model`, `messages`, `max_tokens?`, `temperature?`, `response_format?`, `api_base?`, `api_key?`.
- Important: unlike `acompletion(...)`, `parallel_acompletions(...)` does **not** accept a top-level `model=` kwarg. Put `model` inside each request dict (or rely on `CHUTES_MODEL_ID`/`CHUTES_TEXT_MODEL` defaults).
- Also note: `messages_list=...` is **not** a Python API parameter; it is a CLI convenience used by `scillm-tool parallel` to build the per-item request dicts.
- Progress: if you need progress logging / as-completed checkpointing, use `parallel_acompletions_iter(...)` (or its alias `batch_acompletions_iter(...)`) instead of waiting on one big `await parallel_acompletions(...)`.
  - Iterator parity: `schema=`, `retry_invalid_json=`, and `repair_invalid_json=` are supported at the iterator level too.
- Return shape: list of dicts with `index, request, response, error, status, content`. When `response_format` is json_object, `content` may be a dict or string. Check `error`/`status` per item.
- Guards: if `api_base`/`api_key` or `model` are missing after env defaults, SCILLM raises `ValueError` early instead of hanging.
- Recommended defaults to avoid silent waits: `tenacious=False`, `timeout=20-30`, `wall_time_s=120-300`, `concurrency=4-8`, `response_format={"type":"json_object"}`. Keep `SCILLM_JSON_STRICT=1` in CI to surface bad JSON.
- Structured JSON helpers:
  - `schema=` (jsonschema dict or callable) validates each item’s parsed JSON; failures set `error="invalid_json: …"` and keep `raw` sample.
  - `retry_invalid_json=N` retries invalid JSON up to N times with backoff (same messages).
  - `summary` attached to the first item: counts of ok/invalid_json/provider_error/empty_content.
  - `repair_invalid_json=True` (opt-in; env `SCILLM_REPAIR_INVALID_JSON=1`) salvages malformed JSON (trim braces, then `clean_json_string` when available) before failing; repaired items are marked `repaired=true` in results/summary.
- Example (one model, multiple requests):
```python
import asyncio
import os

from scillm import parallel_acompletions

MODEL = os.environ["CHUTES_MODEL_ID"]

async def main():
    reqs = [
        {
            "model": MODEL,
            "messages": [{"role": "user", "content": 'Return only {"ok":true} as JSON.'}],
            "response_format": {"type": "json_object"},
            "max_tokens": 64,
            "temperature": 0,
        },
        {
            "model": MODEL,
            "messages": [{"role": "user", "content": 'Return only {"n":1} as JSON.'}],
            "response_format": {"type": "json_object"},
            "max_tokens": 64,
            "temperature": 0,
        },
    ]

    resps = await parallel_acompletions(
        reqs,
        api_base=os.environ["CHUTES_API_BASE"],
        api_key=os.environ["CHUTES_API_KEY"],
        custom_llm_provider="openai_like",
        concurrency=4,
        timeout=20,
        wall_time_s=120,
        response_format={"type":"json_object"},
        tenacious=False,
    )
    for r in resps:
        if r["error"]:
            print("error", r["status"], r["error"])
        else:
            print("content", r["content"])

asyncio.run(main())
```

- Example with progress (recommended for large batches):
```python
import asyncio
import os

from scillm import batch_acompletions_iter

MODEL = os.environ["CHUTES_MODEL_ID"]

async def main():
    reqs = [
        {"model": MODEL, "messages": [{"role": "user", "content": "hi"}], "response_format": {"type": "json_object"}},
        {"model": MODEL, "messages": [{"role": "user", "content": "hi"}], "response_format": {"type": "json_object"}},
    ]
    done = ok = err = 0
    async for ev in batch_acompletions_iter(
        reqs,
        api_base=os.environ["CHUTES_API_BASE"],
        api_key=os.environ["CHUTES_API_KEY"],
        custom_llm_provider="openai_like",
        # Optional JSON validation/repair (same as parallel_acompletions)
        # schema=MY_JSON_SCHEMA,
        # retry_invalid_json=1,
        # repair_invalid_json=True,
        concurrency=6,
        timeout=60,
        wall_time_s=900,
        tenacious=True,
    ):
        done += 1
        ok += int(bool(ev.get("ok")))
        err += int(not ev.get("ok"))
        if done % 25 == 0 or not ev.get("ok"):
            print(f"{done}/{len(reqs)} ok={ok} err={err} idx={ev.get('index')} status={ev.get('status')} elapsed_s={ev.get('elapsed_s')}")

asyncio.run(main())
```

- Common mistake (don’t do this):
```python
# ❌ wrong: parallel_acompletions has no model= or messages_list= kwargs
# await parallel_acompletions(model=..., messages_list=[[...], [...]], api_base=..., api_key=...)
```

- Minimal example (single request):
```python
resps = await parallel_acompletions(
    [
      {"messages":[{"role":"system","content":"Return JSON only."},
                   {"role":"user","content":"Return {\"ok\":true} as JSON."}],
       "response_format":{"type":"json_object"},
       "max_tokens":64,
       "temperature":0,
       "model": os.environ["CHUTES_MODEL_ID"]},
    ],
    api_base=os.environ["CHUTES_API_BASE"],
    api_key=os.environ["CHUTES_API_KEY"],
    custom_llm_provider="openai_like",
    concurrency=4,
    timeout=20,
    wall_time_s=120,
    response_format={"type":"json_object"},
    tenacious=False,
)
for r in resps:
    if r["error"]:
        print("error", r["status"], r["error"])
    else:
        print("content", r["content"])
```

Certainly / Lean4 (paved path)

**Architecture Decision: scillm as Main Caller**

scillm is the paved path for certainly in production code. This keeps:
- **Single API surface** — all providers (chutes, openai, certainly) use the same patterns
- **Consistent orchestration** — auth, retries, logging handled uniformly by scillm
- **Separation of concerns** — certainly focuses on proving, scillm handles integration

For debugging and standalone testing, use the lean4 repo's CLI directly:
```bash
# Quick proof test (requires lean_runner + OPENROUTER_API_KEY)
python -m lean4_prover.certainly_min "Prove that n + 0 = n" --tactics simp
```

Do NOT build separate certainly wrappers or CLIs in other projects — route through scillm.

**Two Modes:**
1. **Direct Mode (Preferred)**: When `certainly` is installed (`pip install scillm[certainly]`), the provider uses direct Python imports with no HTTP overhead.
2. **HTTP Mode (Fallback)**: When `certainly` is not installed, falls back to HTTP bridge at `CERTAINLY_BRIDGE_BASE`.

**Direct Mode API** (preferred for new code):
```python
from scillm.integrations.certainly import prove_requirement, is_available

if is_available():
    result = await prove_requirement(
        requirement="Prove that n + 0 = n",
        tactics=["simp"],
    )
    # result["ok"], result["best"]["lean4"], etc.
```

**Minimal Runnable Script** (copy-paste-run):
```python
#!/usr/bin/env python
"""Minimal certainly proof example.

Prerequisites:
  - lean_runner container running (docker ps | grep lean_runner)
  - OPENROUTER_API_KEY set
  - scillm[certainly] installed (pip install scillm[certainly])
"""
import asyncio
from scillm.integrations.certainly import prove_requirement, is_available

async def main():
    if not is_available():
        print("ERROR: certainly not available")
        return 1

    result = await prove_requirement(
        requirement="Prove that for any natural number n, n + 1 > n",
        tactics=["simp", "omega"],
    )

    if result.get("ok"):
        print("OK: Proof found")
        print("Lean4 code:", result["best"]["lean4"][:300])
        return 0
    else:
        print("FAIL:", result.get("error") or result.get("diagnosis", {}).get("diagnosis"))
        return 1

if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
```

**Environment Variables:**
- `SCILLM_CERTAINLY_HTTP_ONLY=1` — Force HTTP mode even if certainly installed
- `SCILLM_CERTAINLY_DIRECT_STRICT=1` — Fail fast if direct mode fails (no fallback)

**Provider API** (uses direct mode automatically when available):
- Explicit signature (most used):
```python
def certainly_prove(
    *,
    items: List[Dict[str, Any]],
    flags: Optional[List[str]] = None,
    strategies: Optional[List[str] | str] = None,
    tactics: Optional[List[str] | str] = None,
    response_format: Optional[Dict[str, Any]] = None,
    options: Optional[Dict[str, Any]] = None,
    request_timeout: float = 120.0,
    max_seconds: Optional[float] = None,
    session_id: Optional[str] = None,
    track_id: Optional[str] = None,
    api_base: Optional[str] = None,
    require_proved: bool = False,
) -> LiteLLMResponse: ...
```

- Canonical item shape: `{"requirement_text": "0 + n = n"}` (alias: `{"text": ...}`).
- **Primary results live in** `resp.additional_kwargs["certainly"]["results"]`.
- In simple mode, failed results may include `explanation` (LLM-generated reason).
- `resp.choices[0].message["content"]` is a short summary string by default. If `response_format={"type":"json_object"}` (or `json_schema`), the content is a JSON string of the proof payload.
- Strategies/tactics can be passed globally via `flags=` **or** per-item via `strategies`/`tactics` keys in each item.
- Best practice: keep items for requirements + metadata only; put solver config in `flags=`.

- Simplified path (recommended default for pipelines)
  - Single LLM generation + **single compile attempt** (no repair loops).
  - Optional LLM explanation on failure (no auto‑fix).
  - LLM enabled by default; set `options={"no_llm": True}` to force offline mode.
  - Use the dedicated helpers or pass `options={"simple": True, "max_refinements": 0, "explain_failures": True}`.
```python
from scillm.extras.providers import certainly_prove_simple

resp = certainly_prove_simple(
    items=[{"requirement_text": "Nat.add_assoc", "id": "sanity-1"}],
    # Optional: increase if Lean compile is slow
    max_seconds=300,
)
payload = (resp.get("additional_kwargs", {}) or {}).get("certainly", {})
results = payload.get("results", [])
print("status", results[0].get("status"))
print("lean_code", results[0].get("lean_code"))
print("explanation", results[0].get("explanation"))  # only on failure
```

- Minimal example (bridge provider):
```python
import os
from scillm import completion

resp = completion(
    model="certainly",
    custom_llm_provider="certainly",
    api_base=os.getenv("CERTAINLY_BRIDGE_BASE", "http://127.0.0.1:8787"),
    messages=[{"role": "system", "content": "Certainly/Lean4"}],
    items=[{"requirement_text": "Nat.add_comm"}],
    max_seconds=120,
    flags=["--strategies", "direct,structured"],
    session_id="stage-08",
    track_id="run-001",
)
summary = resp.choices[0].message["content"]  # string summary
payload = resp.additional_kwargs["certainly"]  # full bridge payload (summary/results/statistics)
```

- Helper (paved convenience):
```python
from scillm.extras.providers import certainly_prove

resp = certainly_prove(
    items=[{"requirement_text": "Nat.add_assoc"}],
    api_base=os.getenv("CERTAINLY_BRIDGE_BASE", "http://127.0.0.1:8787"),
    flags=["--strategies", "direct,structured"],
    max_seconds=120,
)
payload = resp.additional_kwargs["certainly"]
```

- As-completed iterator (LLM-like fan-out, each item compiled independently):
```python
from scillm.extras.providers import certainly_prove_iter

async for r in certainly_prove_iter(
    items=[{"requirement_text": "Nat.add_comm"}, {"requirement_text": "Nat.add_assoc"}],
    response_format={"type":"json_object"},
    concurrency=4,
):
    if r["ok"]:
        print("ok", r["content"])
    else:
        print("err", r["status"], r["error"])
```

- As-completed iterator (simplified, no repair loop):
```python
from scillm.extras.providers import certainly_prove_simple_iter

async for r in certainly_prove_simple_iter(
    items=[{"requirement_text": "Nat.add_comm"}, {"requirement_text": "Nat.add_assoc"}],
    response_format={"type":"json_object"},
    concurrency=4,
):
    payload = (r.get("response", {}).get("additional_kwargs", {}) or {}).get("certainly", {})
    results = payload.get("results", [])
    if r.get("ok"):
        print("ok", results[0].get("status"))
    else:
        print("err", r.get("status"), r.get("error"), results[0].get("explanation"))
```

Debugging quick-guide (Chutes)
- Text sanity (JSON echo):
```
curl -sS -H "Authorization: Bearer $CHUTES_API_KEY" -H 'Content-Type: application/json' \
  -d '{"model":"'"$CHUTES_MODEL_ID"'","messages":[{"role":"user","content":"Return only {\"ok\":true} as JSON."}],"response_format":{"type":"json_object"},"max_tokens":64,"temperature":0}' \
  "$CHUTES_API_BASE/chat/completions"
```
Expect HTTP 200 and body containing `"ok":true`.
- Multimodal sanity (remote image URL, still returns JSON):
```
curl -sS -H "Authorization: Bearer $CHUTES_API_KEY" -H 'Content-Type: application/json' \
  -d '{"model":"'"$CHUTES_VLM_MODEL"'","messages":[{"role":"user","content":[{"type":"text","text":"Describe the image in one JSON object with key desc"},{"type":"image_url","image_url":{"url":"https://picsum.photos/seed/scillm/256/256"}}]}],"response_format":{"type":"json_object"},"max_tokens":128,"temperature":0}' \
  "$CHUTES_API_BASE/chat/completions"
```
Expect HTTP 200 and a JSON object (e.g., `{"desc":"..."}`). If these fail (non‑200 or empty), the upstream is down; parallel_acompletions will also fail.

Packaging expectations
- `pip install scillm>=1.77.3` ships the paved helpers (`scillm.paved.*`) **and** the `chutes.middleware.*` modules they depend on. If an ImportError still occurs, upgrade or reinstall the wheel instead of patching a venv manually.
- The `openai_like` provider now accepts Bearer-only auth. Pass `api_key=` and SciLLM will project the token into the correct header (Bearer or `x-api-key`) for Chutes.

Step 07 (Knowledge) Requirements
- Preflight: `sanity_preflight(api_base=..., api_key=..., model=..., parallel=SCILLM_PREFLIGHT_PARALLEL|3, wall_time_s=SCILLM_PREFLIGHT_WALL_S|30)`
  - If Step 07 runs in an async worker, wrap it: `await asyncio.to_thread(sanity_preflight, api_base=..., api_key=..., model=..., parallel=..., wall_time_s=...)`
- On failure: return `preflight_details` (dict) to the pipeline summary.
- Runtime calls: `scillm.acompletion(..., api_key=CHUTES_API_KEY, custom_llm_provider="openai_like", response_format={"type":"json_object"})`

Simple Wrappers (scillm.paved)

For quick one-off completions without boilerplate, use the simple wrappers:

```python
from scillm.paved import chat, chat_json, analyze_image, analyze_image_json

# Text completion
answer = await chat("What is the capital of France?")

# JSON response (returns parsed dict)
data = await chat_json('Return {"name": "Alice", "age": 25}')

# Image analysis
desc = await analyze_image("https://example.com/photo.jpg", "Describe this")

# Image + JSON
data = await analyze_image_json("receipt.jpg", 'Extract {"total": number}')
```

These wrappers default to `localhost:4001` + `sk-dev-proxy-123` (the Docker proxy).
Override via env vars (`SCILLM_API_BASE`, `SCILLM_PROXY_KEY`, `SCILLM_MODEL`) or function kwargs.

For batch processing (many items), use `parallel_acompletions_proxy` (Section C above).

Skills for AI Agents

scillm bundles skills that can be installed into projects for use by Claude Code, Codex, Gemini, etc.

```bash
# List available skills
python -m scillm.skills list

# Install all skills to .skills/ (agent-agnostic location)
python -m scillm.skills install --all

# Install to specific location
python -m scillm.skills install --all --target .claude/skills
```

Skills are COPIED, not symlinked. Re-run install to update.

Current skills:
- `certainly-prover`: Lean4 theorem proving via scillm
- `scillm-completions`: LLM completions (text, JSON, vision, batch)

Allowed Surfaces (CHUTES / OpenAI‑compatible)
- `scillm.acompletion / scillm.completion`
- `scillm.paved.chat / chat_json / analyze_image / analyze_image_json` (simple wrappers)
- `scillm.paved.sanity_preflight / list_models_openai_like / chutes_chat_json / chutes_router_json`
- `scillm.Router` (lightweight passthrough; do not wrap)

Enforcement (Grep Guards)

These guards apply to SDK code (Section A) only. Proxy HTTP calls (Section B) are allowed.

- Patterns that must not appear in **SDK code** (code that imports scillm):
  - `extra_headers={.*Authorization.*}` or `extra_headers={.*x-api-key.*}`
  - Direct calls to `CHUTES_API_BASE` bypassing the proxy
- Patterns that ARE allowed everywhere:
  - `httpx.post("http://localhost:4001/v1/chat/completions", ...)` -- proxy call (Section B)
  - `openai.OpenAI(base_url="http://localhost:4001/v1", ...)` -- proxy call (Section B)
  - `curl http://localhost:4001/...` -- proxy call in scripts/docs

Quick Self‑Check
- Allowed (SDK path):
  ```python
  from scillm import acompletion
  r = await acompletion(model="text",
                        api_base="http://localhost:4001",
                        api_key="sk-dev-proxy-123",
                        messages=[{"role":"user","content":"hi"}],
                        response_format={'type':'json_object'},
                        timeout=30)
  ```
- Allowed (proxy path — for code without scillm pip-installed):
  ```python
  resp = httpx.post("http://localhost:4001/v1/chat/completions",
                    headers={"Authorization": "Bearer sk-dev-proxy-123"},
                    json={"model": "text", "messages": [{"role": "user", "content": "hi"}]})
  ```
- Disallowed (direct provider bypass):
  ```python
  # ❌ calling Chutes directly, bypassing the proxy
  requests.post(f"{CHUTES_API_BASE}/chat/completions",
                headers={"Authorization": f"Bearer {CHUTES_API_KEY}"}, json=payload)
  ```

CI / PR Review Guidance
- The key question is: **does this code call the proxy (localhost:4001) or bypass it?**
- Calling the proxy via any HTTP client is fine. Calling Chutes/OpenRouter/DeepSeek directly is not.
- For SDK code: `rg -n "extra_headers=|CHUTES_API_BASE.*acompletion" experiments/devops -g '!**/.venv/**'`

Exceptions
- None for CHUTES/SciLLM. If a true exception is required, file a short design note and add a temporary allowlist entry to a local `EXCEPTIONS.md` with an expiration date.

Change History
- 2026‑03‑11: Added Section C (batch calls via `parallel_acompletions_proxy`). Documented three message formats (plain string, convenience fields, OpenAI array). Added source grounding and JSON validation examples. Fixed simple wrappers to show proxy defaults (localhost:4001), not OpenRouter.
- 2026‑03‑07: Proxy-first rewrite. Added Section B for code outside scillm's venv. Relaxed grep guards to allow httpx/openai SDK calls to localhost:4001. Clarified that direct provider calls (not proxy calls) are what's banned.
- 2026‑01‑11: Added simple wrappers (chat, chat_json, analyze_image, analyze_image_json) and skills system. Skills are agent-agnostic (Claude, Codex, Gemini) and install to .skills/ by default.
- 2026‑01‑10: Added minimal runnable certainly script (copy-paste-run) with prerequisites. Documented architectural decision: scillm as main caller, certainly_min CLI for debugging only.
- 2026‑01‑03: Reinforced canonical surfaces, JSON strict guidance, iterator JSON repair parity, and Certainly/Lean4 paved‑path examples.
- 2025‑11‑09: Initial version. Codified paved helpers and strict “no manual headers / no raw HTTP” policy for DevOps.
- 2025‑11‑10: Documented bundled middleware + Bearer-only provider so DevOps doesn’t patch venvs manually.
- 2025‑12‑19: Clarified `parallel_acompletions` request shape and progress-friendly `batch_acompletions_iter` example.
- 2025‑12‑31: Added Certainly/Lean4 signature, primary results path, and clarified item/flags usage.
