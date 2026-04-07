---
title: Make time-dependent tests deterministic
impact: MEDIUM
impactDescription: prevents flakiness due to wall-clock timing
tags: testing, time, determinism
---

## Make time-dependent tests deterministic

**Incorrect:**
```py
def test_expiry():
    assert is_expired() is False
```

**Correct:**
```py
from datetime import datetime, timezone

def test_expiry():
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    assert is_expired(now=now) is False
```

### Notes
- Pass `now` as a parameter instead of calling `datetime.now()` inside logic.
