#!/usr/bin/env python3
"""
Quality metrics dataclasses for persona assessment.

Provides the PersonaQualityScore dataclass used by diagnose, validate,
improve, and audit modules.
"""

from dataclasses import dataclass, field


@dataclass
class PersonaQualityScore:
    """Quality assessment for a persona."""

    name: str
    scope: str

    # Scores (0.0 - 1.0)
    completeness: float = 0.0  # How much data do we have?
    connectivity: float = 0.0  # Colleague/relationship edges
    accuracy: float = 0.0      # Test Q&A accuracy (if tested)
    freshness: float = 0.0     # How recent is the data?

    # Diagnostic details
    sources_count: int = 0
    qra_count: int = 0
    colleague_count: int = 0
    bridge_count: int = 0
    days_since_update: int = 0

    # Gaps identified
    gaps: list[str] = field(default_factory=list)

    # Test results (if validated)
    tests_passed: int = 0
    tests_failed: int = 0
    test_details: list[dict] = field(default_factory=list)

    @property
    def overall_score(self) -> float:
        """Weighted overall quality score."""
        # Weight: completeness 40%, connectivity 20%, accuracy 30%, freshness 10%
        return (
            self.completeness * 0.4 +
            self.connectivity * 0.2 +
            self.accuracy * 0.3 +
            self.freshness * 0.1
        )

    @property
    def grade(self) -> str:
        """Letter grade based on overall score."""
        score = self.overall_score
        if score >= 0.9:
            return "A"
        elif score >= 0.8:
            return "B"
        elif score >= 0.7:
            return "C"
        elif score >= 0.6:
            return "D"
        else:
            return "F"

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "scope": self.scope,
            "scores": {
                "completeness": round(self.completeness, 2),
                "connectivity": round(self.connectivity, 2),
                "accuracy": round(self.accuracy, 2),
                "freshness": round(self.freshness, 2),
                "overall": round(self.overall_score, 2),
            },
            "grade": self.grade,
            "details": {
                "sources_count": self.sources_count,
                "qra_count": self.qra_count,
                "colleague_count": self.colleague_count,
                "bridge_count": self.bridge_count,
                "days_since_update": self.days_since_update,
            },
            "gaps": self.gaps,
            "tests": {
                "passed": self.tests_passed,
                "failed": self.tests_failed,
                "details": self.test_details,
            },
        }
