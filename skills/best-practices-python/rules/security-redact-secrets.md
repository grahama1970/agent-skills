---
title: Never log secrets or raw credentials
impact: HIGH
impactDescription: prevents credential leakage in logs and traces
tags: security, logging
---

## Never log secrets or raw credentials

**Incorrect:**
```py
from loguru import logger

logger.info("token={}", token)
```

**Correct:**
```py
from loguru import logger

logger.info("auth token present={} len={}", bool(token), len(token) if token else 0)
```

### Notes
- Redact tokens/passwords/keys; log booleans and lengths instead.
