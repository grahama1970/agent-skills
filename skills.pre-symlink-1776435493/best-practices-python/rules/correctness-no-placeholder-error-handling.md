---
title: Never leave placeholder or TODO error handling in production code
impact: CRITICAL
impactDescription: placeholder handlers silently swallow catastrophic failures, masking data loss, corruption, and unrecoverable states
tags: correctness, exceptions, reliability, todo
---

## Never leave placeholder or TODO error handling in production code

Placeholder comments inside `except` blocks (e.g., "in a real implementation", "TODO: handle this properly") are the single most dangerous pattern in a codebase. They turn catastrophic failures into silent corruption. The code *looks* like it handles the error. It does not.

**Incorrect:**
```py
try:
    result = db.execute(query)
except Exception as e:
    # TODO: handle database errors properly
    pass

try:
    response = httpx.post(url, json=payload)
except Exception:
    # In a real implementation we would retry here
    result = {}

try:
    data = json.loads(raw)
except json.JSONDecodeError:
    data = {}  # FIXME: should validate input

try:
    model.save(path)
except OSError:
    logger.debug(f"Save failed: {e}")  # placeholder - will fix later
```

**Correct:**
```py
from loguru import logger

try:
    result = db.execute(query)
except (OperationalError, IntegrityError) as e:
    logger.error("query failed: {}", e)
    raise

try:
    response = httpx.post(url, json=payload, timeout=30)
except httpx.HTTPStatusError as e:
    logger.warning("POST {} returned {}", url, e.response.status_code)
    raise
except httpx.ConnectError as e:
    logger.error("connection failed to {}: {}", url, e)
    raise

try:
    data = json.loads(raw)
except json.JSONDecodeError as e:
    raise ValueError(f"invalid JSON at position {e.pos}: {e.msg}") from e

try:
    model.save(path)
except OSError as e:
    logger.error("model save failed: {path}", path=path)
    raise
```

### Detection patterns

Flag any `except` block containing these patterns:

- `# TODO` / `# FIXME` / `# HACK` / `# XXX`
- `# placeholder` / `# stub` / `# temporary`
- `"in a real implementation"` / `"in production"` / `"should be"` / `"will fix"`
- `pass` with no logging or re-raise
- `= {}` / `= []` / `= None` / `= ""` as the only handler (silent default)
- `logger.debug` for errors that should be `logger.error` or `logger.warning`

### Why this is CRITICAL

1. **Silent data loss**: A swallowed database error means writes are silently dropped. Users see success. Data is gone.
2. **Cascading corruption**: Returning `{}` or `None` from a failed operation propagates invalid state downstream. The real crash happens 50 lines later with an incomprehensible `KeyError`.
3. **Invisible in testing**: These handlers pass all tests because the test never triggers the error path. The failure only manifests in production under load.
4. **False confidence**: The `try/except` wrapper signals "this error is handled" to code reviewers. It is not.

### Remediation

When you find a placeholder handler:

1. **Identify the failure mode**: What actually goes wrong? Network timeout? Invalid data? Missing file?
2. **Narrow the exception**: Replace `except Exception` with the specific exceptions that can occur.
3. **Choose a strategy**: Re-raise, retry with backoff, return a typed error, or degrade gracefully with proper logging.
4. **Log at the right level**: Transient failures are `warning`. Permanent failures are `error`. Never use `debug` for error paths.
5. **Add a test**: Write a test that triggers the error path and verifies the handler behaves correctly.

### Notes
- Run `grep -rn "# TODO\|# FIXME\|# HACK\|placeholder\|stub\|will fix" --include="*.py" | grep -i "except\|try"` to find candidates.
- Every `except` block must either re-raise, return a typed error value, or log at `warning`/`error` level with context.
- If you genuinely cannot handle the error yet, use `raise NotImplementedError("description")` instead of a silent placeholder. At least it fails loudly.
