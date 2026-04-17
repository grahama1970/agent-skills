---
title: Use httpx for HTTP requests (not requests)
impact: HIGH
impactDescription: supports async and consistent timeout behavior
tags: conventions, http, httpx
---

## Use httpx for HTTP requests

**Incorrect:**
```py
import requests

def fetch(url: str) -> dict:
    return requests.get(url).json()
```

**Correct:**
```py
import httpx

def fetch(url: str) -> dict:
    with httpx.Client(timeout=httpx.Timeout(10.0)) as client:
        r = client.get(url)
        r.raise_for_status()
        return r.json()
```

### Notes
- Always set timeouts.
- Use `raise_for_status()` unless intentionally handling status codes.
