---
title: Do not perform blocking I/O in the event loop
impact: HIGH
impactDescription: prevents latency spikes and timeouts under load
tags: async, io, performance
---

## Do not perform blocking I/O in the event loop

**Incorrect:**
```py
import requests

async def handler(url: str) -> str:
    return requests.get(url, timeout=10).text
```

**Correct:**
```py
import asyncio
import httpx

async def handler(url: str) -> str:
    async with httpx.AsyncClient(timeout=httpx.Timeout(10.0)) as client:
        r = await client.get(url)
        r.raise_for_status()
        return r.text

# If forced to use a sync library:
# return await asyncio.to_thread(lambda: blocking_call())
```

### FastAPI: use plain `def` for sync-only endpoints

In FastAPI, `async def` runs on the event loop. `def` (without async) automatically runs in a thread pool. **If your endpoint only calls sync libraries (python-arango, requests, CPU-bound code), use `def` not `async def`.**

**Incorrect — blocks the event loop for every request:**
```py
@router.get("/items")
async def list_items():
    db = get_db()  # sync
    return list(db.aql.execute("FOR d IN items RETURN d"))  # sync
```

**Correct — FastAPI auto-threads it:**
```py
@router.get("/items")
def list_items():
    db = get_db()
    return list(db.aql.execute("FOR d IN items RETURN d"))
```

**When to keep `async def`:**
- Endpoint uses `await` (httpx.AsyncClient, asyncio.to_thread, etc.)
- Endpoint mixes async and sync via explicit `asyncio.to_thread()` calls

### Notes
- Prefer `httpx.AsyncClient` for async HTTP.
- If unavoidable, offload sync work via `asyncio.to_thread`.
- **python-arango is entirely synchronous** — every `db.aql.execute()` blocks. Use `def` endpoints or `asyncio.to_thread()`.
- This applies to ALL sync DB drivers, classifier inference, file I/O, and CPU-bound code.
