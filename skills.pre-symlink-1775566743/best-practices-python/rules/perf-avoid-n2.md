---
title: Avoid accidental O(n^2) loops in hot paths
impact: MEDIUM
impactDescription: prevents slowdowns that scale poorly with input size
tags: performance, complexity
---

## Avoid accidental O(n^2) loops in hot paths

**Incorrect:**
```py
def join(users, profiles):
    out = []
    for u in users:
        p = next(p for p in profiles if p["id"] == u["id"])
        out.append((u, p))
    return out
```

**Correct:**
```py
def join(users, profiles):
    by_id = {p["id"]: p for p in profiles}
    return [(u, by_id[u["id"]]) for u in users if u["id"] in by_id]
```

### Notes
- Build indexes (`dict`/`set`) once, then do O(1) lookups.
