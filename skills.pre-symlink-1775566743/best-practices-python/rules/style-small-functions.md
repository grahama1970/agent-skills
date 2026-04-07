---
title: Prefer small single-purpose functions
impact: MEDIUM
impactDescription: improves readability and reduces bug surface area
tags: style, maintainability
---

## Prefer small single-purpose functions

**Incorrect:**
```py
def run_all(config):
    # 200 lines of mixed concerns
    ...
```

**Correct:**
```py
def run_all(config):
    items = load_items(config)
    validated = validate_items(items)
    return write_items(validated, config.out)
```

### Notes
- Split by: parse, validate, transform, side-effects.
- Add tests for each extracted function.
