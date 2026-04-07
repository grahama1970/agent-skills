---
title: Bind contextual fields to logs
impact: MEDIUM
impactDescription: makes failures diagnosable across async tasks and batch jobs
tags: logging, loguru, observability
---

## Bind contextual fields to logs

**Incorrect:**
```py
from loguru import logger

logger.info("processing")
```

**Correct:**
```py
from loguru import logger

logger.bind(job_id=job_id, feed=feed).info("processing")
```

### Notes
- Prefer context fields over string concatenation.
