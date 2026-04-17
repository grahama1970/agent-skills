---
title: Avoid hidden global mutable state
impact: HIGH
impactDescription: prevents action-at-a-distance bugs and test interference
tags: correctness, design
---

## Avoid hidden global mutable state

**Incorrect:**
```py
CACHE = {}

def get(k):
    return CACHE.get(k)
```

**Correct:**
```py
from dataclasses import dataclass

@dataclass
class Cache:
    items: dict[str, str]

    def get(self, k: str) -> str | None:
        return self.items.get(k)
```

### Notes
- Pass state explicitly (as parameters or dataclass fields).
