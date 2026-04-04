---
title: Only call asyncio.run() once per process
impact: CRITICAL
impactDescription: nested asyncio.run() raises RuntimeError and breaks the entire program
tags: async, asyncio, correctness
---

## Only call asyncio.run() once per process

`asyncio.run()` creates and destroys an event loop. Calling it from inside
an already-running loop (or nesting calls) raises `RuntimeError: This event
loop is already running`. Structure code so a single `asyncio.run()` in
`if __name__ == "__main__"` drives all async work.

**Incorrect:**
```py
import asyncio

async def fetch_data():
    ...

async def validate():
    ...

def process():
    data = asyncio.run(fetch_data())      # first loop
    result = asyncio.run(validate())      # second loop — wasteful
    return result

async def run_pipeline():
    # Nested asyncio.run() inside an already-running loop — CRASHES
    result = asyncio.run(validate())      # RuntimeError!
    return result
```

**Correct:**
```py
import asyncio

async def fetch_data():
    ...

async def validate():
    ...

async def process_async():
    """All async work composed via await, not asyncio.run()."""
    data = await fetch_data()
    result = await validate()
    return result

def process():
    """Sync wrapper — single asyncio.run() entry point."""
    return asyncio.run(process_async())

# Only one asyncio.run() in the entire process
if __name__ == "__main__":
    asyncio.run(process_async())
```

### Notes
- `asyncio.run()` must appear **once** per process, typically in `if __name__ == "__main__"` or a single sync wrapper function.
- Compose async work with `await`, not by spawning new event loops.
- If you need to call async code from sync code that may itself be called from async context, use `asyncio.get_event_loop().run_until_complete()` or restructure to keep the caller async.
- Libraries like `nest_asyncio` exist but are a code smell — restructure instead.
