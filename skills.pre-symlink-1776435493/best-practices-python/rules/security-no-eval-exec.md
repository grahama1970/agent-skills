---
title: Never use eval/exec on untrusted input
impact: CRITICAL
impactDescription: prevents arbitrary code execution
tags: security, code-injection
---

## Never use eval/exec on untrusted input

**Incorrect:**
```py
def run(expr: str) -> int:
    return eval(expr)
```

**Correct:**
```py
import ast

def run(expr: str) -> int:
    node = ast.parse(expr, mode="eval")
    # validate allowed nodes here
    return int(eval(compile(node, "<expr>", "eval"), {"__builtins__": {}}))
```

### Notes
- Prefer dedicated parsers; if you must evaluate, restrict the grammar and environment aggressively.
