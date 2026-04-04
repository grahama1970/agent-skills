---
title: Validate and bound untrusted input early
impact: HIGH
impactDescription: prevents crashes, injection primitives, and resource exhaustion
tags: security, input-validation
---

## Validate and bound untrusted input early

**Incorrect:**
```py
def handle(q: str) -> int:
    return int(q)
```

**Correct:**
```py
def handle(q: str) -> int | None:
    if not q.isdigit():
        return None
    if len(q) > 9:
        return None
    return int(q)
```

### Notes
- Validate format, size, and allowed ranges at boundaries (HTTP, CLI, files).
