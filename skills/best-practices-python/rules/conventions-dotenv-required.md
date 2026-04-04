---
title: Load dotenv at module level before any os.getenv() calls
impact: CRITICAL
impactDescription: skills silently fail when API keys are in .env but never loaded
tags: conventions, dotenv, environment, config
---

## Load dotenv before reading environment variables

Every Python script that reads environment variables with `os.getenv()` or `os.environ`
MUST load `.env` files at module level, **before** the first `os.getenv()` call.

Without this, scripts work when launched from a parent that already loaded dotenv
(e.g., orchestrator) but fail silently when run standalone or via `run.sh`.

**Incorrect:**
```py
import os
from pathlib import Path

# BUG: os.getenv returns None if .env was not loaded by a parent process
api_key = os.getenv("MY_API_KEY")
```

**Correct (preferred — use shared helper):**
```py
import os
import sys
from pathlib import Path

# Load dotenv FIRST
SKILLS_DIR = Path(__file__).resolve().parents[1]
if str(SKILLS_DIR) not in sys.path:
    sys.path.append(str(SKILLS_DIR))

try:
    from dotenv_helper import load_env as _load_env
except Exception:
    def _load_env():
        try:
            from dotenv import load_dotenv, find_dotenv
            load_dotenv(find_dotenv(usecwd=True), override=False)
        except Exception:
            pass

_load_env()

# NOW safe to read env vars
api_key = os.getenv("MY_API_KEY")
```

**Correct (standalone — no shared helper available):**
```py
import os
from pathlib import Path

from dotenv import load_dotenv, find_dotenv

load_dotenv(find_dotenv(usecwd=True), override=False)
# Fallback: walk up to repo root .env
_root_env = Path(__file__).resolve().parent.parent.parent / ".env"
if _root_env.exists():
    load_dotenv(_root_env, override=False)

# NOW safe to read env vars
api_key = os.getenv("MY_API_KEY")
```

### Why `override=False`?

- Explicit env vars (set in shell) take precedence over `.env` file values.
- Prevents `.env` from silently overwriting a user's intentional configuration.

### Why `usecwd=True`?

- `find_dotenv()` walks up from the **current working directory** (not the script location).
- When skills are called via `subprocess.run(cwd=skill_dir)`, `usecwd=True` finds the
  nearest `.env` relative to that skill directory.
- The explicit fallback to the repo root `.env` covers the case where `find_dotenv` fails.

### Notes
- Add `python-dotenv>=1.0.0` to the script's inline dependencies or `pyproject.toml`.
- The shared `dotenv_helper.py` lives at `.pi/skills/dotenv_helper.py` — prefer importing it.
- This rule is enforced by `sanity/lint_dotenv.sh`.
- Never call `os.getenv()` at module level before `load_dotenv()` unless the variable is
  truly optional (like `CREATE_IMAGE_ENABLE_SAFE_DEFAULTS` with an explicit default).
