"""review-sparta constants and data classes.

Brandon Bailey persona constants, grading scale, space-relevant CWE lists,
SPACE_TERMS, DimensionResult/AssessmentResult dataclasses, and helper functions.
"""

import json
import random
import re
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional

# ─────────────────────────────────────────────────────────────────────────────
# Brandon Bailey Persona
# ─────────────────────────────────────────────────────────────────────────────

BRANDON_BAILEY_INTRO = """
[bold cyan]Brandon Bailey[/bold cyan]
[dim]Principal Director, Cyber Assessments — The Aerospace Corporation[/dim]

"I created SPARTA to give the space community a common language for discussing
threats. Any derivative work must meet the same standard: every claim must trace
back to source material, every CWE must apply to the actual technology, and every
countermeasure must address a real attack vector.

I'm not here to validate your work — I'm here to find the gaps before an
adversary does."
"""

GRADING_SCALE = {
    "A+": {"max_generic": 0.20, "min_fidelity": 1.00, "min_grounding": 0.90, "label": "EXCELLENT"},
    "A":  {"max_generic": 0.30, "min_fidelity": 0.95, "min_grounding": 0.85, "label": "GOOD"},
    "B":  {"max_generic": 0.50, "min_fidelity": 0.90, "min_grounding": 0.80, "label": "ACCEPTABLE"},
    "C":  {"max_generic": 0.70, "min_fidelity": 0.80, "min_grounding": 0.70, "label": "NEEDS WORK"},
    "F":  {"max_generic": 1.00, "min_fidelity": 0.00, "min_grounding": 0.00, "label": "FAIL"},
}

# Space-relevant CWE categories
SPACE_CWES = {
    "memory_safety": ["CWE-120", "CWE-787", "CWE-125", "CWE-416", "CWE-476", "CWE-190"],
    "cryptography": ["CWE-311", "CWE-327", "CWE-330"],
    "space_systems": ["CWE-1281", "CWE-1282", "CWE-1283", "CWE-345", "CWE-353"],
    "resource_mgmt": ["CWE-400", "CWE-401", "CWE-770"],
    "auth": ["CWE-287", "CWE-306", "CWE-798", "CWE-522"],
    "input_validation": ["CWE-20"],
}

# CWEs that are typically NOT space-relevant
NON_SPACE_CWES = [
    "CWE-79",   # XSS - web specific
    "CWE-89",   # SQL Injection - database specific
    "CWE-918",  # SSRF - web specific
    "CWE-352",  # CSRF - web specific
    "CWE-434",  # Unrestricted Upload - web specific
]

SPACE_TERMS = [
    "satellite", "spacecraft", "orbital", "telemetry", "ground station",
    "uplink", "downlink", "command and control", "c2", "ephemeris",
    "payload", "bus", "solar array", "attitude control", "propulsion",
    "thermal", "radiation", "space segment", "ground segment", "link budget",
    "rf", "radio frequency", "antenna", "transponder", "modulation",
    "encryption", "authentication", "firmware", "embedded", "flight software",
    "mission", "launch", "orbit", "geosynchronous", "leo", "meo", "gso",
    "space vehicle", "sv", "constellation", "deep space", "communication",
]


# ─────────────────────────────────────────────────────────────────────────────
# Data Classes
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class DimensionResult:
    """Result for a single dimension check."""
    name: str
    weight: float
    score: float
    checks: dict = field(default_factory=dict)
    issues: list = field(default_factory=list)
    suggestions: list = field(default_factory=list)

    @property
    def weighted_score(self) -> float:
        return self.score * self.weight

    @property
    def passed(self) -> bool:
        return self.score >= 0.7


@dataclass
class AssessmentResult:
    """Full Brandon Bailey assessment result."""
    run_id: str
    timestamp: str
    dimensions: dict = field(default_factory=dict)
    overall_score: float = 0.0
    grade: str = "F"
    verdict: str = "FAIL"
    critical_issues: int = 0
    warnings: int = 0
    brandon_commentary: str = ""

    def calculate_overall(self):
        """Calculate overall weighted score and grade."""
        if not self.dimensions:
            return

        self.overall_score = sum(d.weighted_score for d in self.dimensions.values())

        for d in self.dimensions.values():
            for issue in d.issues:
                if "CRITICAL" in issue.upper():
                    self.critical_issues += 1
                else:
                    self.warnings += 1

        self.grade = "F"
        self.verdict = "FAIL"
        for grade, criteria in GRADING_SCALE.items():
            if self.overall_score >= criteria["min_grounding"]:
                self.grade = grade
                self.verdict = criteria["label"]
                break


# ─────────────────────────────────────────────────────────────────────────────
# Helper Functions
# ─────────────────────────────────────────────────────────────────────────────

def has_verbatim_phrase(answer: str, source: str, min_len: int = 20) -> bool:
    """Check if answer contains a verbatim phrase from source."""
    if not answer or not source:
        return False

    answer_lower = answer.lower()
    source_lower = source.lower()

    for i in range(len(answer_lower) - min_len + 1):
        phrase = answer_lower[i:i + min_len]
        if phrase in source_lower:
            return True
    return False


def get_db_connection(run_id: str):
    """Get DuckDB connection for a run."""
    import duckdb

    paths = [
        Path.home() / "workspace" / "experiments" / "sparta" / "data" / "runs" / run_id / "sparta.duckdb",
        Path(f"data/runs/{run_id}/sparta.duckdb"),
        Path(f"../sparta/data/runs/{run_id}/sparta.duckdb"),
    ]

    for db_path in paths:
        if db_path.exists():
            return duckdb.connect(str(db_path), read_only=True)

    raise FileNotFoundError(f"Database not found for run: {run_id}")


def generate_brandon_commentary(result: AssessmentResult) -> str:
    """Generate Brandon Bailey's commentary based on results."""
    commentary_parts = []

    if result.grade in ["A+", "A"]:
        commentary_parts.append("This is solid work.")
    elif result.grade == "B":
        commentary_parts.append("The fundamentals are there, but I have concerns.")
    elif result.grade == "C":
        commentary_parts.append("This needs significant improvement before I'd present it to stakeholders.")
    else:
        commentary_parts.append("I cannot approve this in its current state.")

    for dim_name, dim in result.dimensions.items():
        if dim.score < 0.7:
            if dim_name == "qra_quality":
                commentary_parts.append(
                    "The QRA quality concerns me most - answers must trace back to source material."
                )
            elif dim_name == "cwe_relevance":
                commentary_parts.append(
                    "SQL injection on a satellite? Please review the CWE mappings for space relevance."
                )
            elif dim_name == "source_fidelity":
                commentary_parts.append(
                    "The database doesn't match my original SPARTA data. This is a critical flaw."
                )

    if result.critical_issues > 0:
        commentary_parts.append(
            f"Fix the {result.critical_issues} critical issues before proceeding."
        )

    return " ".join(commentary_parts)
