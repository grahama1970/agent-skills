---
title: Keep return types stable; avoid returning different shapes
impact: HIGH
impactDescription: reduces caller complexity and prevents runtime type confusion
tags: correctness, interfaces
---

## Keep return types stable; avoid returning different shapes

**Incorrect:**
```py
def get_user(id: str):
    if not id:
        return None
    return {"id": id}
```

**Correct:**
```py
from dataclasses import dataclass

@dataclass(frozen=True)
class User:
    id: str

def get_user(id: str) -> User | None:
    if not id:
        return None
    return User(id=id)
```

### Notes
- Prefer typed results (`T | None`) over untyped dicts at module boundaries.
