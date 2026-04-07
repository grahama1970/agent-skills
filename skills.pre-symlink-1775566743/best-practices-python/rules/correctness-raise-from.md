---
title: Use raise ... from e to preserve exception context
impact: HIGH
impactDescription: preserves causal chain and prevents misleading tracebacks
tags: correctness, exceptions, debugging
---

## Use `raise ... from e` to preserve exception context

**Incorrect:**
```py
try:
    parse(payload)
except ValueError:
    raise RuntimeError("bad payload")
```

**Correct:**
```py
try:
    parse(payload)
except ValueError as e:
    raise RuntimeError("bad payload") from e
```

### Notes
- Add context; don't erase root cause.
