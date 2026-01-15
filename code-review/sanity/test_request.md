# Sanity Check: Simple Function Fix

## Repository and branch

- **Repo:** `test/sanity-check`
- **Branch:** `main`
- **Paths of interest:**
  - `example.py`

## Summary

This is a sanity check to verify the code review provider is working correctly.
The task is to review a simple Python function and suggest improvements.

## Code to Review

```python
def add_numbers(a, b):
    # TODO: add input validation
    return a + b

def greet(name):
    print("Hello " + name)
    return None
```

## Objectives

### 1. Review the code

- Identify any issues or improvements
- Suggest type hints
- Note any missing error handling

## Constraints for the patch

- **Output format:** Unified diff only, inline inside a single fenced code block.
- Include a one-line commit subject on the first line of the patch.
- No extra commentary outside the diff block.

## Acceptance criteria

- Type hints added to function signatures
- Return type for greet() should be None explicitly or void
- Brief clarifying questions answered if any

## Deliverable

Reply with a single fenced code block containing a unified diff.
