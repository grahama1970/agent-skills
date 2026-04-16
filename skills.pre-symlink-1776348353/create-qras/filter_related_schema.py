"""
Pydantic v2 schema for Filter Related QRAs output validation.

Enforces:
1. Structure and field presence
2. Consistency between relevant_keys and judgments
3. Inclusion logic: all core gates must pass for include=true
4. No MCQ/quiz-style drift - strict JSON schema
"""

from __future__ import annotations

from typing import List
from pydantic import BaseModel, ConfigDict, Field, model_validator


class Checks(BaseModel):
    """Five relevance checks for a candidate QRA."""
    model_config = ConfigDict(extra="forbid")

    addresses_same_concern: bool
    complements_not_duplicates: bool
    aids_user_query: bool
    shares_technique_meaningfully: bool
    evidence_chain_overlap: bool  # Ranking signal only, NOT a gate


class Judgment(BaseModel):
    """Judgment for a single candidate QRA."""
    model_config = ConfigDict(extra="forbid")

    key: str = Field(..., min_length=1, description="Candidate QRA _key")
    include: bool = Field(..., description="Whether to include this candidate")
    shared_techniques: List[str] = Field(
        default_factory=list,
        description="SPARTA techniques shared with primary QRA"
    )
    checks: Checks
    reason: str = Field(
        ...,
        min_length=8,
        max_length=200,
        description="8-20 word explanation of inclusion/exclusion"
    )

    @model_validator(mode="after")
    def validate_include_logic(self) -> "Judgment":
        """Enforce: include=true requires all core gates to pass."""
        core_gates = [
            self.checks.addresses_same_concern,
            self.checks.complements_not_duplicates,
            self.checks.aids_user_query,
            self.checks.shares_technique_meaningfully,
        ]

        if self.include and not all(core_gates):
            failing_gates = []
            if not self.checks.addresses_same_concern:
                failing_gates.append("addresses_same_concern")
            if not self.checks.complements_not_duplicates:
                failing_gates.append("complements_not_duplicates")
            if not self.checks.aids_user_query:
                failing_gates.append("aids_user_query")
            if not self.checks.shares_technique_meaningfully:
                failing_gates.append("shares_technique_meaningfully")
            raise ValueError(
                f"include=true requires all core gates to pass. "
                f"Failing gates: {failing_gates}"
            )

        if self.include and not self.shared_techniques:
            raise ValueError("include=true requires at least one shared technique")

        return self


class FilterRelatedQRAsOutput(BaseModel):
    """Output schema for Filter Related QRAs judge."""
    model_config = ConfigDict(extra="forbid")

    relevant_keys: List[str] = Field(
        default_factory=list,
        description="Keys of included candidates, sorted best-to-worst"
    )
    excluded_count: int = Field(
        ...,
        ge=0,
        description="Number of excluded candidates"
    )
    judgments: List[Judgment] = Field(
        default_factory=list,
        description="One judgment per candidate, in input order"
    )

    @model_validator(mode="after")
    def validate_consistency(self) -> "FilterRelatedQRAsOutput":
        """Enforce output consistency rules."""
        # Check for duplicate keys in judgments
        judgment_keys = [j.key for j in self.judgments]
        if len(judgment_keys) != len(set(judgment_keys)):
            raise ValueError("judgments contain duplicate keys")

        # relevant_keys must match included judgment keys
        included_keys = [j.key for j in self.judgments if j.include]
        if set(self.relevant_keys) != set(included_keys):
            raise ValueError(
                f"relevant_keys must contain exactly the keys where include=true. "
                f"Expected {included_keys}, got {self.relevant_keys}"
            )

        # excluded_count must match
        computed_excluded = len(self.judgments) - len(included_keys)
        if self.excluded_count != computed_excluded:
            raise ValueError(
                f"excluded_count must equal {computed_excluded}, got {self.excluded_count}"
            )

        return self


def parse_filter_output(raw_json: str) -> FilterRelatedQRAsOutput:
    """Parse and validate filter output from LLM response."""
    import json
    data = json.loads(raw_json)
    return FilterRelatedQRAsOutput.model_validate(data)


def get_json_schema() -> dict:
    """Get JSON Schema for response_format parameter."""
    return FilterRelatedQRAsOutput.model_json_schema()
