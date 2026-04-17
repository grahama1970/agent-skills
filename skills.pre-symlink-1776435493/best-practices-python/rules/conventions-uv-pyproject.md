---
title: Use uv + pyproject.toml for dependencies and tooling
impact: HIGH
impactDescription: keeps installs reproducible and configuration centralized
tags: conventions, packaging, uv, pyproject
---

## Use uv + pyproject.toml

**Incorrect:**
```py
# requirements.txt + scattered tool configs
```

**Correct:**
```py
# pyproject.toml is the single source of truth
# uv manages installs and lockfile
```

### Notes
- Avoid introducing alternative dependency managers.
- Keep tool config (ruff/pytest/etc.) in pyproject when possible.
