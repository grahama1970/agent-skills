---
title: Prefer httpx.AsyncClient for async HTTP
impact: MEDIUM
impactDescription: reduces thread offloading and improves throughput
tags: async, httpx
---

## Prefer httpx.AsyncClient for async HTTP

**Incorrect:**
```py
import asyncio
import httpx

async def get(url):
    return await asyncio.to_thread(lambda: httpx.get(url).text)
```

**Correct:**
```py
import httpx

async def get(url: str) -> str:
    async with httpx.AsyncClient(timeout=httpx.Timeout(10.0)) as client:
        r = await client.get(url)
        r.raise_for_status()
        return r.text
```

### Notes
- Use one AsyncClient per scope to reuse connections when appropriate.
