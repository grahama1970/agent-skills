"""Shared models and constants for review-pdf.

Purpose:
- define small immutable structures and global constants used across modules.

Inputs:
- none (module-level declarations).

Outputs:
- dataclasses and constants for domain routing, regex checks, and report paths.

Failure modes:
- none beyond import/path resolution errors.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict

SKILL_DIR = Path(__file__).resolve().parent.parent
DEFAULT_REPORT_DIR = SKILL_DIR / "reports"
DEFAULT_EXTRACTED_RUNS_DIR = SKILL_DIR / "extracted_runs"
MEMORY_EVENTS_PATH = SKILL_DIR.parent / "memory" / ".artifacts" / "review_pdf_events.jsonl"

DOMAIN_HINTS = {
    "arxiv": "arxiv",
    "dtic": "defense_gov",
    "faa": "defense_gov",
    "nasa": "defense_gov",
    "nist": "defense_gov",
    "ietf": "standards",
    "industry": "industry",
    "adversarial": "adversarial",
    "edge_cases": "edge_cases",
}

MATH_TOKEN_RE = re.compile(
    r"(?:"
    r"[A-Za-z0-9\)\]]\s*(?:=|\+|-|\*|/|\^)\s*[A-Za-z0-9\(\[]|"
    r"\b(?:sin|cos|tan|log|ln|sqrt|sum|int|lim|min|max|argmax|argmin)\s*\(|"
    r"[∑∫∂√∆∇≈≠≤≥±×÷∞α-ωΑ-Ω]"
    r")"
)


@dataclass
class Issue:
    """Single detected quality issue."""

    code: str
    severity: str
    message: str
    root_cause: str
    recommendation: str

    def as_dict(self) -> Dict[str, str]:
        return {
            "code": self.code,
            "severity": self.severity,
            "message": self.message,
            "root_cause": self.root_cause,
            "recommendation": self.recommendation,
        }


@dataclass
class EscalationJob:
    """Escalation action to run or queue in companion skills."""

    skill: str
    command: str
    reason: str
    auto_executable: bool

    def as_dict(self) -> Dict[str, Any]:
        return {
            "skill": self.skill,
            "command": self.command,
            "reason": self.reason,
            "auto_executable": self.auto_executable,
        }
