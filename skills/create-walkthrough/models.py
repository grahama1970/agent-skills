"""Shared data models for the walkthrough claim verification engine."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class Verdict(str, Enum):
    VERIFIED = "VERIFIED"
    MISMATCH = "MISMATCH"
    UNVERIFIED = "UNVERIFIED"
    SKIPPED = "SKIPPED"


@dataclass
class Claim:
    """A factual claim extracted from a walkthrough."""

    claim_type: str  # file_path, function, package, env_var, port, config, line_count
    raw_text: str  # The original text containing the claim
    value: str  # The specific claimed value
    line_number: int  # Line in the walkthrough
    context: str = ""  # Surrounding text for disambiguation

    # Verification results (populated after check)
    verdict: Optional[Verdict] = None
    detail: str = ""
    actual_value: Optional[str] = None


@dataclass
class VerificationReport:
    """Results of verifying all claims in a walkthrough."""

    file: str
    claims: list[Claim] = field(default_factory=list)

    @property
    def verified(self) -> int:
        return sum(1 for c in self.claims if c.verdict == Verdict.VERIFIED)

    @property
    def mismatched(self) -> int:
        return sum(1 for c in self.claims if c.verdict == Verdict.MISMATCH)

    @property
    def unverified(self) -> int:
        return sum(1 for c in self.claims if c.verdict == Verdict.UNVERIFIED)

    @property
    def skipped(self) -> int:
        return sum(1 for c in self.claims if c.verdict == Verdict.SKIPPED)

    def to_dict(self) -> dict:
        return {
            "file": self.file,
            "total_claims": len(self.claims),
            "verified": self.verified,
            "mismatched": self.mismatched,
            "unverified": self.unverified,
            "skipped": self.skipped,
            "claims": [
                {
                    "type": c.claim_type,
                    "value": c.value,
                    "line": c.line_number,
                    "verdict": c.verdict.value if c.verdict else None,
                    "detail": c.detail,
                    "actual": c.actual_value,
                }
                for c in self.claims
            ],
        }
