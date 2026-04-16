---
title: Do not use print() in library/service code
impact: MEDIUM
impactDescription: keeps output structured and controllable; avoids noisy stdout
tags: conventions, logging
---

## Do not use print() in library/service code

**Incorrect:**
```py
print("starting")
```

**Correct:**
```py
from loguru import logger

logger.info("starting")
```

### Notes
- Use `typer.echo` only for user-facing CLI output.
- Use Loguru for logs.
