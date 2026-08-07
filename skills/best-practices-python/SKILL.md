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
disciplines:
  - engineering-standards
  - developer-tooling
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
- `style-dataclass-records-over-stringly-dicts`
- `correctness-centralized-error-codes`
- `correctness-regex-only-known-grammar`
- `correctness-mutable-default-factory`
- `correctness-validate-boundaries`
- `io-httpx-timeout-status`
- `security-subprocess-no-shell-true`
- `security-no-unsafe-deserialization`
- `security-no-dynamic-exec`
- `security-no-hardcoded-secrets`
- `correctness-no-runtime-assert`
- `packaging-no-sys-path-surgery`
- `style-pathlib-paths`
- `correctness-utc-aware-timestamps`
- `conventions-loguru`
- `conventions-typer-cli`
- `conventions-httpx`
- `conventions-uv-pyproject`
- `conventions-functions-over-classes`
- `conventions-pyproject-deps-complete`
- `testing-non-mocked-sanity`

## Dataclasses for Typed Records and Error Codes

**Use dataclasses for typed, repeated record shapes instead of scattered string keys, loose dictionaries, or long `if`/`elif` chains.**

### Rule: `style-dataclass-records-over-stringly-dicts`

When a concept has a stable shape and is passed across functions, model it as a dataclass. This gives the code one discoverable definition, typed fields, readable construction, and safer refactors than repeating dictionary keys or unpacked tuples at call sites.

**Use a dataclass when:**
- the same dictionary shape appears in more than one function
- fields are read by string key in several places
- construction requires defaults, derived fields, or validation
- an `if`/`elif` chain is switching on ad hoc string values that should be named states or result types

**Do not use a dataclass for:**
- arbitrary JSON payloads that stay at the IO boundary
- one-off local dictionaries that never cross a function boundary
- records that need runtime validation, coercion, or serialization guarantees strong enough to require Pydantic

### Rule: `correctness-centralized-error-codes`

Closed vocabularies such as statuses, error codes, lanes, providers, and result categories MUST be centralized with symbolic names. Use `StrEnum` for the closed set and a frozen dataclass for error metadata when callers need more than the raw code.

```python
from dataclasses import dataclass
from enum import StrEnum


class ErrorCode(StrEnum):
    MISSING_INPUT = "missing_input"
    PROVIDER_TIMEOUT = "provider_timeout"
    INVALID_RECEIPT = "invalid_receipt"


@dataclass(frozen=True, slots=True)
class ErrorInfo:
    code: ErrorCode
    message: str
    retryable: bool = False


ERRORS: dict[ErrorCode, ErrorInfo] = {
    ErrorCode.MISSING_INPUT: ErrorInfo(
        code=ErrorCode.MISSING_INPUT,
        message="required input was not provided",
    ),
    ErrorCode.PROVIDER_TIMEOUT: ErrorInfo(
        code=ErrorCode.PROVIDER_TIMEOUT,
        message="provider did not respond before the timeout",
        retryable=True,
    ),
    ErrorCode.INVALID_RECEIPT: ErrorInfo(
        code=ErrorCode.INVALID_RECEIPT,
        message="receipt failed schema or consistency checks",
    ),
}
```

**Wrong:**
```python
if error == "timeout":
    return {"code": "provider_timeout", "retry": "yes"}
if error == "bad_receipt":
    return {"code": "invalid_receipt", "retry": "no"}
```

**Right:**
```python
info = ERRORS[ErrorCode.PROVIDER_TIMEOUT]
if info.retryable:
    logger.warning("retryable error: {}", info.code.value)
```

Use `frozen=True` when the record is configuration, registry metadata, or a returned result that should not be mutated after construction. Use `slots=True` for small high-volume records unless the code needs dynamic attributes.

### Rule: `correctness-mutable-default-factory`

Never use mutable defaults in function signatures or dataclass fields. Use `None` plus initialization for functions, and `field(default_factory=...)` for dataclasses.

**Wrong:**
```python
def collect(items: list[str] = []) -> list[str]:
    items.append("new")
    return items


@dataclass
class Batch:
    records: list[str] = []
```

**Right:**
```python
from dataclasses import dataclass, field


def collect(items: list[str] | None = None) -> list[str]:
    safe_items = list(items or [])
    safe_items.append("new")
    return safe_items


@dataclass
class Batch:
    records: list[str] = field(default_factory=list)
```

## Regex Is Seldom the Right Choice

**Use regex only when the input grammar is known in advance, bounded, and covered by fixtures.**

### Rule: `correctness-regex-only-known-grammar`

Regex is brittle against human text, generated text, HTML, JSON, Markdown, PDFs, code, logs with evolving formats, and any input whose shape is learned from examples rather than specified by a grammar. A project agent MUST NOT add regex as the first parsing or classification tool for unknown or drifting input.

**Regex is allowed when:**
- the accepted input format is documented and stable
- the pattern is anchored or scoped to the smallest known field
- positive and negative fixtures cover realistic edge cases
- the failure mode is explicit instead of silently returning partial data

**Prefer these instead of regex:**
- structured parsers for structured data: `json`, `tomllib`, `csv`, `ast`, XML/HTML parsers, Markdown parsers, tree-sitter, or service schemas
- exact keyed lookup or `Enum`/`StrEnum` for closed vocabularies
- a classifier or fastText-style model when the input category is learned from examples
- RapidFuzz after classification, using a bounded candidate set and an explicit score threshold

**Wrong:**
```python
if re.search("urgent|important|asap", message.lower()):
    route = "priority"
elif re.search("refund|billing|invoice", message.lower()):
    route = "billing"
```

**Right:**
```python
from rapidfuzz import fuzz, process


label = classify_message(message)
match, score, _ = process.extractOne(
    label,
    ["priority", "billing", "support"],
    scorer=fuzz.WRatio,
)
if score < 90:
    raise ValueError(f"unmatched route label: {label}")
route = Route(match)
```

When regex is truly justified, name the grammar in the function or constant, keep the pattern centralized, and add tests that prove both accepted and rejected inputs.

## Validate External Data at Boundaries

**External input is untrusted until parsed through a schema or typed boundary object.**

### Rule: `correctness-validate-boundaries`

When data enters from JSON, YAML, HTTP, files, CLI strings, environment variables, LLM output, browser state, subprocess output, or databases, validate it once at the boundary before business logic touches it.

Use:
- Pydantic for external payload validation, coercion, and explicit error reports
- dataclasses for already-validated internal records
- `TypedDict` only for narrow static typing of dictionary-shaped data that does not need runtime validation
- parser libraries for known structured formats

**Wrong:**
```python
payload = response.json()
task_id = payload["task"]["id"]
timeout = int(payload.get("timeout", 30))
```

**Right:**
```python
from pydantic import BaseModel, Field


class TaskPayload(BaseModel):
    task_id: str = Field(min_length=1)
    timeout_s: float = Field(default=30.0, gt=0, le=600)


payload = TaskPayload.model_validate(response.json())
```

Do not pass raw provider dictionaries across multiple modules. Convert them into a named model at the boundary, then pass the typed object.

## Security and Runtime Gates

### Rule: `security-no-unsafe-deserialization`

Do not load untrusted or user-modifiable data with `pickle`, `marshal`, or unsafe YAML loaders. `pickle` can execute code during loading, and `yaml.load()` has historically allowed arbitrary object construction.

**Wrong:**
```python
model = pickle.load(open(path, "rb"))
config = yaml.load(text, Loader=yaml.Loader)
```

**Right:**
```python
config = yaml.safe_load(text)
payload = ConfigPayload.model_validate(config)
```

Use JSON, TOML, safe YAML, SQLite, Parquet, or a signed/hashed internal artifact instead. If a trusted model artifact truly requires pickle/joblib, document the trust boundary, verify the artifact path or digest, and never accept that path from external input.

### Rule: `security-no-dynamic-exec`

Do not use `eval()`, `exec()`, dynamic imports from untrusted strings, or generated Python code as a parser, router, validator, or repair mechanism.

**Wrong:**
```python
value = eval(user_expression)
exec(generated_fix)
```

**Right:**
```python
value = ast.literal_eval(user_expression)
```

Prefer structured schemas, command registries, `Enum` dispatch, or purpose-built parsers. If executing generated code is the explicit product behavior, isolate it in a sandboxed runner with a receipt and no ambient credentials.

### Rule: `security-no-hardcoded-secrets`

Never hardcode API keys, tokens, passwords, proxy credentials, or plausible secret defaults in source. Do not log secrets, request headers, full environment dumps, or provider payloads that may contain secrets.

**Wrong:**
```python
api_key = os.getenv("SCILLM_PROXY_KEY", "sk-dev-proxy-123")
logger.info("headers={}", headers)
```

**Right:**
```python
api_key = os.environ["SCILLM_PROXY_KEY"]
logger.info("calling provider auth=present")
```

Example keys used only in tests or documentation must be obvious placeholders such as `example-key-not-secret`, and production code must fail closed when a required secret is absent.

### Rule: `correctness-no-runtime-assert`

Do not use `assert` for runtime validation, security checks, user input checks, artifact gates, or provider response validation. Python can remove assertions in optimized mode.

**Wrong:**
```python
assert receipt["ok"] is True
```

**Right:**
```python
if receipt.get("ok") is not True:
    raise ValueError("receipt did not pass validation")
```

`assert` is fine in tests. For smoke commands embedded in documentation, prefer explicit `raise SystemExit(...)` or a small checker script when the command is used as proof.

### Rule: `packaging-no-sys-path-surgery`

Do not scatter `sys.path.insert()` or `PYTHONPATH` hacks through project code. Package import paths through `pyproject.toml`, `uv run --project`, editable installs, or a single documented CLI bootstrap.

**Wrong:**
```python
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from common import memory_client
```

**Right:**
```python
from agent_skills.common import memory_client
```

A short source-tree bootstrap is acceptable only in a CLI entry file that documents why package execution is unavailable. Do not put path mutation inside libraries, reusable helpers, or modules imported by tests.

## HTTP, Subprocess, Path, and Time Hygiene

### Rule: `io-httpx-timeout-status`

Every HTTP call MUST use `httpx`, an explicit timeout appropriate to the operation, and status handling. Do not rely on default timeout behavior for project code, because the correct budget differs between health checks, streaming calls, downloads, and model inference.

**Wrong:**
```python
resp = httpx.post(url, json=payload)
return resp.json()
```

**Right:**
```python
timeout = httpx.Timeout(connect=5.0, read=60.0, write=10.0, pool=5.0)
with httpx.Client(timeout=timeout) as client:
    resp = client.post(url, json=payload)
    resp.raise_for_status()
    return ResponsePayload.model_validate(resp.json())
```

Health checks should use short timeouts, usually 2-5 seconds. Long provider calls should still have a documented finite timeout and log timeout failures at `logger.error`.

### Rule: `security-subprocess-no-shell-true`

Do not use `shell=True` for subprocess calls. Use argument lists, finite timeouts, `check=True` when failure should stop the workflow, and explicit output capture when the caller needs receipts.

**Wrong:**
```python
subprocess.run(f"git show {ref}", shell=True)
```

**Right:**
```python
result = subprocess.run(
    ["git", "show", ref],
    check=True,
    capture_output=True,
    text=True,
    timeout=30,
)
```

If shell behavior is genuinely required, the command must be static or every interpolated value must be quoted with `shlex.quote`, and the reason must be documented at the call site. In async code, this rule composes with `async-no-sync-subprocess`.

### Rule: `style-pathlib-paths`

Use `pathlib.Path` for filesystem paths. Do not build paths with string concatenation or scatter hardcoded `/tmp/...` paths through project logic.

**Wrong:**
```python
out = "/tmp/my-skill/" + task_id + "/receipt.json"
open(out, "w").write(data)
```

**Right:**
```python
from pathlib import Path
from tempfile import TemporaryDirectory


with TemporaryDirectory(prefix="my-skill-") as tmp:
    out = Path(tmp) / task_id / "receipt.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(data, encoding="utf-8")
```

Hardcoded `/tmp` is allowed only for explicitly disposable evidence artifacts or documented runtime defaults. Even then, expose an override through CLI/env/config and convert to `Path` immediately.

### Rule: `correctness-utc-aware-timestamps`

Timestamps written to receipts, logs, caches, databases, filenames, or API payloads MUST be timezone-aware UTC. Do not use naive `datetime.now()` or `datetime.utcnow()`.

**Wrong:**
```python
created_at = datetime.now().isoformat()
```

**Right:**
```python
from datetime import UTC, datetime


created_at = datetime.now(UTC).isoformat()
```

Use wall-clock local time only for human-facing display, never as persisted operational evidence.

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
