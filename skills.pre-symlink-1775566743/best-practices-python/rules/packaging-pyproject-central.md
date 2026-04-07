---
title: Centralize tooling config in pyproject.toml
impact: MEDIUM
impactDescription: reduces config drift and improves reproducibility
tags: packaging, pyproject
---

## Centralize tooling config in pyproject.toml

**Incorrect:**
```py
# flake8.cfg + isort.cfg + pytest.ini scattered
```

**Correct:**
```py
# Use pyproject.toml for tool configuration where supported
```

### Notes
- Prefer a single canonical config file.
- Keep per-tool config minimal and consistent.
