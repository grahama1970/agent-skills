---
title: Pin major dependency versions and document upgrades
impact: LOW
impactDescription: reduces surprise breakage from transitive updates
tags: packaging, dependencies
---

## Pin major dependency versions and document upgrades

**Incorrect:**
```py
# unbounded deps
```

**Correct:**
```py
# pin major versions and note rationale in pyproject
```

### Notes
- Keep upgrades intentional and test-backed.
