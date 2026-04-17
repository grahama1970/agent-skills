---
name: best-practices-python
description: >
  Repo-specific Python best practices for agentic coding: Loguru + Typer + uv + pyproject.toml,
  httpx over requests, functions-first, module docstrings, max 800 LOC per file, and non-mocked sanity tests.
triggers:
  - best practices python
  - python conventions
  - loguru
  - typer
  - httpx
  - python code review
license: MIT
metadata:
  language: python
  python_versions: ["3.11+", "3.12+"]
  defaults:
    logging: loguru
    cli: typer
    http: httpx
    packaging: uv + pyproject.toml
    style:
      max_lines_per_file: 800
      module_docstring: required
      functions_over_classes: true
    testing:
      include_sanity_tests: true

provides:
  - best-practices-python
composes:
  - task-monitor
---

# Python Best Practices (Project Skill)

This skill is a curated set of atomic rules for writing and refactoring Python in *this* repo.

## Project Defaults (apply unless explicitly overridden)

- **Logging:** Loguru (`from loguru import logger`)
- **CLI:** Typer (thin CLI; logic in functions)
- **HTTP:** httpx (not requests)
- **Packaging:** uv + pyproject.toml
- **Structure:** functions over classes unless state is required
- **Files:** no Python file over **800** lines
- **Docs:** every module begins with a **clear module docstring** describing purpose, inputs, outputs, and failure modes
- **Tests:** include **non-mocked sanity tests** in addition to unit tests

## Package Reference

See **[PACKAGES.md](docs/PACKAGES.md)** for the full Python package reference — mandatory standards, standard toolkit (80+ packages across 15 categories), and anti-patterns. Generated from 1,414 pyproject.toml files. Also available via `/memory recall "python packages"`.

## When to Apply

Use this skill whenever you:
- create or refactor Python modules, CLIs, services, or pipelines
- add network calls, subprocess calls, or IO
- change packaging/tooling (uv, pyproject)
- add tests or fix bugs/flakiness

## Categories (priority order)

1. Correctness (CRITICAL/HIGH): `correctness-`
2. Security (CRITICAL/HIGH): `security-`
3. Conventions (HIGH): `conventions-`
4. Testing & Sanity (HIGH/MEDIUM): `testing-`
5. Async & Concurrency (HIGH/MEDIUM): `async-`
6. Performance (MEDIUM): `perf-`
7. Packaging (MEDIUM): `packaging-`
8. Logging & Observability (MEDIUM): `logging-`
9. Style & Maintainability (MEDIUM/LOW): `style-`

## Quick Reference (house rules)

- `style-max-800-lines`
- `style-module-docstring`
- `style-thin-init-py`
- `conventions-loguru`
- `conventions-typer-cli`
- `conventions-httpx`
- `conventions-uv-pyproject`
- `conventions-functions-over-classes`
- `conventions-pyproject-deps-complete`
- `testing-non-mocked-sanity`

## Thin `__init__.py` in Packages (NON-NEGOTIABLE)

**`__init__.py` files must contain only re-exports and package metadata — never business logic.**

### Rule: `style-thin-init-py`

When logic is hidden in `__init__.py`, agents (and humans) searching for `module_name.py` won't find it. This causes misdiagnosis — an agent sees `from probes import run_probes`, looks for `probes.py`, doesn't find it, and concludes the module is missing. The logic is actually in `probes/__init__.py` but invisible to file-based search.

**Correct pattern:**
```
mypackage/
  __init__.py          # Only re-exports: from .registry import run_probes, ProbeResult
  registry.py          # Actual logic lives here (discoverable by name)
  tier0.py
  tier1.py
```

**Anti-pattern:**
```
mypackage/
  __init__.py          # 120 lines of logic, registries, runner functions
  tier0.py
  tier1.py
```

### What belongs in `__init__.py`:
- `__all__` list
- Re-exports: `from .submodule import ClassName`
- Package-level constants (version, etc.)
- Max ~20 lines

### What does NOT belong:
- Functions with business logic
- Class definitions with methods
- Registry patterns (register/lookup)
- Anything an agent would look for by name

**Incident**: On 2026-03-16, an agent misdiagnosed `monitor-taxonomy` as broken ("missing probes.py glue module") because `run_probes()` lived in `probes/__init__.py` (122 lines) instead of a named module. The code worked fine — but was invisible to agents doing file-based search.

---

## pyproject.toml Dependency Completeness (NON-NEGOTIABLE)

**Every `import` in a skill's `.py` files MUST have a corresponding entry in `pyproject.toml` `[project.dependencies]`.**

This is a hard gate. Missing dependencies cause `ModuleNotFoundError` at runtime after `uv sync` in a clean venv — a silent regression that only surfaces when the skill is invoked by another agent or in CI.

### Rule: `conventions-pyproject-deps-complete`

When creating or modifying a Python skill with a `pyproject.toml`:

1. **Scan all `.py` files** in the skill for `import` and `from X import` statements
2. **Cross-reference** each top-level import against `[project.dependencies]`
3. **Add any missing** third-party packages to dependencies
4. **Run `uv sync`** after adding to verify resolution

### Common offenders (imports that look stdlib but aren't)

| Import | Package needed in pyproject.toml |
|--------|----------------------------------|
| `from loguru import logger` | `loguru>=0.7.0` |
| `import typer` | `typer>=0.9.0` |
| `import httpx` | `httpx>=0.24.0` |
| `from rich import ...` | `rich>=13.0.0` |
| `import pydantic` | `pydantic>=2.0` |
| `from dotenv import ...` | `python-dotenv>=1.0.0` |
| `import pytz` | `pytz` |
| `import tenacity` | `tenacity>=8.0` |

### Verification pattern

```bash
# After any pyproject.toml change:
cd /path/to/skill && uv sync && uv run python -c "import <every_module>"
```

### Why this matters

The ops-chutes skill broke (Feb 2026) because `loguru` was imported by 3 files but
missing from `pyproject.toml`. After `uv sync` recreated the venv, `loguru` vanished
and every downstream skill that called ops-chutes got `ModuleNotFoundError`. This was
a silent regression — the skill worked in the shared system venv but failed in isolation.

---

## uv Isolation in run.sh (NON-NEGOTIABLE)

**If a skill has `pyproject.toml`, ALL Python invocations in `run.sh` MUST use `uv run --project "$SCRIPT_DIR" python` — never bare `python3`.**

### Rule: `conventions-uv-run-in-runsh`

Bare `python3` uses the system Python, which picks up stale packages from `~/.local/lib/python3.12/site-packages/`. The skill's `.venv` (managed by `uv sync`) has the correct pinned versions. Using bare `python3` bypasses it entirely.

**The `alias python3='uv run ...'` pattern is acceptable** IF `shopt -s expand_aliases` is set at the top of `run.sh`. But aliases do NOT expand inside `nohup`, `env`, `xargs`, or `$()` — those contexts MUST use explicit `uv run --project`.

**Incident**: 2026-03-17 — `/orchestrate` failed with anyio version mismatch because `run.sh` called bare `python3 structured_execute.py`. System python3 had anyio 3.x from `~/.local/`, but httpx 0.28+ requires anyio 4.x which was only in the skill's `.venv`.

### Correct:
```bash
uv run --project "$SCRIPT_DIR" python "$SCRIPT_DIR/structured_execute.py" run plan.yaml
```

### Wrong:
```bash
python3 "$SCRIPT_DIR/structured_execute.py" run plan.yaml  # system python, wrong deps
nohup python3 "$SCRIPT_DIR/worker.py" &                    # alias doesn't expand in nohup
```

## Common Mistakes

### WRONG: Using `import logging` instead of loguru
```python
import logging
logger = logging.getLogger(__name__)
```

### RIGHT: Always use loguru
```python
from loguru import logger
```

### WRONG: Using `import requests` for HTTP calls
```python
import requests
resp = requests.get("https://api.example.com")
```

### RIGHT: Use httpx
```python
import httpx
resp = httpx.get("https://api.example.com")
```

### WRONG: Using bare `python3` in run.sh when pyproject.toml exists
```bash
python3 "$SCRIPT_DIR/main.py"
```

### RIGHT: Use uv run for proper dependency isolation
```bash
uv run --project "$SCRIPT_DIR" python "$SCRIPT_DIR/main.py"
```

### WRONG: Missing dependency in pyproject.toml that the code imports
```python
from loguru import logger  # imported but not in pyproject.toml dependencies
```

### RIGHT: Every import has a matching pyproject.toml entry
```toml
[project]
dependencies = ["loguru>=0.7.0"]
```

---

## Docker Skills Must Have docker-compose.yml

**If a skill launches a persistent Docker container (`docker run -d`), it MUST have a `docker-compose.yml`.**

### Rule: `conventions-docker-compose`

Container specs buried in `docker run` flags across 10+ lines of shell are:
- Unreadable by agents (who has to grep run.sh to understand the container config)
- Error-prone (one missing flag = broken container)
- Non-declarative (can't diff container changes across commits)

The compose file is the canonical spec. `run.sh` handles dynamic lifecycle (port allocation, multi-instance, health checks) on top of it.

### Enforced by: `/skills-ci` scanner `runtime.docker_no_compose`

---

## No Silent Fallbacks in Exception Handlers (NON-NEGOTIABLE)

**Every `except` block MUST log at `logger.error`, NOT `logger.debug`.** `logger.debug` is invisible in production — failures silently disappear.

### Rule: `correctness-no-silent-fallback`

```python
# WRONG — silent in production, hides failures
except Exception as exc:
    logger.debug("search failed: {}", exc)
    return []

# WRONG — bare except with no logging at all
except Exception:
    pass

# RIGHT — visible in production logs
except Exception as exc:
    logger.error("search failed: {}", exc)
    return []
```

**Exceptions:**
- `dotenv` imports at module top (line 1-10) — genuinely optional
- Optional dependency imports (`sentence_transformers`, `torch`) — log at WARNING
- Health check retry loops — `continue` is acceptable

**Everything else MUST use `logger.error`.** This includes:
- ArangoDB queries, view searches, collection operations
- Embedding service calls
- Entity extraction, taxonomy lookups
- Graph traversal, relationship scoring
- Edge creation, document upserts

Cross-ref: `/best-practices-arangodb` rule `arango-no-silent-fallback`.

Enforced by: `/monitor-codebase` scanner and `/codex` review gate.

---

## No sync subprocess in async code

**If a Python file uses `asyncio`, it MUST NOT import `subprocess` or call `subprocess.run()`.** Use `asyncio.create_subprocess_exec()` or `asyncio.create_subprocess_shell()` instead.

### Rule: `async-no-sync-subprocess`

Sync `subprocess.run()` blocks the entire event loop. In an async executor, this freezes ALL concurrent tasks — cancel signals, watchdog polling, other lanes — until the subprocess finishes.

### Correct:
```python
proc = await asyncio.create_subprocess_shell(cmd, stdout=asyncio.subprocess.PIPE)
stdout, stderr = await proc.communicate()
```

### Wrong:
```python
result = subprocess.run(cmd, capture_output=True)  # blocks event loop
```
