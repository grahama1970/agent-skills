---
title: Never use mutable default arguments
impact: HIGH
impactDescription: prevents shared state bugs across calls
tags: correctness, python-gotchas
---

## Never use mutable default arguments

**Incorrect:**
```py
def add(x: int, items: list[int] = []):
    items.append(x)
    return items
```

**Correct:**
```py
def add(x: int, items: list[int] | None = None) -> list[int]:
    if items is None:
        items = []
    items.append(x)
    return items
```

### Notes
- Use `None` sentinel defaults for lists/dicts/sets.
