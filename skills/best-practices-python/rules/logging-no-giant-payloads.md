---
title: Avoid logging giant payloads; log summaries
impact: MEDIUM
impactDescription: prevents log bloat and accidental PII leakage
tags: logging, security
---

## Avoid logging giant payloads; log summaries

**Incorrect:**
```py
from loguru import logger

logger.debug("payload={} ", payload)
```

**Correct:**
```py
from loguru import logger

logger.debug("payload_len={} keys={}", len(payload), list(payload)[:10])
```

### Notes
- Never log secrets; prefer lengths, counts, IDs, and key subsets.
