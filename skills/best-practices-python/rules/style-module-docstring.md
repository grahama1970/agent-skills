---
title: Required Module Docstrings
impact: HIGH
impactDescription: Improves discoverability and understanding for AI agents and humans
tags: style, documentation, maintainability
---

## Required Module Docstrings

**Impact: HIGH (Improves discoverability and understanding for AI agents and humans)**

Every Python module must begin with a clear docstring describing its purpose, inputs, outputs, and failure modes. This helps both humans and AI agents understand the module's role without reading all the code.

**Incorrect (missing or vague docstring):**

```python
# user_service.py
import requests

def get_user(user_id):
    # No module docstring - unclear what this module does
    response = requests.get(f"/api/users/{user_id}")
    return response.json()
```

**Correct (clear module docstring):**

```python
# user_service.py
"""
User service for fetching and managing user data.

This module provides functions for:
- Fetching user profiles from the API
- Updating user metadata
- Managing user permissions

Inputs:
- user_id (int): Unique user identifier
- API credentials via USERAPI_KEY environment variable

Outputs:
- User objects with id, name, email, permissions

Failure modes:
- Raises UserNotFoundError if user doesn't exist
- Raises APIError on network/API failures
- Returns None for soft failures (e.g., missing optional data)

Dependencies:
- Requires httpx for API calls
- Requires USERAPI_KEY in environment
"""
import httpx
from loguru import logger

def get_user(user_id: int) -> dict:
    """Fetch user profile from API."""
    response = httpx.get(f"/api/users/{user_id}")
    response.raise_for_status()
    return response.json()
```

**Module docstring template:**

```python
"""
{One-line summary of module purpose}

This module provides:
- {Key function 1}
- {Key function 2}
- {Key function 3}

Inputs:
- {Expected inputs, config, environment variables}

Outputs:
- {What the module produces}

Failure modes:
- {How it fails and what exceptions it raises}

Dependencies:
- {External dependencies, APIs, services}
"""
```

Reference: [PEP 257 - Docstring Conventions](https://peps.python.org/pep-0257/)
