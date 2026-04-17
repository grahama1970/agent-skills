---
title: Use logger.exception in exception handlers
impact: MEDIUM
impactDescription: preserves stack traces and makes failures actionable
tags: logging, exceptions
---

## Use logger.exception in exception handlers

**Incorrect:**
```py
from loguru import logger

try:
    do_work()
except Exception as e:
    logger.error("failed: {}", e)
```

**Correct:**
```py
from loguru import logger

try:
    do_work()
except Exception:
    logger.exception("failed during do_work")
    raise
```

### Notes
- Use exception logs sparingly; avoid dumping huge payloads.
