---
title: Commit uv lockfile for reproducible installs
impact: MEDIUM
impactDescription: ensures consistent dependency resolution across environments
tags: packaging, uv
---

## Commit uv lockfile for reproducible installs

**Incorrect:**
```py
# No lockfile committed
```

**Correct:**
```py
# Commit uv.lock (or your uv lock artifact) to version control
```

### Notes
- Treat lockfiles as source-of-truth for production parity.
