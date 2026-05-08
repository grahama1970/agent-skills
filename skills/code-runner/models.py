"""Pydantic models for /code-runner spec validation and result schema.

Declarative guardrails — bad types, missing fields, and invalid values
caught at parse time before any LLM call, git operation, or subprocess.
"""
from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator


# ── Run State Machine ────────────────────────────────────────────────────────
# Normalized states for execution lifecycle. Maps to existing code paths.


class RunState(str, Enum):
    """Run-level execution states. Each maps to a distinct remediation path."""
    queued = "queued"              # Spec loaded, not yet started
    preflight_failed = "preflight_failed"  # Spec/DoD validation failed
    running = "running"            # Actively executing rounds
    blocked = "blocked"            # Stuck (zero_write, repo_lock, etc.)
    timed_out = "timed_out"        # Round or run timeout exceeded
    crashed = "crashed"            # Unhandled exception
    failed = "failed"              # DoD not passed after max rounds
    passed = "passed"              # DoD passed


class ReasonCode(str, Enum):
    """Reason codes for terminal states. Guides remediation."""
    # Preflight failures
    bad_spec = "bad_spec"          # TaskSpec validation failed
    bad_dod = "bad_dod"            # DoD command/assertion invalid
    missing_files = "missing_files"  # Allowlist files don't exist
    dirty_worktree = "dirty_worktree"  # Working tree has pre-existing changes

    # Blocking conditions
    repo_lock_conflict = "repo_lock_conflict"  # Another runner has repo lock
    zero_write = "zero_write"      # Repeated zero-write aborts
    stash_conflict = "stash_conflict"  # Git stash/restore failed

    # Execution failures
    max_rounds_exhausted = "max_rounds_exhausted"  # Hit round limit
    backend_timeout = "backend_timeout"  # LLM call timed out
    backend_error = "backend_error"  # LLM returned error
    diagnosis_rejected = "diagnosis_rejected"  # Diagnosis failed validation

    # Crashes
    runner_exception = "runner_exception"  # Unhandled Python exception

    # Manual
    manual_abort = "manual_abort"  # User cancelled


class EventType(str, Enum):
    """Event types for events.jsonl. Append-only execution log."""
    # Run lifecycle
    run_queued = "run_queued"
    preflight_started = "preflight_started"
    preflight_failed = "preflight_failed"
    run_started = "run_started"
    run_blocked = "run_blocked"
    run_timed_out = "run_timed_out"
    run_crashed = "run_crashed"
    run_failed = "run_failed"
    run_passed = "run_passed"
    request_written = "request_written"
    dirty_worktree_detected = "dirty_worktree_detected"

    # Round lifecycle
    round_started = "round_started"
    diagnosis_started = "diagnosis_started"
    diagnosis_complete = "diagnosis_complete"
    diagnosis_rejected = "diagnosis_rejected"
    tool_use_started = "tool_use_started"
    tool_use_complete = "tool_use_complete"
    backend_stream_event = "backend_stream_event"
    evidence_collected = "evidence_collected"
    round_scored = "round_scored"
    round_kept = "round_kept"
    round_discarded = "round_discarded"
    round_timeout = "round_timeout"
    zero_write_detected = "zero_write_detected"

    # DoD
    dod_checked = "dod_checked"
    dod_passed = "dod_passed"

    # LogAct-inspired tool-level events (pre-execution intent logging)
    tool_intent = "tool_intent"      # Intent logged BEFORE execution
    tool_result = "tool_result"      # Result logged AFTER execution
    tool_blocked = "tool_blocked"    # Voter rejected the tool call

    # Recovery events
    recovery_started = "recovery_started"    # Crash recovery initiated
    recovery_complete = "recovery_complete"  # Recovery action taken
    failure_diagnosed = "failure_diagnosed"  # Semantic failure analysis


class RunEvent(BaseModel):
    """Schema for events.jsonl entries. ArangoDB-ingestible."""
    run_id: str
    event: EventType
    ts: float  # Unix timestamp
    round: int | None = None
    state_before: RunState | None = None
    state_after: RunState | None = None
    reason_code: ReasonCode | None = None
    payload: dict[str, Any] = Field(default_factory=dict)


class DefinitionOfDone(BaseModel):
    command: str = Field(..., min_length=1, description="Shell command that verifies correctness")
    assertion: str = Field("", description="Substring that must appear in output, or 'exit_code == 0' expression")


class TaskSpec(BaseModel):
    """Input spec for /code-runner. Validated before any execution."""
    task_id: str = Field(..., min_length=1)
    title: str = Field("", description="Human-readable task title")
    prompt: str = Field(..., min_length=20, description="Specific task instructions (>=20 chars)")
    backend: str = Field("codex", description="LLM backend: codex, claude, text, gemini, deepseek")
    lang: str = Field("", description="Language: python, rust, typescript. Empty = auto-detect from cwd")
    cwd: str = Field(..., min_length=1, description="Working directory (must exist)")
    output_dir: str = Field("/tmp/code-runner", description="Where to write logs and results")
    definition_of_done: DefinitionOfDone
    allowlist: list[str] | None = Field(None, description="Files/dirs the LLM can write. None = requires allowlist_optional")
    read_context: list[str] = Field(default_factory=list, description="Files the LLM should READ for context but NOT write. Injected into prompt alongside allowlist files.")
    skills_used: list[str] = Field(default_factory=list, description="Skill names whose SKILL.md is deterministically injected into the LLM prompt. Trust boundary: code reads docs, not the LLM.")
    allowlist_optional: bool = Field(False, description="Set true to allow unrestricted writes")
    dirty_worktree_policy: Literal["isolated_worktree"] = Field(
        "isolated_worktree",
        description="Code-runner always writes in a disposable worktree.",
    )
    # NOTE: blind_tests deliberately NOT in this model. Information barrier:
    # only /orchestrate handles blind_tests, code-runner never parses them.
    max_rounds: int = Field(5, ge=1, le=20)
    timeout_seconds: int = Field(1800, ge=60, le=7200)
    apply_to_source: bool = Field(
        False,
        description="Explicit opt-in complete-task mode: apply the passing allowlist patch to the source repo.",
    )
    commit_on_success: bool = Field(
        False,
        description="When apply_to_source is true, commit allowlisted source changes after source DoD passes.",
    )
    rollback_on_failure: bool = Field(
        True,
        description="When source apply or source DoD fails, restore allowlisted source paths.",
    )

    @field_validator("cwd")
    @classmethod
    def cwd_must_exist(cls, v: str) -> str:
        if not Path(v).exists():
            raise ValueError(f"cwd does not exist: {v}")
        return v

    @field_validator("backend")
    @classmethod
    def backend_must_be_known(cls, v: str) -> str:
        known = {"codex", "claude", "text", "gemini", "deepseek", "test"}
        if v and v not in known:
            raise ValueError(f"Unknown backend '{v}'. Valid: {', '.join(sorted(known))}")
        return v

    @field_validator("lang")
    @classmethod
    def lang_must_be_known(cls, v: str) -> str:
        known = {"", "python", "rust", "typescript", "ts", "node"}
        if v and v.lower() not in known:
            raise ValueError(f"Unknown lang '{v}'. Valid: python, rust, typescript")
        return v.lower()

    @model_validator(mode="after")
    def require_allowlist_or_opt_out(self) -> "TaskSpec":
        if self.allowlist is None and not self.allowlist_optional:
            raise ValueError(
                "allowlist is required. Add specific files: [\"src/auth.py\"] "
                "or directories: [\"scripts/\"]. "
                "Set allowlist_optional: true to allow unrestricted writes."
            )
        return self

    @model_validator(mode="after")
    def validate_source_apply_options(self) -> "TaskSpec":
        if self.commit_on_success and not self.apply_to_source:
            raise ValueError("commit_on_success requires apply_to_source: true")
        return self

    @model_validator(mode="before")
    @classmethod
    def reject_removed_runner_features(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        removed_fields = []
        if data.get("predecessor_patches"):
            removed_fields.append("predecessor_patches")
        if data.get("escalation_chain"):
            removed_fields.append("escalation_chain")
        if removed_fields:
            raise ValueError(
                "Unsupported code-runner field(s): "
                + ", ".join(removed_fields)
                + ". Code-runner v0 self-contained mode accepts one task, one backend, "
                "one disposable worktree, and one allowlist-scoped patch."
            )
        return data

    @model_validator(mode="after")
    def warn_missing_read_context(self) -> "TaskSpec":
        """Detect when prompt references imports/modules not in allowlist or read_context.

        Empirical finding: tasks with 3+ unseen dependencies fail ~50% on text backends.
        This warning tells the project agent to add read_context for referenced files.
        """
        import re
        prompt_lower = self.prompt.lower()
        # Extract module references from prompt (Import X from Y, from Y import X, use Y)
        referenced = set()
        for match in re.findall(r'(?:from|import)\s+(\w+(?:\.\w+)*)', prompt_lower):
            referenced.add(match.split(".")[0])
        for match in re.findall(r'(?:read|use|import|from)\s+(\w+\.py)', prompt_lower):
            referenced.add(match)

        if not referenced:
            return self

        # Check which references are covered by allowlist or read_context
        all_context = set(self.read_context or [])
        if self.allowlist:
            all_context.update(self.allowlist)

        # Normalize: "auth/store.py" covers "auth.store" and "store"
        covered_modules = set()
        for path in all_context:
            # "auth/store.py" → {"auth.store", "store", "auth/store.py"}
            clean = path.rstrip("/").replace("/", ".")
            if clean.endswith(".py"):
                clean = clean[:-3]
            covered_modules.add(clean)
            covered_modules.add(clean.split(".")[-1])
            covered_modules.add(path)

        # Stdlib + common third-party packages that appear in prompts
        # but are NOT project files the LLM needs to read
        KNOWN_PACKAGES = {
            # stdlib
            "sys", "os", "json", "re", "time", "math", "pathlib", "typing",
            "collections", "functools", "hashlib", "base64", "dataclasses",
            "abc", "enum", "io", "subprocess", "tempfile", "shutil", "copy",
            "datetime", "logging", "argparse", "unittest", "contextlib",
            "itertools", "operator", "string", "textwrap", "struct", "csv",
            "sqlite3", "urllib", "http", "socket", "threading", "asyncio",
            "concurrent", "multiprocessing", "inspect", "ast", "dis",
            # common third-party (pip)
            "pydantic", "fastapi", "uvicorn", "starlette", "httpx", "requests",
            "aiohttp", "flask", "django", "sqlalchemy", "alembic",
            "typer", "click", "rich", "loguru", "structlog",
            "numpy", "pandas", "scipy", "sklearn", "torch", "tensorflow",
            "pytest", "hypothesis", "mypy", "ruff", "black",
            "pyyaml", "yaml", "toml", "tomli", "tomllib",
            "boto3", "botocore", "google", "azure",
            "celery", "redis", "pymongo", "psycopg2",
            "jinja2", "mako", "lxml", "beautifulsoup4", "bs4",
            "cryptography", "jwt", "passlib", "bcrypt",
            "pillow", "pil", "matplotlib", "seaborn", "plotly",
            "docker", "paramiko", "fabric",
            "openai", "anthropic", "tiktoken", "transformers", "huggingface",
            "rapidfuzz", "python",
            # JS/TS (appear in TypeScript task prompts)
            "react", "express", "next", "vue", "angular", "svelte",
            "axios", "fetch", "node", "npm", "typescript", "zod",
            "prisma", "drizzle", "sequelize", "mongoose",
            "mui", "tailwind", "chakra", "radix",
        }
        unseen = referenced - covered_modules - KNOWN_PACKAGES
        if len(unseen) >= 3:
            object.__setattr__(self, "_unseen_deps", list(unseen))
            object.__setattr__(self, "_unseen_dep_count", len(unseen))
        return self

    @property
    def unseen_deps(self) -> list[str]:
        return getattr(self, "_unseen_deps", [])

    @property
    def unseen_dep_count(self) -> int:
        return getattr(self, "_unseen_dep_count", 0)

    @model_validator(mode="after")
    def warn_weak_dod(self) -> "TaskSpec":
        dod = self.definition_of_done
        if dod.command and not dod.assertion:
            cmd_lower = dod.command.lower()
            if "assert" not in cmd_lower and "test" not in cmd_lower and "pytest" not in cmd_lower:
                # Attach as metadata — not a hard failure, but a warning
                # The preflight will surface this
                object.__setattr__(self, "_weak_dod", True)
        return self

    @property
    def has_weak_dod(self) -> bool:
        return getattr(self, "_weak_dod", False)

    @model_validator(mode="after")
    def warn_silent_success_dod(self) -> "TaskSpec":
        """Detect DoD commands that produce no stdout on success.

        Commands like `tsc --noEmit`, `ruff check`, `mypy` output nothing
        when they pass (exit 0 only). If the assertion expects a string like
        "passed" or "ok", it will NEVER match — score stuck forever.

        Empirical: this caused score=0.490 stuck across 3 rounds.
        """
        dod = self.definition_of_done
        if not dod.command or not dod.assertion:
            return self

        # Commands that produce no stdout on success
        silent_commands = [
            "tsc --noEmit", "tsc --noemit", "ruff check", "mypy ",
            "flake8 ", "eslint ", "prettier --check",
        ]
        cmd_lower = dod.command.lower()
        assertion_lower = dod.assertion.lower().strip()

        is_silent = any(sc in cmd_lower for sc in silent_commands)
        if not is_silent:
            return self

        # These assertions work with silent commands
        valid_silent_assertions = [
            "exit_code", "exit code", "returncode", "==", "!=",
        ]
        if any(va in assertion_lower for va in valid_silent_assertions):
            return self

        # String assertion on a silent command = guaranteed mismatch
        object.__setattr__(self, "_silent_dod_mismatch", True)
        object.__setattr__(self, "_silent_dod_detail",
            f"'{dod.command}' outputs nothing on success (exit 0 only). "
            f"Assertion '{dod.assertion}' will never match empty stdout. "
            f"Use 'exit_code == 0' instead.")
        return self

    @property
    def has_silent_dod_mismatch(self) -> bool:
        return getattr(self, "_silent_dod_mismatch", False)

    @property
    def silent_dod_detail(self) -> str:
        return getattr(self, "_silent_dod_detail", "")

    @model_validator(mode="after")
    def detect_design_decision(self) -> "TaskSpec":
        """Detect prompts asking code-runner to make architecture/design choices.

        Code-runner is an executor, not an architect. Design decisions belong in /plan.
        Empirical: these tasks waste 3+ rounds and fail.
        """
        import re
        prompt_lower = self.prompt.lower()
        decision_patterns = [
            r"\bchoose\s+(the\s+)?best\b", r"\bdecide\s+(between|whether)\b",
            r"\bwhich\s+(approach|method|library|framework|pattern)\b",
            r"\bbest\s+(way|approach|method|practice)\b",
            r"\bshould\s+(we|i|you)\s+use\b", r"\bcompare\s+and\s+(select|choose)\b",
            r"\bevaluate\s+(options|alternatives|approaches)\b",
        ]
        if any(re.search(p, prompt_lower) for p in decision_patterns):
            object.__setattr__(self, "_design_decision", True)
        return self

    @property
    def is_design_decision(self) -> bool:
        return getattr(self, "_design_decision", False)


class PreflightError(BaseModel):
    """Structured error returned when spec validation fails."""
    field: str
    error: str
    fix: str


class RoundResult(BaseModel):
    """Schema for each round in the experiment log."""
    round: int
    task_id: str = ""
    score: float
    prev_score: float = 0
    delta: float = 0
    dod_passed: bool
    status: str  # keep | discard
    strategy: str
    error_count: int = 0
    error_severity: str = "unknown"
    errors_by_type: dict[str, int] = Field(default_factory=dict)
    lint_violations: int = 0
    bp_violations: list[str] = Field(default_factory=list)
    error_evidence: dict[str, Any] | None = None
    stdout: str = ""
    stderr: str = ""
    written_files: list[str] = Field(default_factory=list)
    commit: str = ""
    backend: str = ""
    reasoning: str = ""
    temperature: float = 0.2
    timestamp: float = 0


class TaskResult(BaseModel):
    """Schema for the final result.json output."""
    task_id: str
    title: str = ""
    status: str  # pass | fail | preflight_fail | timeout | stash_conflict
    rounds: int = 0
    best_score: float = 0
    dod_passed: bool = False
    backend: str = ""
    best_commit: str = ""
    error: str = ""  # actionable error message for calling agent
    round_details: list[dict[str, Any]] = Field(default_factory=list)
    preflight_errors: list[PreflightError] = Field(default_factory=list)
    course_correction: dict[str, Any] = Field(default_factory=dict)
    execution_mode: str = ""
    patch_artifact: str = ""
    worktree_path: str = ""
    worktree_removed: bool = False
    apply_to_source: bool = False
    source_patch_applied: bool = False
    source_commit: str = ""
    source_dod_passed: bool = False
    source_rollback_applied: bool = False
    source_apply_error: str = ""
