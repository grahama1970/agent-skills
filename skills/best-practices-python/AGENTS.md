# Python Best Practices (AGENTS)

This document is compiled from `rules/`. Apply categories in order: correctness → security → conventions → testing → async → perf → packaging → logging → style.


Tip: The most important house rules are in `conventions-` and `style-` (Loguru, Typer, httpx, uv/pyproject, module docstrings, max 800 LOC, sanity tests).


## correctness


---

### correctness-avoid-mutable-defaults

---
title: Never use mutable default arguments
impact: HIGH
impactDescription: prevents shared state bugs across calls
tags: correctness, python-gotchas
---

## Never use mutable default arguments

**Incorrect:**
```py
def add(x: int, items: list[int] = []):
    items.append(x)
    return items
```

**Correct:**
```py
def add(x: int, items: list[int] | None = None) -> list[int]:
    if items is None:
        items = []
    items.append(x)
    return items
```

### Notes
- Use `None` sentinel defaults for lists/dicts/sets.


---

### correctness-guard-invariants

---
title: Validate invariants early and fail fast
impact: HIGH
impactDescription: prevents cascading errors and unclear downstream failures
tags: correctness, validation
---

## Validate invariants early and fail fast

**Incorrect:**
```py
def compute(x: int) -> int:
    return 100 // x
```

**Correct:**
```py
def compute(x: int) -> int:
    if x == 0:
        raise ValueError("x must be non-zero")
    return 100 // x
```

### Notes
- Prefer explicit checks at boundaries and before irreversible side-effects.


---

### correctness-no-bare-except

---
title: Never use bare except or silently swallow exceptions
impact: CRITICAL
impactDescription: prevents hidden failures and corrupted state; improves debuggability
tags: correctness, exceptions, reliability
---

## Never use bare except or silently swallow exceptions

**Incorrect:**
```py
try:
    do_work()
except Exception:
    pass
```

**Correct:**
```py
from loguru import logger

try:
    do_work()
except (TimeoutError, ConnectionError) as e:
    logger.warning("transient failure: {}", e)
    raise
```

### Notes
- Catch the narrowest exception set you can justify.
- If continuing, log with context and return a typed failure result.


---

### correctness-no-implicit-global-state

---
title: Avoid hidden global mutable state
impact: HIGH
impactDescription: prevents action-at-a-distance bugs and test interference
tags: correctness, design
---

## Avoid hidden global mutable state

**Incorrect:**
```py
CACHE = {}

def get(k):
    return CACHE.get(k)
```

**Correct:**
```py
from dataclasses import dataclass

@dataclass
class Cache:
    items: dict[str, str]

    def get(self, k: str) -> str | None:
        return self.items.get(k)
```

### Notes
- Pass state explicitly (as parameters or dataclass fields).


---

### correctness-no-placeholder-error-handling

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


---

### correctness-raise-from

---
title: Use raise ... from e to preserve exception context
impact: HIGH
impactDescription: preserves causal chain and prevents misleading tracebacks
tags: correctness, exceptions, debugging
---

## Use `raise ... from e` to preserve exception context

**Incorrect:**
```py
try:
    parse(payload)
except ValueError:
    raise RuntimeError("bad payload")
```

**Correct:**
```py
try:
    parse(payload)
except ValueError as e:
    raise RuntimeError("bad payload") from e
```

### Notes
- Add context; don't erase root cause.


---

### correctness-return-types

---
title: Keep return types stable; avoid returning different shapes
impact: HIGH
impactDescription: reduces caller complexity and prevents runtime type confusion
tags: correctness, interfaces
---

## Keep return types stable; avoid returning different shapes

**Incorrect:**
```py
def get_user(id: str):
    if not id:
        return None
    return {"id": id}
```

**Correct:**
```py
from dataclasses import dataclass

@dataclass(frozen=True)
class User:
    id: str

def get_user(id: str) -> User | None:
    if not id:
        return None
    return User(id=id)
```

### Notes
- Prefer typed results (`T | None`) over untyped dicts at module boundaries.


## security


---

### security-no-eval-exec

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


---

### security-no-shell-true

---
title: Avoid shell=True in subprocess calls
impact: CRITICAL
impactDescription: prevents command injection and quoting bugs
tags: security, subprocess
---

## Avoid `shell=True` in subprocess calls

**Incorrect:**
```py
import subprocess

subprocess.run(f"convert {src} {dst}", shell=True, check=True)
```

**Correct:**
```py
import subprocess

subprocess.run(["convert", src, dst], check=True)
```

### Notes
- If you must use a shell, treat all input as hostile and escape carefully.
- Prefer explicit argv lists.


---

### security-redact-secrets

---
title: Never log secrets or raw credentials
impact: HIGH
impactDescription: prevents credential leakage in logs and traces
tags: security, logging
---

## Never log secrets or raw credentials

**Incorrect:**
```py
from loguru import logger

logger.info("token={}", token)
```

**Correct:**
```py
from loguru import logger

logger.info("auth token present={} len={}", bool(token), len(token) if token else 0)
```

### Notes
- Redact tokens/passwords/keys; log booleans and lengths instead.


---

### security-validate-untrusted-input

---
title: Validate and bound untrusted input early
impact: HIGH
impactDescription: prevents crashes, injection primitives, and resource exhaustion
tags: security, input-validation
---

## Validate and bound untrusted input early

**Incorrect:**
```py
def handle(q: str) -> int:
    return int(q)
```

**Correct:**
```py
def handle(q: str) -> int | None:
    if not q.isdigit():
        return None
    if len(q) > 9:
        return None
    return int(q)
```

### Notes
- Validate format, size, and allowed ranges at boundaries (HTTP, CLI, files).


---

### security-xml-safe-parsing

---
title: Use safe XML parsing for untrusted XML
impact: HIGH
impactDescription: prevents XML entity expansion and related attacks
tags: security, xml
---

## Use safe XML parsing for untrusted XML

**Incorrect:**
```py
import xml.etree.ElementTree as ET

ET.fromstring(xml_text)
```

**Correct:**
```py
from defusedxml import ElementTree as ET

ET.fromstring(xml_text)
```

### Notes
- Only parse XML if required; prefer JSON.
- If parsing untrusted XML, use defusedxml.


## conventions


---

### conventions-dotenv-required

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


---

### conventions-functions-over-classes

---
title: Prefer functions over classes unless state is required
impact: MEDIUM
impactDescription: reduces indirection and improves testability
tags: conventions, design
---

## Prefer functions over classes unless state is required

**Incorrect:**
```py
class Processor:
    def __init__(self):
        pass
    def run(self, x: int) -> int:
        return x + 1
```

**Correct:**
```py
def process(x: int) -> int:
    return x + 1

# If state is required:
from dataclasses import dataclass

@dataclass
class Processor:
    cache: dict[str, int]

    def run(self, key: str) -> int:
        return self.cache[key]
```

### Notes
- Use classes for stateful components (clients, caches, shared config).
- Prefer dataclasses for explicit state.


---

### conventions-httpx

---
title: Use httpx for HTTP requests (not requests)
impact: HIGH
impactDescription: supports async and consistent timeout behavior
tags: conventions, http, httpx
---

## Use httpx for HTTP requests

**Incorrect:**
```py
import requests

def fetch(url: str) -> dict:
    return requests.get(url).json()
```

**Correct:**
```py
import httpx

def fetch(url: str) -> dict:
    with httpx.Client(timeout=httpx.Timeout(10.0)) as client:
        r = client.get(url)
        r.raise_for_status()
        return r.json()
```

### Notes
- Always set timeouts.
- Use `raise_for_status()` unless intentionally handling status codes.


---

### conventions-loguru

---
title: Use Loguru for Logging
impact: MEDIUM
impactDescription: Simplifies logging setup and provides better defaults
tags: conventions, logging, observability
---

## Use Loguru for Logging

**Impact: MEDIUM (Simplifies logging setup and provides better defaults)**

Use Loguru for all logging instead of Python's built-in logging module. Loguru provides better defaults, simpler API, and automatic context capture without boilerplate configuration.

**Incorrect (using built-in logging):**

```python
import logging

# Requires manual configuration
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def process_user(user_id):
    logger.info(f"Processing user {user_id}")
    try:
        result = fetch_data(user_id)
        logger.info(f"Processed user {user_id}")
    except Exception as e:
        logger.error(f"Failed to process user {user_id}: {e}")
        raise
```

**Correct (using Loguru):**

```python
from loguru import logger

def process_user(user_id: int) -> dict:
    """Process user data with automatic context logging."""
    logger.info("Processing user {user_id}", user_id=user_id)
    try:
        result = fetch_data(user_id)
        logger.info("Processed user {user_id}", user_id=user_id)
        return result
    except Exception as e:
        logger.exception("Failed to process user {user_id}", user_id=user_id)
        raise
```

**Loguru benefits:**

1. **No configuration needed** - works out of the box
2. **Automatic exception tracing** - `logger.exception()` captures full traceback
3. **Structured logging** - pass variables as kwargs for JSON output
4. **Better formatting** - colors and readable output by default
5. **Easy file rotation** - `logger.add("file.log", rotation="500 MB")`

**Structured logging example:**

```python
from loguru import logger

logger.info(
    "User action completed",
    user_id=user_id,
    action="update_profile",
    duration_ms=duration,
    success=True
)
# Output: 2024-01-15 10:30:45 | INFO | User action completed | user_id=123 action=update_profile duration_ms=45 success=True
```

**Configuration (optional):**

```python
# Remove default handler and add custom one
logger.remove()
logger.add(
    sys.stderr,
    format="{time} | {level} | {message}",
    level="INFO"
)
logger.add("logs/app.log", rotation="1 day", retention="7 days")
```

Reference: [Loguru Documentation](https://loguru.readthedocs.io/)


---

### conventions-module-docstring-required

---
title: Begin every module with a clear module docstring
impact: HIGH
impactDescription: makes intent and I/O obvious to humans and agents
tags: conventions, documentation
---

## Begin every module with a clear module docstring

**Incorrect:**
```py
import os

def run():
    ...
```

**Correct:**
```py
"""Fetch and normalize incident feeds into ArangoDB.

Inputs:
- FEED_URL (env or CLI option)
- --since (ISO timestamp)

Outputs:
- Writes normalized records
- Exits non-zero on validation/write failures
"""

from __future__ import annotations

def run() -> None:
    ...
```

### Notes
- Include: purpose, inputs, outputs/side-effects, failure modes.
- Keep it short but specific.


---

### conventions-no-print

---
title: Do not use print() in library/service code
impact: MEDIUM
impactDescription: keeps output structured and controllable; avoids noisy stdout
tags: conventions, logging
---

## Do not use print() in library/service code

**Incorrect:**
```py
print("starting")
```

**Correct:**
```py
from loguru import logger

logger.info("starting")
```

### Notes
- Use `typer.echo` only for user-facing CLI output.
- Use Loguru for logs.


---

### conventions-typer-cli

---
title: Use Typer for CLIs; keep CLI thin
impact: HIGH
impactDescription: consistent UX and easier testing of core logic
tags: conventions, cli, typer
---

## Use Typer for CLIs; keep CLI thin

**Incorrect:**
```py
import argparse

def main():
    ...
```

**Correct:**
```py
import typer
from loguru import logger

app = typer.Typer(no_args_is_help=True)

@app.command()
def run(feed_url: str, limit: int = 100) -> None:
    logger.info("run feed_url={} limit={}", feed_url, limit)
    ingest(feed_url=feed_url, limit=limit)

def main() -> None:
    app()

if __name__ == "__main__":
    main()
```

### Notes
- Put business logic in functions so it can be unit-tested without CLI parsing.


---

### conventions-uv-pyproject

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


## testing


---

### testing-arrange-act-assert

---
title: Write tests with Arrange/Act/Assert structure
impact: MEDIUM
impactDescription: improves readability and reduces brittle assertions
tags: testing, pytest
---

## Write tests with Arrange/Act/Assert structure

**Incorrect:**
```py
def test_it():
    assert do(1) == 2
    assert do(2) == 3
```

**Correct:**
```py
def test_increment():
    # Arrange
    x = 1
    # Act
    y = do(x)
    # Assert
    assert y == 2
```

### Notes
- Prefer one behavior per test.
- Parametrize instead of duplicating structure.


---

### testing-deterministic-time

---
title: Make time-dependent tests deterministic
impact: MEDIUM
impactDescription: prevents flakiness due to wall-clock timing
tags: testing, time, determinism
---

## Make time-dependent tests deterministic

**Incorrect:**
```py
def test_expiry():
    assert is_expired() is False
```

**Correct:**
```py
from datetime import datetime, timezone

def test_expiry():
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    assert is_expired(now=now) is False
```

### Notes
- Pass `now` as a parameter instead of calling `datetime.now()` inside logic.


---

### testing-no-network-by-default

---
title: Do not rely on real network in tests by default
impact: MEDIUM
impactDescription: keeps tests deterministic and fast; avoids flaky CI failures
tags: testing, determinism
---

## Do not rely on real network in tests by default

**Incorrect:**
```py
def test_fetch_real():
    assert fetch("https://example.com")
```

**Correct:**
```py
def test_fetch_fixture(httpx_mock):
    httpx_mock.add_response(json={"ok": True})
    assert fetch("https://api") == {"ok": True}
```

### Notes
- Network tests can exist as explicit, opt-in smoke tests (marked/segregated).


---

### testing-non-mocked-sanity

---
title: Include non-mocked sanity tests
impact: HIGH
impactDescription: catches integration breakage unit tests miss
tags: testing, sanity, integration
---

## Include non-mocked sanity tests

**Incorrect:**
```py
def test_ingest():
    # everything mocked
    ...
```

**Correct:**
```py
def test_sanity_ingest_smoke(tmp_path):
    # minimal real-path test: parse real fixture and write to temp output
    out = tmp_path / "out.json"
    n = ingest_fixture_to_path("tests/fixtures/sample.json", out)
    assert n > 0
    assert out.exists()
```

### Notes
- Sanity tests should be small and deterministic.
- Prefer local fixtures + temp dirs; avoid real network unless explicitly allowed.


---

### testing-sanity-fixtures

---
title: Prefer real small fixtures for parsing/IO code
impact: MEDIUM
impactDescription: exercises real code paths without heavy integration dependencies
tags: testing, fixtures
---

## Prefer real small fixtures for parsing/IO code

**Incorrect:**
```py
def test_parse():
    payload = {"hard": "to maintain"}
    assert parse(payload)["id"] == "x"
```

**Correct:**
```py
def test_parse_fixture():
    payload = load_fixture_json("tests/fixtures/payload.json")
    result = parse(payload)
    assert result.id == "x"
```

### Notes
- Fixtures are easier to extend and match production shapes.


## async


---

### async-limit-concurrency

---
title: Limit concurrency when fan-out is possible
impact: MEDIUM
impactDescription: prevents resource exhaustion and rate-limit storms
tags: async, concurrency
---

## Limit concurrency when fan-out is possible

**Incorrect:**
```py
async def fetch_all(urls):
    return await asyncio.gather(*(fetch(u) for u in urls))
```

**Correct:**
```py
import asyncio

async def fetch_all(urls, limit: int = 10):
    sem = asyncio.Semaphore(limit)

    async def bounded(u):
        async with sem:
            return await fetch(u)

    return await asyncio.gather(*(bounded(u) for u in urls))
```

### Notes
- Constrain concurrency for network/disk/CPU fan-out paths.


---

### async-no-blocking-in-event-loop

---
title: Do not perform blocking I/O in the event loop
impact: HIGH
impactDescription: prevents latency spikes and timeouts under load
tags: async, io, performance
---

## Do not perform blocking I/O in the event loop

**Incorrect:**
```py
import requests

async def handler(url: str) -> str:
    return requests.get(url, timeout=10).text
```

**Correct:**
```py
import asyncio
import httpx

async def handler(url: str) -> str:
    async with httpx.AsyncClient(timeout=httpx.Timeout(10.0)) as client:
        r = await client.get(url)
        r.raise_for_status()
        return r.text

# If forced to use a sync library:
# return await asyncio.to_thread(lambda: blocking_call())
```

### FastAPI: use plain `def` for sync-only endpoints

In FastAPI, `async def` runs on the event loop. `def` (without async) automatically runs in a thread pool. **If your endpoint only calls sync libraries (python-arango, requests, CPU-bound code), use `def` not `async def`.**

**Incorrect — blocks the event loop for every request:**
```py
@router.get("/items")
async def list_items():
    db = get_db()  # sync
    return list(db.aql.execute("FOR d IN items RETURN d"))  # sync
```

**Correct — FastAPI auto-threads it:**
```py
@router.get("/items")
def list_items():
    db = get_db()
    return list(db.aql.execute("FOR d IN items RETURN d"))
```

**When to keep `async def`:**
- Endpoint uses `await` (httpx.AsyncClient, asyncio.to_thread, etc.)
- Endpoint mixes async and sync via explicit `asyncio.to_thread()` calls

### Notes
- Prefer `httpx.AsyncClient` for async HTTP.
- If unavoidable, offload sync work via `asyncio.to_thread`.
- **python-arango is entirely synchronous** — every `db.aql.execute()` blocks. Use `def` endpoints or `asyncio.to_thread()`.
- This applies to ALL sync DB drivers, classifier inference, file I/O, and CPU-bound code.


---

### async-prefer-asyncclient

---
title: Prefer httpx.AsyncClient for async HTTP
impact: MEDIUM
impactDescription: reduces thread offloading and improves throughput
tags: async, httpx
---

## Prefer httpx.AsyncClient for async HTTP

**Incorrect:**
```py
import asyncio
import httpx

async def get(url):
    return await asyncio.to_thread(lambda: httpx.get(url).text)
```

**Correct:**
```py
import httpx

async def get(url: str) -> str:
    async with httpx.AsyncClient(timeout=httpx.Timeout(10.0)) as client:
        r = await client.get(url)
        r.raise_for_status()
        return r.text
```

### Notes
- Use one AsyncClient per scope to reuse connections when appropriate.


---

### async-single-asyncio-run

---
title: Only call asyncio.run() once per process
impact: CRITICAL
impactDescription: nested asyncio.run() raises RuntimeError and breaks the entire program
tags: async, asyncio, correctness
---

## Only call asyncio.run() once per process

`asyncio.run()` creates and destroys an event loop. Calling it from inside
an already-running loop (or nesting calls) raises `RuntimeError: This event
loop is already running`. Structure code so a single `asyncio.run()` in
`if __name__ == "__main__"` drives all async work.

**Incorrect:**
```py
import asyncio

async def fetch_data():
    ...

async def validate():
    ...

def process():
    data = asyncio.run(fetch_data())      # first loop
    result = asyncio.run(validate())      # second loop — wasteful
    return result

async def run_pipeline():
    # Nested asyncio.run() inside an already-running loop — CRASHES
    result = asyncio.run(validate())      # RuntimeError!
    return result
```

**Correct:**
```py
import asyncio

async def fetch_data():
    ...

async def validate():
    ...

async def process_async():
    """All async work composed via await, not asyncio.run()."""
    data = await fetch_data()
    result = await validate()
    return result

def process():
    """Sync wrapper — single asyncio.run() entry point."""
    return asyncio.run(process_async())

# Only one asyncio.run() in the entire process
if __name__ == "__main__":
    asyncio.run(process_async())
```

### Notes
- `asyncio.run()` must appear **once** per process, typically in `if __name__ == "__main__"` or a single sync wrapper function.
- Compose async work with `await`, not by spawning new event loops.
- If you need to call async code from sync code that may itself be called from async context, use `asyncio.get_event_loop().run_until_complete()` or restructure to keep the caller async.
- Libraries like `nest_asyncio` exist but are a code smell — restructure instead.


---

### async-timeouts-cancellation

---
title: Use timeouts and handle cancellation explicitly
impact: HIGH
impactDescription: prevents hung tasks and resource leaks
tags: async, timeouts, cancellation
---

## Use timeouts and handle cancellation explicitly

**Incorrect:**
```py
async def fetch():
    return await slow_call()
```

**Correct:**
```py
import asyncio

async def fetch():
    try:
        return await asyncio.wait_for(slow_call(), timeout=5)
    except asyncio.TimeoutError:
        return None
```

### Notes
- Background tasks must be cancelled/awaited on shutdown.


## perf


---

### perf-avoid-n2

---
title: Avoid accidental O(n^2) loops in hot paths
impact: MEDIUM
impactDescription: prevents slowdowns that scale poorly with input size
tags: performance, complexity
---

## Avoid accidental O(n^2) loops in hot paths

**Incorrect:**
```py
def join(users, profiles):
    out = []
    for u in users:
        p = next(p for p in profiles if p["id"] == u["id"])
        out.append((u, p))
    return out
```

**Correct:**
```py
def join(users, profiles):
    by_id = {p["id"]: p for p in profiles}
    return [(u, by_id[u["id"]]) for u in users if u["id"] in by_id]
```

### Notes
- Build indexes (`dict`/`set`) once, then do O(1) lookups.


---

### perf-cache-pure

---
title: Cache expensive pure computations
impact: MEDIUM
impactDescription: avoids repeated work for identical inputs
tags: performance, caching
---

## Cache expensive pure computations

**Incorrect:**
```py
def render(user_id: str) -> str:
    return compute_expensive(user_id)
```

**Correct:**
```py
from functools import lru_cache

@lru_cache(maxsize=1024)
def compute_cached(user_id: str) -> str:
    return compute_expensive(user_id)

def render(user_id: str) -> str:
    return compute_cached(user_id)
```

### Notes
- Only cache pure functions (no IO, time, randomness, or global mutation).


---

### perf-stream-large-files

---
title: Stream large files instead of reading into memory
impact: MEDIUM
impactDescription: prevents memory spikes and improves throughput
tags: performance, io
---

## Stream large files instead of reading into memory

**Incorrect:**
```py
data = Path(path).read_bytes()
```

**Correct:**
```py
from pathlib import Path

p = Path(path)
with p.open("rb") as f:
    for chunk in iter(lambda: f.read(1024 * 1024), b""):
        handle_chunk(chunk)
```

### Notes
- If you need whole-file operations, justify it and cap file sizes.


## packaging


---

### packaging-pin-major-deps

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


---

### packaging-pyproject-central

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


---

### packaging-uv-lockfile

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


## logging


---

### logging-bind-context

---
title: Bind contextual fields to logs
impact: MEDIUM
impactDescription: makes failures diagnosable across async tasks and batch jobs
tags: logging, loguru, observability
---

## Bind contextual fields to logs

**Incorrect:**
```py
from loguru import logger

logger.info("processing")
```

**Correct:**
```py
from loguru import logger

logger.bind(job_id=job_id, feed=feed).info("processing")
```

### Notes
- Prefer context fields over string concatenation.


---

### logging-no-giant-payloads

---
title: Avoid logging giant payloads; log summaries
impact: MEDIUM
impactDescription: prevents log bloat and accidental PII leakage
tags: logging, security
---

## Avoid logging giant payloads; log summaries

**Incorrect:**
```py
from loguru import logger

logger.debug("payload={} ", payload)
```

**Correct:**
```py
from loguru import logger

logger.debug("payload_len={} keys={}", len(payload), list(payload)[:10])
```

### Notes
- Never log secrets; prefer lengths, counts, IDs, and key subsets.


---

### logging-use-exception

---
title: Use logger.exception in exception handlers
impact: MEDIUM
impactDescription: preserves stack traces and makes failures actionable
tags: logging, exceptions
---

## Use logger.exception in exception handlers

**Incorrect:**
```py
from loguru import logger

try:
    do_work()
except Exception as e:
    logger.error("failed: {}", e)
```

**Correct:**
```py
from loguru import logger

try:
    do_work()
except Exception:
    logger.exception("failed during do_work")
    raise
```

### Notes
- Use exception logs sparingly; avoid dumping huge payloads.


## style


---

### style-max-800-lines

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


---

### style-module-docstring

---
title: Required Module Docstrings
impact: HIGH
impactDescription: Improves discoverability and understanding for AI agents and humans
tags: style, documentation, maintainability
---

## Required Module Docstrings

**Impact: HIGH (Improves discoverability and understanding for AI agents and humans)**

Every Python module must begin with a clear docstring describing its purpose, inputs, outputs, and failure modes. This helps both humans and AI agents understand the module's role without reading all the code.

**Incorrect (missing or vague docstring):**

```python
# user_service.py
import requests

def get_user(user_id):
    # No module docstring - unclear what this module does
    response = requests.get(f"/api/users/{user_id}")
    return response.json()
```

**Correct (clear module docstring):**

```python
# user_service.py
"""
User service for fetching and managing user data.

This module provides functions for:
- Fetching user profiles from the API
- Updating user metadata
- Managing user permissions

Inputs:
- user_id (int): Unique user identifier
- API credentials via USERAPI_KEY environment variable

Outputs:
- User objects with id, name, email, permissions

Failure modes:
- Raises UserNotFoundError if user doesn't exist
- Raises APIError on network/API failures
- Returns None for soft failures (e.g., missing optional data)

Dependencies:
- Requires httpx for API calls
- Requires USERAPI_KEY in environment
"""
import httpx
from loguru import logger

def get_user(user_id: int) -> dict:
    """Fetch user profile from API."""
    response = httpx.get(f"/api/users/{user_id}")
    response.raise_for_status()
    return response.json()
```

**Module docstring template:**

```python
"""
{One-line summary of module purpose}

This module provides:
- {Key function 1}
- {Key function 2}
- {Key function 3}

Inputs:
- {Expected inputs, config, environment variables}

Outputs:
- {What the module produces}

Failure modes:
- {How it fails and what exceptions it raises}

Dependencies:
- {External dependencies, APIs, services}
"""
```

Reference: [PEP 257 - Docstring Conventions](https://peps.python.org/pep-0257/)


---

### style-pathlib

---
title: Prefer pathlib.Path over os.path
impact: LOW
impactDescription: improves readability and cross-platform path handling
tags: style, io, pathlib
---

## Prefer pathlib.Path over os.path

**Incorrect:**
```py
import os

p = os.path.join(root, "data", "x.json")
```

**Correct:**
```py
from pathlib import Path

p = Path(root) / "data" / "x.json"
```

### Notes
- Use `Path` consistently inside modules.


---

### style-small-functions

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
