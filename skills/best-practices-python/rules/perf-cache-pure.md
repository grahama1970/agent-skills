---
title: Cache expensive pure computations
impact: MEDIUM
impactDescription: avoids repeated work for identical inputs
tags: performance, caching
---

## Cache expensive pure computations

**Incorrect:**
```py
def render(user_id: str) -> str:
    return compute_expensive(user_id)
```

**Correct:**
```py
from functools import lru_cache

@lru_cache(maxsize=1024)
def compute_cached(user_id: str) -> str:
    return compute_expensive(user_id)

def render(user_id: str) -> str:
    return compute_cached(user_id)
```

### Notes
- Only cache pure functions (no IO, time, randomness, or global mutation).
