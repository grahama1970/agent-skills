---
title: Maximum 800 Lines Per File
impact: HIGH
impactDescription: Improves maintainability and reduces cognitive load
tags: style, maintainability, readability
---

## Maximum 800 Lines Per File

**Impact: HIGH (Improves maintainability and reduces cognitive load)**

No Python file should exceed 800 lines. This constraint forces modular design, prevents god objects, and makes code easier to understand, test, and refactor.

**Incorrect (monolithic file):**

```python
# services/user_service.py - 1500 lines
# All user logic in one file:
# - Authentication (200 lines)
# - Profile management (300 lines)
# - Permissions (400 lines)
# - Notifications (300 lines)
# - Analytics (300 lines)

class UserService:
    def authenticate(self, username, password):
        # ... 50 lines of auth logic
        pass

    def update_profile(self, user_id, data):
        # ... 80 lines of profile logic
        pass

    # ... 20+ more methods
```

**Correct (modular files under 800 lines each):**

```python
# services/user/auth.py - 200 lines
"""User authentication and session management."""

def authenticate_user(username: str, password: str) -> AuthResult:
    """Authenticate user credentials."""
    # ... focused auth logic
    pass

# services/user/profile.py - 250 lines
"""User profile CRUD operations."""

def update_profile(user_id: int, data: dict) -> User:
    """Update user profile data."""
    # ... focused profile logic
    pass

# services/user/permissions.py - 300 lines
"""User permissions and role management."""

def check_permission(user_id: int, resource: str, action: str) -> bool:
    """Check if user has permission for action."""
    # ... focused permission logic
    pass

# services/user/notifications.py - 200 lines
"""User notification delivery."""

# services/user/analytics.py - 250 lines
"""User activity analytics."""
```

**How to split large files:**

1. **Group by responsibility** - auth, profile, permissions, etc.
2. **Extract utilities** - move helper functions to `utils/` modules
3. **Create domain modules** - user operations, admin operations, etc.
4. **Use packages** - `services/user/__init__.py` can re-export public APIs

Reference: [Clean Code: Small Functions](https://martinfowler.com/bliki/FunctionLength.html)
