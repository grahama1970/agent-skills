---
title: Limit concurrency when fan-out is possible
impact: MEDIUM
impactDescription: prevents resource exhaustion and rate-limit storms
tags: async, concurrency
---

## Limit concurrency when fan-out is possible

**Incorrect:**
```py
async def fetch_all(urls):
    return await asyncio.gather(*(fetch(u) for u in urls))
```

**Correct:**
```py
import asyncio

async def fetch_all(urls, limit: int = 10):
    sem = asyncio.Semaphore(limit)

    async def bounded(u):
        async with sem:
            return await fetch(u)

    return await asyncio.gather(*(bounded(u) for u in urls))
```

### Notes
- Constrain concurrency for network/disk/CPU fan-out paths.
