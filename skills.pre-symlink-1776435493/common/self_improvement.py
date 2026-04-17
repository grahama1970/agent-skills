"""Shared self-improvement loop patterns for code-runner, prompt-lab, classifier-lab.

Extracts common patterns from code-runner's autoresearch implementation:
- Strategy escalation (5-step)
- Keep/discard decision with epsilon threshold
- Error severity classification
- Round entry structure for logging

These patterns are domain-agnostic — the calling skill provides the scoring
function and domain-specific evidence collection.

Usage:
    from self_improvement import (
        Strategy, get_strategy, should_keep, ErrorSeverity,
        classify_error_severity, RoundEntry,
    )

    # Get escalation strategy based on round and error trajectory
    strategy = get_strategy(
        round_num=2,
        prev_error_severity="import",
        curr_error_severity="import",  # Same error → escalate faster
        score_improving=False,
    )

    # Keep/discard decision
    if should_keep(prev_score=0.45, curr_score=0.47, epsilon=0.01):
        git_commit(...)  # or store best prompt variation
    else:
        git_revert(...)  # or discard variation
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


# ── Strategy Escalation ─────────────────────────────────────────────────
# Same 5-step pattern used by code-runner, adapted from classifier-lab's 10-step.


class Strategy(Enum):
    """Self-improvement strategy escalation levels.

    Progression: try direct fix first, then get more systematic, then
    try something completely different, then simplify to minimum viable,
    then escalate to human/stronger model.
    """
    direct_fix = "direct_fix"
    structured_analysis = "structured_analysis"
    different_approach = "different_approach"
    simplify = "simplify"
    escalate = "escalate"


# Ordered list for index-based escalation
STRATEGIES = [
    Strategy.direct_fix,
    Strategy.structured_analysis,
    Strategy.different_approach,
    Strategy.simplify,
    Strategy.escalate,
]


def get_strategy(
    round_num: int,
    prev_error_severity: str | None = None,
    curr_error_severity: str | None = None,
    score_improving: bool = False,
) -> Strategy:
    """Determine escalation strategy based on round and error trajectory.

    Args:
        round_num: Current round number (1-indexed)
        prev_error_severity: Error severity from previous round (if any)
        curr_error_severity: Error severity from current round
        score_improving: Whether score improved from previous round

    Returns:
        Strategy to use for next fix attempt.

    Strategy selection rules:
        1. Round 1 always uses direct_fix
        2. If same error severity repeats → escalate faster (skip a level)
        3. If score is improving → stay at current level (don't over-escalate)
        4. Otherwise → normal progression through levels
    """
    if round_num == 1:
        return Strategy.direct_fix

    # Same error type repeating → escalate faster (skip ahead)
    if prev_error_severity and curr_error_severity:
        if prev_error_severity == curr_error_severity:
            idx = min(round_num, len(STRATEGIES) - 1)
            return STRATEGIES[idx]

    # Score improving → stay at current level (working, don't change)
    if score_improving:
        idx = min(round_num - 1, len(STRATEGIES) - 1)
        return STRATEGIES[idx]

    # Normal progression
    idx = min(round_num - 1, len(STRATEGIES) - 1)
    return STRATEGIES[idx]


def strategy_instruction(strategy: Strategy) -> str:
    """Return human-readable instruction for each strategy.

    Use these in fix prompts to guide the LLM's approach.
    """
    instructions = {
        Strategy.direct_fix: (
            "Fix the specific error shown. Make the minimal change needed."
        ),
        Strategy.structured_analysis: (
            "Analyze the error systematically. Classify the root cause, "
            "identify affected components, then propose a targeted fix."
        ),
        Strategy.different_approach: (
            "The previous approach isn't working. Try a fundamentally different "
            "solution — different algorithm, different data structure, different API."
        ),
        Strategy.simplify: (
            "Simplify to minimum viable. Remove all optional complexity. "
            "Get the basic case working first, even if it means fewer features."
        ),
        Strategy.escalate: (
            "Write a detailed diagnosis of why this is failing. Document what "
            "you've tried, what the constraints are, and what help you need."
        ),
    }
    return instructions.get(strategy, "")


# ── Keep/Discard Decision ───────────────────────────────────────────────


def should_keep(
    prev_score: float,
    curr_score: float,
    epsilon: float = 0.01,
) -> bool:
    """Keep/discard decision with epsilon threshold to avoid churn.

    The epsilon threshold prevents committing tiny improvements that might
    just be noise. A 0.001 improvement isn't worth a git commit or storing
    a new prompt variation.

    Args:
        prev_score: Best score so far (0.0 to 1.0)
        curr_score: Score from current round (0.0 to 1.0)
        epsilon: Minimum improvement threshold (default 0.01 = 1%)

    Returns:
        True if curr_score > prev_score + epsilon (KEEP)
        False otherwise (DISCARD)
    """
    return curr_score > prev_score + epsilon


# ── Error Severity Classification ───────────────────────────────────────


class ErrorSeverity(Enum):
    """Error severity levels for classification.

    Ordered from most severe (syntax) to least (runtime).
    Syntax errors prevent execution entirely.
    Runtime errors only appear during execution.
    """
    syntax = "syntax"       # SyntaxError, IndentationError
    import_ = "import"      # ImportError, ModuleNotFoundError
    contract = "contract"   # TypeError, AttributeError, KeyError, NameError
    logic = "logic"         # AssertionError, ValueError, IndexError
    runtime = "runtime"     # RuntimeError, FileNotFoundError, TimeoutError
    unknown = "unknown"     # Unclassified errors


# Mapping from Python exception names to severity
ERROR_TYPE_TO_SEVERITY: dict[str, ErrorSeverity] = {
    "SyntaxError": ErrorSeverity.syntax,
    "IndentationError": ErrorSeverity.syntax,
    "ImportError": ErrorSeverity.import_,
    "ModuleNotFoundError": ErrorSeverity.import_,
    "TypeError": ErrorSeverity.contract,
    "AttributeError": ErrorSeverity.contract,
    "KeyError": ErrorSeverity.contract,
    "NameError": ErrorSeverity.contract,
    "AssertionError": ErrorSeverity.logic,
    "ValueError": ErrorSeverity.logic,
    "IndexError": ErrorSeverity.logic,
    "RuntimeError": ErrorSeverity.runtime,
    "FileNotFoundError": ErrorSeverity.runtime,
    "TimeoutError": ErrorSeverity.runtime,
    "PermissionError": ErrorSeverity.runtime,
    "ConnectionError": ErrorSeverity.runtime,
}

# Priority order for determining overall severity (most severe first)
SEVERITY_PRIORITY = [
    ErrorSeverity.syntax,
    ErrorSeverity.import_,
    ErrorSeverity.contract,
    ErrorSeverity.logic,
    ErrorSeverity.runtime,
    ErrorSeverity.unknown,
]


def classify_error_severity(error_types: list[str]) -> ErrorSeverity:
    """Classify overall error severity from individual error types.

    Args:
        error_types: List of Python exception names (e.g., ["TypeError", "KeyError"])

    Returns:
        Highest-priority severity found, or ErrorSeverity.unknown if none match.
    """
    if not error_types:
        return ErrorSeverity.unknown

    # Find highest-priority severity among the error types
    for severity in SEVERITY_PRIORITY:
        for error_type in error_types:
            if ERROR_TYPE_TO_SEVERITY.get(error_type) == severity:
                return severity

    return ErrorSeverity.unknown


def error_severity_from_text(text: str) -> ErrorSeverity:
    """Extract error severity from raw text (stderr, logs, etc.).

    Useful for prompt-lab where errors aren't Python exceptions but
    might mention error types in the text.

    Args:
        text: Raw text that might contain error type names

    Returns:
        Highest-priority severity found in the text.
    """
    for severity in SEVERITY_PRIORITY:
        for error_type, sev in ERROR_TYPE_TO_SEVERITY.items():
            if sev == severity and error_type in text:
                return severity
    return ErrorSeverity.unknown


# ── Round Entry Structure ───────────────────────────────────────────────


@dataclass
class RoundEntry:
    """Structured round entry for self-improvement loop logging.

    Common fields across code-runner, prompt-lab, classifier-lab.
    Domain-specific fields go in `metadata`.
    """
    # Identity
    round: int
    task_id: str

    # Scoring
    score: float
    prev_score: float
    delta: float  # score - prev_score

    # Decision
    status: str  # "keep" | "discard"
    strategy: Strategy

    # Errors
    error_count: int = 0
    error_severity: ErrorSeverity = ErrorSeverity.unknown
    errors_by_type: dict[str, int] = field(default_factory=dict)

    # Timing
    timestamp: float = field(default_factory=time.time)
    latency_ms: float = 0.0

    # Domain-specific metadata
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dict for JSON serialization."""
        return {
            "round": self.round,
            "task_id": self.task_id,
            "score": self.score,
            "prev_score": self.prev_score,
            "delta": self.delta,
            "status": self.status,
            "strategy": self.strategy.value,
            "error_count": self.error_count,
            "error_severity": self.error_severity.value,
            "errors_by_type": self.errors_by_type,
            "timestamp": self.timestamp,
            "latency_ms": self.latency_ms,
            **self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RoundEntry":
        """Create from dict (e.g., loaded from JSON)."""
        # Extract known fields
        known_fields = {
            "round", "task_id", "score", "prev_score", "delta",
            "status", "strategy", "error_count", "error_severity",
            "errors_by_type", "timestamp", "latency_ms",
        }
        metadata = {k: v for k, v in data.items() if k not in known_fields}

        return cls(
            round=data["round"],
            task_id=data["task_id"],
            score=data["score"],
            prev_score=data["prev_score"],
            delta=data["delta"],
            status=data["status"],
            strategy=Strategy(data["strategy"]),
            error_count=data.get("error_count", 0),
            error_severity=ErrorSeverity(data.get("error_severity", "unknown")),
            errors_by_type=data.get("errors_by_type", {}),
            timestamp=data.get("timestamp", 0.0),
            latency_ms=data.get("latency_ms", 0.0),
            metadata=metadata,
        )


# ── Correction Message Templates ────────────────────────────────────────
# Used by prompt-lab style self-correction loops.


def correction_message(
    error_description: str,
    valid_options: list[str] | None = None,
    examples: list[str] | None = None,
    strategy: Strategy = Strategy.direct_fix,
) -> str:
    """Build a correction message for the LLM based on current strategy.

    Args:
        error_description: What went wrong (e.g., "Invalid tags: X, Y")
        valid_options: List of valid options (if applicable)
        examples: Example correct outputs (for structured_analysis+)
        strategy: Current escalation strategy

    Returns:
        Formatted correction message to send back to the LLM.
    """
    parts = [f"Your response had an issue: {error_description}"]

    if strategy == Strategy.direct_fix:
        # Simple: just state the error and valid options
        if valid_options:
            parts.append(f"\nValid options are: {', '.join(valid_options)}")
        parts.append("\nPlease fix your response.")

    elif strategy == Strategy.structured_analysis:
        # Explain WHY it's wrong
        parts.append("\n\nLet me explain why this is invalid:")
        if valid_options:
            parts.append(f"- Only these options are allowed: {', '.join(valid_options)}")
        parts.append("- Your response must exactly match one of the valid options")
        parts.append("\nAnalyze the input again and provide a corrected response.")

    elif strategy == Strategy.different_approach:
        # Suggest trying something different
        parts.append("\n\nPrevious correction attempts haven't worked.")
        parts.append("Try a different interpretation of the input.")
        if examples:
            parts.append("\nHere are some example correct outputs:")
            for ex in examples[:3]:
                parts.append(f"  - {ex}")

    elif strategy == Strategy.simplify:
        # Simplify to most basic case
        parts.append("\n\nSimplify your approach:")
        if valid_options:
            parts.append(f"- Pick the MOST LIKELY option from: {', '.join(valid_options[:5])}")
        parts.append("- If unsure, choose the most general/common option")
        parts.append("- Don't overthink it — simpler is better here")

    elif strategy == Strategy.escalate:
        # Ask for explicit reasoning
        parts.append("\n\nI need to understand your reasoning:")
        parts.append("1. What do you think the input is asking for?")
        parts.append("2. Why did you choose your previous answer?")
        parts.append("3. What would you try differently?")
        if valid_options:
            parts.append(f"\nRemember, valid options are: {', '.join(valid_options)}")

    return "\n".join(parts)
