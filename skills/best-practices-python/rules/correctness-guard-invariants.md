---
title: Validate invariants early and fail fast
impact: HIGH
impactDescription: prevents cascading errors and unclear downstream failures
tags: correctness, validation
---

## Validate invariants early and fail fast

**Incorrect:**
```py
def compute(x: int) -> int:
    return 100 // x
```

**Correct:**
```py
def compute(x: int) -> int:
    if x == 0:
        raise ValueError("x must be non-zero")
    return 100 // x
```

### Notes
- Prefer explicit checks at boundaries and before irreversible side-effects.
