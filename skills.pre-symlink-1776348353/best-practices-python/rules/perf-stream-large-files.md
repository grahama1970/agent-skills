---
title: Stream large files instead of reading into memory
impact: MEDIUM
impactDescription: prevents memory spikes and improves throughput
tags: performance, io
---

## Stream large files instead of reading into memory

**Incorrect:**
```py
data = Path(path).read_bytes()
```

**Correct:**
```py
from pathlib import Path

p = Path(path)
with p.open("rb") as f:
    for chunk in iter(lambda: f.read(1024 * 1024), b""):
        handle_chunk(chunk)
```

### Notes
- If you need whole-file operations, justify it and cap file sizes.
