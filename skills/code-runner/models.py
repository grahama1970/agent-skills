"""Pydantic models for /code-runner spec validation and result schema.

Declarative guardrails — bad types, missing fields, and invalid values
caught at parse time before any LLM call, git operation, or subprocess.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator


class DefinitionOfDone(BaseModel):
    command: str = Field(..., min_length=1, description="Shell command that verifies correctness")
    assertion: str = Field("", description="Substring that must appear in output, or 'exit_code == 0' expression")


class TaskSpec(BaseModel):
    """Input spec for /code-runner. Validated before any execution."""
    task_id: str = Field(..., min_length=1)
    title: str = Field("", description="Human-readable task title")
    prompt: str = Field(..., min_length=20, description="Specific task instructions (>=20 chars)")
    backend: str = Field("codex", description="LLM backend: codex, claude, text, gemini, deepseek")
    cwd: str = Field(..., min_length=1, description="Working directory (must exist)")
    output_dir: str = Field("/tmp/code-runner", description="Where to write logs and results")
    definition_of_done: DefinitionOfDone
    allowlist: list[str] | None = Field(None, description="Files/dirs the LLM can write. None = requires allowlist_optional")
    read_context: list[str] = Field(default_factory=list, description="Files the LLM should READ for context but NOT write. Injected into prompt alongside allowlist files.")
    skills_used: list[str] = Field(default_factory=list, description="Skill names whose SKILL.md is deterministically injected into the LLM prompt. Trust boundary: code reads docs, not the LLM.")
    allowlist_optional: bool = Field(False, description="Set true to allow unrestricted writes")
    # NOTE: blind_tests deliberately NOT in this model. Information barrier:
    # only /orchestrate handles blind_tests, code-runner never parses them.
    max_rounds: int = Field(5, ge=1, le=20)
    escalation_chain: list[list[str]] | None = Field(None, description="Override: [[backend, reasoning], ...]")

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
