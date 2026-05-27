"""Structured validation errors for DAG chart/validate commands."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class DagChartError(Exception):
    """User-facing DAG problem; never expose raw tracebacks for these."""

    message: str
    code: str = "dag_invalid"
    hint: str = ""

    def __str__(self) -> str:
        return self.message

    def format_stderr(self) -> str:
        lines = [f"error [{self.code}]: {self.message}"]
        if self.hint:
            lines.append(f"hint: {self.hint}")
        return "\n".join(lines) + "\n"


@dataclass(frozen=True, slots=True)
class ValidationIssue:
    severity: str  # error | warning
    code: str
    message: str
    hint: str = ""

    def to_dict(self) -> dict[str, str]:
        out = {"severity": self.severity, "code": self.code, "message": self.message}
        if self.hint:
            out["hint"] = self.hint
        return out
