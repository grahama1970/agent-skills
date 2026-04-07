---
title: Use Loguru for Logging
impact: MEDIUM
impactDescription: Simplifies logging setup and provides better defaults
tags: conventions, logging, observability
---

## Use Loguru for Logging

**Impact: MEDIUM (Simplifies logging setup and provides better defaults)**

Use Loguru for all logging instead of Python's built-in logging module. Loguru provides better defaults, simpler API, and automatic context capture without boilerplate configuration.

**Incorrect (using built-in logging):**

```python
import logging

# Requires manual configuration
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def process_user(user_id):
    logger.info(f"Processing user {user_id}")
    try:
        result = fetch_data(user_id)
        logger.info(f"Processed user {user_id}")
    except Exception as e:
        logger.error(f"Failed to process user {user_id}: {e}")
        raise
```

**Correct (using Loguru):**

```python
from loguru import logger

def process_user(user_id: int) -> dict:
    """Process user data with automatic context logging."""
    logger.info("Processing user {user_id}", user_id=user_id)
    try:
        result = fetch_data(user_id)
        logger.info("Processed user {user_id}", user_id=user_id)
        return result
    except Exception as e:
        logger.exception("Failed to process user {user_id}", user_id=user_id)
        raise
```

**Loguru benefits:**

1. **No configuration needed** - works out of the box
2. **Automatic exception tracing** - `logger.exception()` captures full traceback
3. **Structured logging** - pass variables as kwargs for JSON output
4. **Better formatting** - colors and readable output by default
5. **Easy file rotation** - `logger.add("file.log", rotation="500 MB")`

**Structured logging example:**

```python
from loguru import logger

logger.info(
    "User action completed",
    user_id=user_id,
    action="update_profile",
    duration_ms=duration,
    success=True
)
# Output: 2024-01-15 10:30:45 | INFO | User action completed | user_id=123 action=update_profile duration_ms=45 success=True
```

**Configuration (optional):**

```python
# Remove default handler and add custom one
logger.remove()
logger.add(
    sys.stderr,
    format="{time} | {level} | {message}",
    level="INFO"
)
logger.add("logs/app.log", rotation="1 day", retention="7 days")
```

Reference: [Loguru Documentation](https://loguru.readthedocs.io/)
