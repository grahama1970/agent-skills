---
title: Never use bare except or silently swallow exceptions
impact: CRITICAL
impactDescription: prevents hidden failures and corrupted state; improves debuggability
tags: correctness, exceptions, reliability
---

## Never use bare except or silently swallow exceptions

**Incorrect:**
```py
try:
    do_work()
except Exception:
    pass
```

**Correct:**
```py
from loguru import logger

try:
    do_work()
except (TimeoutError, ConnectionError) as e:
    logger.warning("transient failure: {}", e)
    raise
```

### Notes
- Catch the narrowest exception set you can justify.
- If continuing, log with context and return a typed failure result.
