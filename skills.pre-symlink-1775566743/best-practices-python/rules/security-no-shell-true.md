---
title: Avoid shell=True in subprocess calls
impact: CRITICAL
impactDescription: prevents command injection and quoting bugs
tags: security, subprocess
---

## Avoid `shell=True` in subprocess calls

**Incorrect:**
```py
import subprocess

subprocess.run(f"convert {src} {dst}", shell=True, check=True)
```

**Correct:**
```py
import subprocess

subprocess.run(["convert", src, dst], check=True)
```

### Notes
- If you must use a shell, treat all input as hostile and escape carefully.
- Prefer explicit argv lists.
