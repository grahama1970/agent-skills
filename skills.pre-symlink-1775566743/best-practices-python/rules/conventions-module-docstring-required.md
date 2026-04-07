---
title: Begin every module with a clear module docstring
impact: HIGH
impactDescription: makes intent and I/O obvious to humans and agents
tags: conventions, documentation
---

## Begin every module with a clear module docstring

**Incorrect:**
```py
import os

def run():
    ...
```

**Correct:**
```py
"""Fetch and normalize incident feeds into ArangoDB.

Inputs:
- FEED_URL (env or CLI option)
- --since (ISO timestamp)

Outputs:
- Writes normalized records
- Exits non-zero on validation/write failures
"""

from __future__ import annotations

def run() -> None:
    ...
```

### Notes
- Include: purpose, inputs, outputs/side-effects, failure modes.
- Keep it short but specific.
