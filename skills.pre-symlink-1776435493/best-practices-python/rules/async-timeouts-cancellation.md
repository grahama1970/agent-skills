---
title: Use timeouts and handle cancellation explicitly
impact: HIGH
impactDescription: prevents hung tasks and resource leaks
tags: async, timeouts, cancellation
---

## Use timeouts and handle cancellation explicitly

**Incorrect:**
```py
async def fetch():
    return await slow_call()
```

**Correct:**
```py
import asyncio

async def fetch():
    try:
        return await asyncio.wait_for(slow_call(), timeout=5)
    except asyncio.TimeoutError:
        return None
```

### Notes
- Background tasks must be cancelled/awaited on shutdown.
