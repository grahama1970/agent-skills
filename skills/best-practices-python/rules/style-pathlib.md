---
title: Prefer pathlib.Path over os.path
impact: LOW
impactDescription: improves readability and cross-platform path handling
tags: style, io, pathlib
---

## Prefer pathlib.Path over os.path

**Incorrect:**
```py
import os

p = os.path.join(root, "data", "x.json")
```

**Correct:**
```py
from pathlib import Path

p = Path(root) / "data" / "x.json"
```

### Notes
- Use `Path` consistently inside modules.
