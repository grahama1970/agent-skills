---
title: Prefer functions over classes unless state is required
impact: MEDIUM
impactDescription: reduces indirection and improves testability
tags: conventions, design
---

## Prefer functions over classes unless state is required

**Incorrect:**
```py
class Processor:
    def __init__(self):
        pass
    def run(self, x: int) -> int:
        return x + 1
```

**Correct:**
```py
def process(x: int) -> int:
    return x + 1

# If state is required:
from dataclasses import dataclass

@dataclass
class Processor:
    cache: dict[str, int]

    def run(self, key: str) -> int:
        return self.cache[key]
```

### Notes
- Use classes for stateful components (clients, caches, shared config).
- Prefer dataclasses for explicit state.
