"""Misuse detection for /code-runner task specs.

Project agents frequently misuse code-runner because they skim SKILL.md.
This module catches common mistakes at task spec validation time and:
1. Returns helpful error messages that teach correct usage
2. Logs events to /memory for nightly /monitor-misuse analysis

Adapted from best-practices-skills/references/misuse_guard_template.py

Common misuse patterns:
- Wrong backend names (gpt, openai, anthropic → codex, claude, text)
- Grep-based DoD assertions (gameable by LLM)
- Missing allowlist on large prompts
- Design decision prompts (architecture belongs in /plan)
- Weak/empty prompts with no file references
"""
from __future__ import annotations

import hashlib
import re
import time
from dataclasses import dataclass
from typing import Any

from loguru import logger


# ============================================================================
# Misuse Event Logging (to /memory for nightly analysis)
# ============================================================================

def log_misuse_event(
    error_type: str,
    sent_value: str,
    correct_value: str | None = None,
    task_id: str = "unknown",
) -> None:
    """Log misuse to /memory for nightly /monitor-misuse analysis.

    Events are stored in the `misuse_events` collection. The nightly job
    clusters unknown patterns and proposes new corrections.
    """
    try:
        import httpx

        # Deterministic key: same misuse = same key (for counting, not duplicating)
        key_source = f"code-runner:preflight:{error_type}:{sent_value}"
        doc_key = hashlib.sha256(key_source.encode()).hexdigest()[:16]

        transport = httpx.HTTPTransport(uds="/run/user/1000/embry/memory.sock")
        with httpx.Client(transport=transport, base_url="http://localhost", timeout=2.0) as client:
            resp = client.post("/store", json={
                "document": {
                    "_key": doc_key,
                    "skill": "code-runner",
                    "endpoint": "preflight",
                    "error_type": error_type,
                    "sent_value": sent_value[:500],  # Cap for storage
                    "correct_value": correct_value,
                    "was_known": correct_value is not None,
                    "task_id": task_id,
                    "ts": int(time.time()),
                    "count": 1,
                },
                "collection": "misuse_events",
            })
            if resp.status_code != 200:
                logger.debug("Failed to log misuse event: {}", resp.status_code)
    except Exception as exc:
        # Never fail the request due to logging failure
        logger.debug("Misuse event logging failed (non-fatal): {}", exc)


# ============================================================================
# Corrections Maps (known misuse patterns → correct values)
# ============================================================================

# Backend name corrections — agents often use provider names instead of our aliases
BACKEND_CORRECTIONS: dict[str, str] = {
    # OpenAI variants
    "gpt": "codex",
    "gpt-4": "codex",
    "gpt-5": "codex",
    "openai": "codex",
    "chatgpt": "codex",
    "o1": "codex",
    "o3": "codex",
    # Anthropic variants
    "anthropic": "claude",
    "sonnet": "claude",
    "opus": "claude",
    "haiku": "claude",
    # Google variants
    "google": "gemini",
    "palm": "gemini",
    "bard": "gemini",
    # DeepSeek
    "deepseek-coder": "deepseek",
    "deepseek-v3": "deepseek",
    # Generic
    "llm": "text",
    "default": "text",
}

# DoD assertion patterns that are gameable
GAMEABLE_DOD_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"grep\s+['\"]?\w+['\"]?\s+\w+\.(py|js|ts)"),
     "grep-based assertion can be gamed by adding a comment. Use execution-based check instead."),
    (re.compile(r"cat\s+.*\|\s*grep"),
     "cat|grep assertion can be gamed. Run the code and check output instead."),
    (re.compile(r"test\s+-f\s+"),
     "File existence check is weak. Verify file content or run the code."),
    (re.compile(r"wc\s+-l"),
     "Line count check is weak. Verify actual content or behavior."),
]

# Prompt patterns that indicate design decisions (should use /plan instead)
DESIGN_DECISION_PATTERNS: list[re.Pattern] = [
    re.compile(r"\b(should\s+I|should\s+we|which\s+(is\s+better|approach|method))\b", re.I),
    re.compile(r"\b(decide|choose|pick)\s+(between|whether)\b", re.I),
    re.compile(r"\b(REST\s+or\s+GraphQL|SQL\s+or\s+NoSQL|monolith\s+or\s+microservice)\b", re.I),
    re.compile(r"\b(what\s+architecture|design\s+the\s+system|plan\s+the)\b", re.I),
]


# ============================================================================
# Validation Functions
# ============================================================================

@dataclass
class MisuseWarning:
    """A non-fatal warning about potential misuse."""
    field: str
    message: str
    suggestion: str


@dataclass
class MisuseError:
    """A fatal error due to misuse."""
    field: str
    error_type: str
    message: str
    sent_value: str
    correct_value: str | None = None


def check_backend(backend: str) -> MisuseError | None:
    """Check if backend name is a known misuse pattern."""
    lower = backend.lower().strip()
    if lower in BACKEND_CORRECTIONS:
        correct = BACKEND_CORRECTIONS[lower]
        return MisuseError(
            field="backend",
            error_type="wrong_backend",
            message=f"Backend '{backend}' is not recognized. Use '{correct}' instead. "
                    f"Valid backends: codex, claude, text, gemini, deepseek.",
            sent_value=backend,
            correct_value=correct,
        )
    return None


def check_dod_gameable(dod_command: str, dod_assertion: str | None) -> MisuseWarning | None:
    """Check if DoD assertion is gameable."""
    check_text = f"{dod_command} {dod_assertion or ''}"
    for pattern, message in GAMEABLE_DOD_PATTERNS:
        if pattern.search(check_text):
            return MisuseWarning(
                field="definition_of_done",
                message=f"DoD may be gameable: {message}",
                suggestion="Use a command that RUNS the code and checks OUTPUT, not file content. "
                          "Example: python3 -c 'from module import func; assert func(x) == y'",
            )
    return None


def check_design_decision(prompt: str) -> MisuseError | None:
    """Check if prompt asks for design decisions instead of implementation."""
    for pattern in DESIGN_DECISION_PATTERNS:
        match = pattern.search(prompt)
        if match:
            return MisuseError(
                field="prompt",
                error_type="design_decision",
                message=f"Prompt appears to ask for a DESIGN DECISION ('{match.group()}'). "
                        f"Code-runner is an executor, not an architect. "
                        f"Use /plan for architecture choices, then tell code-runner 'implement X using Y'.",
                sent_value=prompt[:200],
                correct_value=None,
            )
    return None


def check_weak_prompt(prompt: str, allowlist: list[str] | None) -> MisuseWarning | None:
    """Check if prompt is too vague."""
    # Very short prompt
    if len(prompt.strip()) < 50:
        return MisuseWarning(
            field="prompt",
            message=f"Prompt is only {len(prompt.strip())} chars — likely too vague.",
            suggestion="Include: which file to read, what's broken, what the fix should do. Min 50 chars.",
        )

    # No file references and no allowlist
    file_pattern = re.compile(r'\b[\w/]+\.(py|js|ts|tsx|jsx|json|yaml|yml|sh|md)\b')
    if not file_pattern.search(prompt) and not allowlist:
        return MisuseWarning(
            field="prompt",
            message="Prompt has no file references and no allowlist specified.",
            suggestion="Add specific file paths to the prompt, or set allowlist to constrain writes.",
        )

    return None


def check_missing_allowlist(prompt: str, allowlist: list[str] | None, allowlist_optional: bool) -> MisuseWarning | None:
    """Warn if no allowlist on a large prompt."""
    if allowlist is None and not allowlist_optional and len(prompt) > 500:
        return MisuseWarning(
            field="allowlist",
            message="No allowlist specified on a large prompt. LLM can write anywhere under cwd.",
            suggestion="Add allowlist: ['path/to/file.py'] to constrain which files can be modified.",
        )
    return None


def check_dod_missing(dod: dict | None) -> MisuseError | None:
    """Check if definition_of_done is missing or empty."""
    if not dod:
        return MisuseError(
            field="definition_of_done",
            error_type="missing_dod",
            message="definition_of_done is REQUIRED. Without it, code-runner has no way to verify success. "
                    "Add a command that RUNS the code and checks OUTPUT.",
            sent_value="(missing)",
            correct_value='{"command": "python3 -c \'from module import func; print(func(x))\'", "assertion": "expected_output"}',
        )

    command = dod.get("command", "")
    if not command or not command.strip():
        return MisuseError(
            field="definition_of_done.command",
            error_type="empty_dod_command",
            message="definition_of_done.command is empty. This MUST be a shell command that verifies correctness.",
            sent_value="(empty)",
            correct_value="python3 -c 'from module import func; assert func(test_input) == expected; print(OK)'",
        )

    return None


def validate_task_spec(spec: dict[str, Any], task_id: str = "unknown") -> tuple[list[MisuseError], list[MisuseWarning]]:
    """Validate a task spec for common misuse patterns.

    Returns:
        (errors, warnings) — errors are fatal, warnings are logged but don't block
    """
    errors: list[MisuseError] = []
    warnings: list[MisuseWarning] = []

    # Backend check
    backend = spec.get("backend", "")
    if backend:
        err = check_backend(backend)
        if err:
            errors.append(err)
            log_misuse_event(err.error_type, err.sent_value, err.correct_value, task_id)

    # DoD checks
    dod = spec.get("definition_of_done")
    dod_err = check_dod_missing(dod)
    if dod_err:
        errors.append(dod_err)
        log_misuse_event(dod_err.error_type, dod_err.sent_value, dod_err.correct_value, task_id)
    elif dod:
        gameable = check_dod_gameable(dod.get("command", ""), dod.get("assertion"))
        if gameable:
            warnings.append(gameable)
            log_misuse_event("gameable_dod", dod.get("command", "")[:200], gameable.suggestion, task_id)

    # Prompt checks
    prompt = spec.get("prompt", "")
    if prompt:
        design_err = check_design_decision(prompt)
        if design_err:
            errors.append(design_err)
            log_misuse_event(design_err.error_type, design_err.sent_value, design_err.correct_value, task_id)

        weak = check_weak_prompt(prompt, spec.get("allowlist"))
        if weak:
            warnings.append(weak)
            log_misuse_event("weak_prompt", prompt[:200], weak.suggestion, task_id)

    # Allowlist check
    allowlist_warn = check_missing_allowlist(
        prompt,
        spec.get("allowlist"),
        spec.get("allowlist_optional", False),
    )
    if allowlist_warn:
        warnings.append(allowlist_warn)

    return errors, warnings


def format_misuse_errors(errors: list[MisuseError], warnings: list[MisuseWarning]) -> str:
    """Format misuse errors and warnings into a helpful message."""
    lines = []

    if errors:
        lines.append("=== TASK SPEC MISUSE DETECTED ===")
        lines.append("")
        for err in errors:
            lines.append(f"[{err.field}] {err.message}")
            if err.correct_value:
                lines.append(f"  CORRECT: {err.correct_value}")
            lines.append("")

    if warnings:
        lines.append("=== WARNINGS (non-fatal) ===")
        lines.append("")
        for warn in warnings:
            lines.append(f"[{warn.field}] {warn.message}")
            lines.append(f"  SUGGESTION: {warn.suggestion}")
            lines.append("")

    if errors or warnings:
        lines.append("See SKILL.md for full documentation: .pi/skills/code-runner/SKILL.md")

    return "\n".join(lines)
