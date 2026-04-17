"""Data models for skills-ci scan results and reports.

Defines the core Violation and Report dataclasses used across all skills-ci
modules, plus the summarize_violations helper.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence


@dataclass
class Violation:
    rule: str
    severity: str
    skill: str
    path: str
    message: str
    fixable: bool = False
    applied: bool = False


@dataclass
class Report:
    root: str
    best_practices: List[str]
    mode: str
    timestamp: str
    violations: List[Violation]
    applied_fixes: List[str]
    skipped_fixes: List[str]
    worktree: Optional[str] = None

    def summary(self) -> Dict[str, int]:
        return summarize_violations(self.violations)


def summarize_violations(violations: Sequence[Violation]) -> Dict[str, int]:
    counts = {"error": 0, "warn": 0}
    for v in violations:
        counts[v.severity] = counts.get(v.severity, 0) + 1
    counts["total"] = len(violations)
    return counts
