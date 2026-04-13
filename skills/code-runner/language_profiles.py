"""Language-specific execution profiles for code-runner.

Each profile knows how to:
- Detect its language from repo markers
- Run syntax/compile checks
- Run tests
- Parse error output into structured severity
- Check best practices

The core loop (scoring, git ops, strategy escalation) stays in code_runner.py.
Only the language-specific checks are in the profile.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol, runtime_checkable

from loguru import logger


@dataclass
class LintResult:
    """Lint/typecheck output."""
    violations: int = 0
    details: list[str] = field(default_factory=list)
    tool_available: bool = True  # False when linter not installed


@dataclass
class ErrorClassification:
    """Parsed error output."""
    error_types: dict[str, int] = field(default_factory=dict)
    total: int = 0
    severity: str = "unknown"


@dataclass
class BestPracticeViolations:
    """Best practice check results."""
    violations: list[str] = field(default_factory=list)


@runtime_checkable
class LanguageProfile(Protocol):
    """Protocol for language-specific execution profiles."""

    name: str

    def detect(self, cwd: str) -> bool:
        """Return True if this profile should handle the given directory."""
        ...

    def syntax_check(self, files: list[str], cwd: str) -> ErrorClassification:
        """Fast syntax check before execution. Returns errors found."""
        ...

    def lint_check(self, files: list[str], cwd: str) -> LintResult:
        """Lint/style check. Returns violation count."""
        ...

    def typecheck(self, files: list[str], cwd: str) -> LintResult:
        """Type check (mypy, tsc, etc). Returns violation count."""
        ...

    def run_tests(self, cwd: str, test_command: str | None = None) -> tuple[str, str, int]:
        """Run tests. Returns (stdout, stderr, exit_code)."""
        ...

    def classify_errors(self, stderr: str, stdout: str = "") -> ErrorClassification:
        """Parse output for error types. Returns classification."""
        ...

    def best_practices(self, diff_text: str) -> BestPracticeViolations:
        """Check diff for best practice violations."""
        ...

    def get_modified_files(self, cwd: str) -> list[str]:
        """Get list of modified files for this language."""
        ...


# ── Python Profile ────────────────────────────────────────────────────────────


class PythonProfile:
    """Python execution profile. Uses ruff, mypy, pytest."""

    name = "python"

    # Error patterns for classification
    ERROR_PATTERNS = {
        "SyntaxError": "syntax", "IndentationError": "syntax",
        "ImportError": "import", "ModuleNotFoundError": "import",
        "TypeError": "contract", "AttributeError": "contract", "KeyError": "contract",
        "NameError": "contract",
        "AssertionError": "logic", "ValueError": "logic", "IndexError": "logic",
        "RuntimeError": "runtime", "FileNotFoundError": "runtime", "TimeoutError": "runtime",
    }

    # Best practice checks
    BP_CHECKS = [
        ("import logging", "Use 'from loguru import logger'"),
        ("import requests", "Use 'httpx'"),
        ("import argparse", "Use 'typer'"),
    ]

    def detect(self, cwd: str) -> bool:
        """Detect Python project by pyproject.toml, setup.py, or .py files."""
        cwd_path = Path(cwd)
        return (
            (cwd_path / "pyproject.toml").exists() or
            (cwd_path / "setup.py").exists() or
            any(cwd_path.glob("**/*.py"))
        )

    def syntax_check(self, files: list[str], cwd: str) -> ErrorClassification:
        """Use Python's compile() for fast syntax check."""
        errors: dict[str, int] = {}
        for f in files:
            if not f.endswith(".py"):
                continue
            fpath = Path(cwd) / f
            if not fpath.exists():
                continue
            try:
                compile(fpath.read_text(errors="replace"), str(fpath), "exec")
            except SyntaxError as e:
                error_type = type(e).__name__
                errors[error_type] = errors.get(error_type, 0) + 1
        total = sum(errors.values())
        severity = "syntax" if errors else "unknown"
        return ErrorClassification(error_types=errors, total=total, severity=severity)

    def lint_check(self, files: list[str], cwd: str) -> LintResult:
        """Run ruff check on files."""
        py_files = [f for f in files if f.endswith(".py")]
        if not py_files:
            return LintResult()
        try:
            proc = subprocess.run(
                ["ruff", "check", "--output-format", "json", *py_files],
                capture_output=True, text=True, cwd=cwd, timeout=30,
            )
            try:
                violations = json.loads(proc.stdout or "[]")
                count = len(violations) if isinstance(violations, list) else 0
                details = [f"{v.get('filename')}:{v.get('location', {}).get('row')}: {v.get('code')} {v.get('message')}"
                          for v in (violations if isinstance(violations, list) else [])[:5]]
                return LintResult(violations=count, details=details)
            except json.JSONDecodeError:
                return LintResult(violations=proc.returncode)
        except FileNotFoundError:
            return LintResult(tool_available=False, details=["ruff not installed"])
        except subprocess.SubprocessError:
            return LintResult()

    def typecheck(self, files: list[str], cwd: str) -> LintResult:
        """Run mypy on files (if available)."""
        py_files = [f for f in files if f.endswith(".py")]
        if not py_files:
            return LintResult()
        try:
            proc = subprocess.run(
                ["mypy", "--ignore-missing-imports", *py_files],
                capture_output=True, text=True, cwd=cwd, timeout=60,
            )
            # Count error lines
            errors = [l for l in proc.stdout.splitlines() if ": error:" in l]
            return LintResult(violations=len(errors), details=errors[:5])
        except FileNotFoundError:
            return LintResult(tool_available=False, details=["mypy not installed"])
        except subprocess.SubprocessError:
            return LintResult()

    def run_tests(self, cwd: str, test_command: str | None = None) -> tuple[str, str, int]:
        """Run pytest or custom test command."""
        cmd = test_command or "python -m pytest -q"
        try:
            env = self._clean_env()
            proc = subprocess.run(
                ["bash", "-lc", cmd],
                capture_output=True, text=True, timeout=120, cwd=cwd, env=env,
            )
            return proc.stdout, proc.stderr, proc.returncode
        except subprocess.TimeoutExpired:
            return "", "Test command timed out after 120s", 1
        except Exception as e:
            return "", f"Test error: {e}", 1

    def classify_errors(self, stderr: str, stdout: str = "") -> ErrorClassification:
        """Parse stderr for Python error types."""
        errors_by_type: dict[str, int] = {}
        for pattern in self.ERROR_PATTERNS:
            count = len(re.findall(rf"\b{re.escape(pattern)}\b", stderr))
            if count:
                errors_by_type[pattern] = count

        total = sum(errors_by_type.values())

        # Determine severity from highest-priority error
        severity = "unknown"
        priority = ["syntax", "import", "contract", "logic", "runtime"]
        for sev in priority:
            for error_type, s in self.ERROR_PATTERNS.items():
                if s == sev and error_type in errors_by_type:
                    severity = sev
                    break
            if severity != "unknown":
                break

        return ErrorClassification(error_types=errors_by_type, total=total, severity=severity)

    def best_practices(self, diff_text: str) -> BestPracticeViolations:
        """Check diff for Python best practice violations."""
        violations = []
        for pattern, msg in self.BP_CHECKS:
            if f"+{pattern}" in diff_text or f"+ {pattern}" in diff_text:
                violations.append(msg)
        return BestPracticeViolations(violations=violations)

    def get_modified_files(self, cwd: str) -> list[str]:
        """Get modified Python files from git."""
        try:
            proc = subprocess.run(
                ["git", "diff", "--name-only", "HEAD"],
                capture_output=True, text=True, cwd=cwd, timeout=30,
            )
            return [f.strip() for f in proc.stdout.splitlines() if f.strip().endswith(".py")]
        except subprocess.SubprocessError:
            return []

    def _clean_env(self) -> dict[str, str]:
        """Strip .venv paths from environment."""
        env = {k: v for k, v in os.environ.items() if k != "VIRTUAL_ENV"}
        env["PATH"] = os.pathsep.join(
            p for p in env.get("PATH", "").split(os.pathsep)
            if ".venv" not in p
        )
        return env


# ── Rust Profile ──────────────────────────────────────────────────────────────


class RustProfile:
    """Rust execution profile. Uses cargo check, cargo test, rustc errors."""

    name = "rust"

    # Rustc error codes to severity
    ERROR_PATTERNS = {
        # Syntax/parse errors (E0XXX)
        r"error\[E0": "syntax",
        r"error: expected": "syntax",
        r"error: mismatched types": "contract",
        r"error\[E0308\]": "contract",  # mismatched types
        r"error\[E0412\]": "import",    # cannot find type
        r"error\[E0432\]": "import",    # unresolved import
        r"error\[E0433\]": "import",    # failed to resolve
        r"error\[E0425\]": "contract",  # cannot find value
        r"error\[E0599\]": "contract",  # no method named
        r"cannot find": "import",
        r"panicked at": "runtime",
        r"assertion .* failed": "logic",
        r"thread .* panicked": "runtime",
    }

    def detect(self, cwd: str) -> bool:
        """Detect Rust project by Cargo.toml."""
        return (Path(cwd) / "Cargo.toml").exists()

    def syntax_check(self, files: list[str], cwd: str) -> ErrorClassification:
        """Use cargo check for fast syntax/type check."""
        try:
            proc = subprocess.run(
                ["cargo", "check", "--message-format=json"],
                capture_output=True, text=True, cwd=cwd, timeout=120,
            )
            return self._parse_cargo_output(proc.stdout, proc.stderr)
        except (FileNotFoundError, subprocess.SubprocessError) as e:
            return ErrorClassification(error_types={"CargoError": 1}, total=1, severity="syntax")

    def lint_check(self, files: list[str], cwd: str) -> LintResult:
        """Run cargo clippy for linting."""
        try:
            proc = subprocess.run(
                ["cargo", "clippy", "--message-format=json", "--", "-D", "warnings"],
                capture_output=True, text=True, cwd=cwd, timeout=120,
            )
            # Count warning/error lines in JSON output
            violations = 0
            details = []
            for line in proc.stdout.splitlines():
                try:
                    msg = json.loads(line)
                    if msg.get("reason") == "compiler-message":
                        level = msg.get("message", {}).get("level", "")
                        if level in ("warning", "error"):
                            violations += 1
                            rendered = msg.get("message", {}).get("rendered", "")
                            if rendered and len(details) < 5:
                                details.append(rendered.split("\n")[0][:200])
                except json.JSONDecodeError:
                    pass
            return LintResult(violations=violations, details=details)
        except FileNotFoundError:
            return LintResult(tool_available=False, details=["cargo clippy not installed"])
        except subprocess.SubprocessError:
            return LintResult()

    def typecheck(self, files: list[str], cwd: str) -> LintResult:
        """Rust type checking is part of cargo check/build."""
        # Already done in syntax_check, return empty
        return LintResult()

    def run_tests(self, cwd: str, test_command: str | None = None) -> tuple[str, str, int]:
        """Run cargo test."""
        cmd = test_command or "cargo test"
        try:
            proc = subprocess.run(
                ["bash", "-lc", cmd],
                capture_output=True, text=True, timeout=300, cwd=cwd,
            )
            return proc.stdout, proc.stderr, proc.returncode
        except subprocess.TimeoutExpired:
            return "", "cargo test timed out after 300s", 1
        except Exception as e:
            return "", f"Test error: {e}", 1

    def classify_errors(self, stderr: str, stdout: str = "") -> ErrorClassification:
        """Parse cargo/rustc output for error types."""
        combined = f"{stderr}\n{stdout}"
        errors_by_type: dict[str, int] = {}

        for pattern, severity in self.ERROR_PATTERNS.items():
            count = len(re.findall(pattern, combined, re.IGNORECASE))
            if count:
                # Use pattern as type name for clarity
                type_name = pattern.replace(r"\[", "[").replace(r"\]", "]").replace(r"\\", "")
                errors_by_type[type_name] = errors_by_type.get(type_name, 0) + count

        total = sum(errors_by_type.values())

        # Determine severity (first match wins, ordered by priority)
        severity = "unknown"
        priority_order = ["syntax", "import", "contract", "logic", "runtime"]
        for sev in priority_order:
            for pattern, s in self.ERROR_PATTERNS.items():
                if s == sev and re.search(pattern, combined, re.IGNORECASE):
                    severity = sev
                    break
            if severity != "unknown":
                break

        return ErrorClassification(error_types=errors_by_type, total=total, severity=severity)

    def best_practices(self, diff_text: str) -> BestPracticeViolations:
        """Check diff for Rust best practice violations."""
        violations = []
        checks = [
            ("unwrap()", "Use '?' or 'expect()' with context message"),
            (".clone()", "Avoid unnecessary clones — check if borrowing works"),
            ("unsafe {", "Justify unsafe blocks in comments"),
        ]
        for pattern, msg in checks:
            if f"+{pattern}" in diff_text or f"+ {pattern}" in diff_text:
                violations.append(msg)
        return BestPracticeViolations(violations=violations)

    def get_modified_files(self, cwd: str) -> list[str]:
        """Get modified Rust files from git."""
        try:
            proc = subprocess.run(
                ["git", "diff", "--name-only", "HEAD"],
                capture_output=True, text=True, cwd=cwd, timeout=30,
            )
            return [f.strip() for f in proc.stdout.splitlines() if f.strip().endswith(".rs")]
        except subprocess.SubprocessError:
            return []

    def _parse_cargo_output(self, stdout: str, stderr: str) -> ErrorClassification:
        """Parse cargo JSON output for errors."""
        errors_by_type: dict[str, int] = {}
        for line in stdout.splitlines():
            try:
                msg = json.loads(line)
                if msg.get("reason") == "compiler-message":
                    level = msg.get("message", {}).get("level", "")
                    code = msg.get("message", {}).get("code", {})
                    if level == "error":
                        code_str = code.get("code", "E0000") if isinstance(code, dict) else "E0000"
                        errors_by_type[code_str] = errors_by_type.get(code_str, 0) + 1
            except json.JSONDecodeError:
                pass

        # Also parse stderr for non-JSON errors
        stderr_errors = self.classify_errors(stderr, "")
        for k, v in stderr_errors.error_types.items():
            errors_by_type[k] = errors_by_type.get(k, 0) + v

        total = sum(errors_by_type.values())
        # Severity from the most severe error
        severity = stderr_errors.severity if stderr_errors.total > 0 else ("syntax" if total > 0 else "unknown")
        return ErrorClassification(error_types=errors_by_type, total=total, severity=severity)


# ── TypeScript/Node Profile ───────────────────────────────────────────────────


class TypeScriptProfile:
    """TypeScript/Node execution profile. Uses tsc, eslint, npm/bun test."""

    name = "typescript"

    # TypeScript/Node error patterns
    ERROR_PATTERNS = {
        r"SyntaxError": "syntax",
        r"TS\d{4}:": "syntax",  # TypeScript errors (e.g., TS2304)
        r"error TS\d{4}": "syntax",
        r"Cannot find module": "import",
        r"Module not found": "import",
        r"TypeError": "contract",
        r"ReferenceError": "contract",
        r"is not a function": "contract",
        r"undefined is not": "contract",
        r"null is not": "contract",
        r"AssertionError": "logic",
        r"Expected .* to": "logic",  # Jest/Vitest assertions
        r"expect\(": "logic",
        r"Error:": "runtime",
        r"ENOENT": "runtime",
        r"EACCES": "runtime",
    }

    def detect(self, cwd: str) -> bool:
        """Detect TS/Node project by package.json or tsconfig.json."""
        cwd_path = Path(cwd)
        return (
            (cwd_path / "package.json").exists() or
            (cwd_path / "tsconfig.json").exists()
        )

    def syntax_check(self, files: list[str], cwd: str) -> ErrorClassification:
        """Use tsc --noEmit for syntax/type check."""
        try:
            # Prefer npx tsc to handle local installs
            proc = subprocess.run(
                ["npx", "tsc", "--noEmit"],
                capture_output=True, text=True, cwd=cwd, timeout=120,
            )
            return self.classify_errors(proc.stderr, proc.stdout)
        except (FileNotFoundError, subprocess.SubprocessError):
            return ErrorClassification()

    def lint_check(self, files: list[str], cwd: str) -> LintResult:
        """Run eslint on files."""
        ts_files = [f for f in files if f.endswith((".ts", ".tsx", ".js", ".jsx"))]
        if not ts_files:
            return LintResult()
        try:
            proc = subprocess.run(
                ["npx", "eslint", "--format", "json", *ts_files],
                capture_output=True, text=True, cwd=cwd, timeout=60,
            )
            try:
                results = json.loads(proc.stdout or "[]")
                total = sum(len(r.get("messages", [])) for r in results)
                details = []
                for r in results[:3]:
                    for msg in r.get("messages", [])[:2]:
                        details.append(f"{r.get('filePath', '')}:{msg.get('line')}: {msg.get('message')}")
                return LintResult(violations=total, details=details[:5])
            except json.JSONDecodeError:
                return LintResult(violations=proc.returncode if proc.returncode else 0)
        except FileNotFoundError:
            return LintResult(tool_available=False, details=["eslint not installed"])
        except subprocess.SubprocessError:
            return LintResult()

    def typecheck(self, files: list[str], cwd: str) -> LintResult:
        """TypeScript type checking via tsc."""
        try:
            proc = subprocess.run(
                ["npx", "tsc", "--noEmit"],
                capture_output=True, text=True, cwd=cwd, timeout=120,
            )
            # Count error lines
            errors = [l for l in proc.stdout.splitlines() if "error TS" in l]
            return LintResult(violations=len(errors), details=errors[:5])
        except FileNotFoundError:
            return LintResult(tool_available=False, details=["tsc not installed"])
        except subprocess.SubprocessError:
            return LintResult()

    def run_tests(self, cwd: str, test_command: str | None = None) -> tuple[str, str, int]:
        """Run npm test, bun test, or custom command."""
        if test_command:
            cmd = test_command
        else:
            # Detect test runner from package.json
            pkg_json = Path(cwd) / "package.json"
            if pkg_json.exists():
                try:
                    pkg = json.loads(pkg_json.read_text())
                    scripts = pkg.get("scripts", {})
                    if "test" in scripts:
                        # Check for bun.lockb to use bun
                        if (Path(cwd) / "bun.lockb").exists():
                            cmd = "bun test"
                        else:
                            cmd = "npm test"
                    else:
                        cmd = "npm test"
                except (json.JSONDecodeError, IOError):
                    cmd = "npm test"
            else:
                cmd = "npm test"

        try:
            proc = subprocess.run(
                ["bash", "-lc", cmd],
                capture_output=True, text=True, timeout=180, cwd=cwd,
            )
            return proc.stdout, proc.stderr, proc.returncode
        except subprocess.TimeoutExpired:
            return "", "Test command timed out after 180s", 1
        except Exception as e:
            return "", f"Test error: {e}", 1

    def classify_errors(self, stderr: str, stdout: str = "") -> ErrorClassification:
        """Parse TS/Node output for error types."""
        combined = f"{stderr}\n{stdout}"
        errors_by_type: dict[str, int] = {}

        for pattern, severity in self.ERROR_PATTERNS.items():
            count = len(re.findall(pattern, combined, re.IGNORECASE))
            if count:
                # Clean pattern for type name
                type_name = pattern.replace(r"\d{4}", "XXXX").replace(r"\(", "(").replace(r"\)", ")")
                errors_by_type[type_name] = errors_by_type.get(type_name, 0) + count

        total = sum(errors_by_type.values())

        # Determine severity
        severity = "unknown"
        priority_order = ["syntax", "import", "contract", "logic", "runtime"]
        for sev in priority_order:
            for pattern, s in self.ERROR_PATTERNS.items():
                if s == sev and re.search(pattern, combined, re.IGNORECASE):
                    severity = sev
                    break
            if severity != "unknown":
                break

        return ErrorClassification(error_types=errors_by_type, total=total, severity=severity)

    def best_practices(self, diff_text: str) -> BestPracticeViolations:
        """Check diff for TS/Node best practice violations."""
        violations = []
        checks = [
            ("console.log", "Remove console.log before commit"),
            (": any", "Avoid 'any' type — use specific types"),
            ("as any", "Avoid type assertions to 'any'"),
            ("// @ts-ignore", "Fix the type error instead of ignoring"),
            ("// @ts-expect-error", "Consider fixing the underlying type issue"),
        ]
        for pattern, msg in checks:
            if f"+{pattern}" in diff_text or f"+ {pattern}" in diff_text:
                violations.append(msg)
        return BestPracticeViolations(violations=violations)

    def get_modified_files(self, cwd: str) -> list[str]:
        """Get modified TS/JS files from git."""
        try:
            proc = subprocess.run(
                ["git", "diff", "--name-only", "HEAD"],
                capture_output=True, text=True, cwd=cwd, timeout=30,
            )
            extensions = (".ts", ".tsx", ".js", ".jsx")
            return [f.strip() for f in proc.stdout.splitlines() if f.strip().endswith(extensions)]
        except subprocess.SubprocessError:
            return []


# ── Profile Registry ──────────────────────────────────────────────────────────


# All available profiles
PROFILES: dict[str, LanguageProfile] = {
    "python": PythonProfile(),
    "rust": RustProfile(),
    "typescript": TypeScriptProfile(),
    "ts": TypeScriptProfile(),  # alias
    "node": TypeScriptProfile(),  # alias
}


def get_profile(lang: str | None, cwd: str | None = None) -> LanguageProfile:
    """Get profile by name or auto-detect from cwd.

    Args:
        lang: Explicit language name (python, rust, typescript, ts, node)
        cwd: Working directory for auto-detection (if lang is None)

    Returns:
        LanguageProfile for the specified/detected language.
        Falls back to PythonProfile if nothing detected.
    """
    # Explicit language
    if lang:
        profile = PROFILES.get(lang.lower())
        if profile:
            return profile
        logger.warning("Unknown language '{}', falling back to python", lang)
        return PROFILES["python"]

    # Auto-detect from cwd
    if cwd:
        # Priority order: Rust (more specific) > TypeScript > Python (most common)
        for name in ["rust", "typescript", "python"]:
            profile = PROFILES[name]
            if profile.detect(cwd):
                logger.info("Auto-detected language: {}", name)
                return profile

    # Default to Python
    return PROFILES["python"]


def detect_language(cwd: str) -> str:
    """Detect language from cwd, return name string."""
    for name in ["rust", "typescript", "python"]:
        if PROFILES[name].detect(cwd):
            return name
    return "python"
