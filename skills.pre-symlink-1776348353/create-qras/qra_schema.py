"""
Pydantic v2 schema for CWE independent QRA validation.

Two-layer validation:
1. Pydantic: shape and internal consistency
2. validate_grounding_against_record(): quotes exist in source sections
"""

from __future__ import annotations

import re
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator


MAX_PAIRS = 6


class SourceFramework(str, Enum):
    CWE = "CWE"


class PairType(str, Enum):
    implementation_guidance = "implementation_guidance"
    assessment_criteria = "assessment_criteria"
    scope_clarification = "scope_clarification"
    risk_context = "risk_context"


class ActionableFor(str, Enum):
    implementation = "implementation"
    audit = "audit"
    risk_analysis = "risk_analysis"
    vulnerability_assessment = "vulnerability_assessment"


class Confidence(str, Enum):
    high = "high"
    medium = "medium"


class EvidenceField(str, Enum):
    description = "description"
    extended_description = "extended_description"
    likelihood_of_exploit = "likelihood_of_exploit"
    common_consequences = "common_consequences"
    modes_of_introduction = "modes_of_introduction"
    potential_mitigations = "potential_mitigations"
    observed_examples = "observed_examples"


class AbstainReasonCode(str, Enum):
    insufficient_grounded_content = "insufficient_grounded_content"
    no_substantive_content = "no_substantive_content"
    only_generic_pairs_available = "only_generic_pairs_available"
    duplicate_or_redundant_candidates = "duplicate_or_redundant_candidates"


class EvidenceItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    field: EvidenceField
    quote: str = Field(min_length=1)

    @field_validator("quote")
    @classmethod
    def validate_quote(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("quote must not be blank")
        return value


class QRAPair(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pair_id: str = Field(min_length=1)
    pair_type: PairType
    actionable_for: list[ActionableFor] = Field(min_length=1)
    question: str = Field(min_length=1)
    reasoning: str = Field(min_length=1)
    answer: str = Field(min_length=1)
    confidence: Confidence
    evidence: list[EvidenceItem] = Field(min_length=1)

    @field_validator("pair_id", "question", "reasoning", "answer")
    @classmethod
    def validate_non_blank_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("field must not be blank")
        return value

    @field_validator("actionable_for")
    @classmethod
    def validate_actionable_for_unique(cls, value: list[ActionableFor]) -> list[ActionableFor]:
        if len(set(value)) != len(value):
            raise ValueError("actionable_for must not contain duplicates")
        return value


class QRAResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_framework: SourceFramework
    source_id: str = Field(min_length=1)
    pair_count: int = Field(ge=0, le=MAX_PAIRS)
    abstained: bool
    abstain_reason_code: AbstainReasonCode | None = None
    abstain_reason: str | None = None
    pairs: list[QRAPair] = Field(default_factory=list)

    @field_validator("source_id")
    @classmethod
    def validate_source_id(cls, value: str) -> str:
        value = value.strip()
        if not re.fullmatch(r"CWE-\d+", value):
            raise ValueError("source_id must match CWE-<number>")
        return value

    @model_validator(mode="after")
    def validate_result_consistency(self) -> "QRAResult":
        if self.pair_count != len(self.pairs):
            raise ValueError("pair_count must equal len(pairs)")

        if self.abstained:
            if self.pair_count != 0:
                raise ValueError("abstained result must have pair_count == 0")
            if self.pairs:
                raise ValueError("abstained result must have no pairs")
            if self.abstain_reason_code is None:
                raise ValueError("abstained result must include abstain_reason_code")
            if self.abstain_reason is None or not self.abstain_reason.strip():
                raise ValueError("abstained result must include abstain_reason")
        else:
            if self.pair_count < 1:
                raise ValueError("non-abstained result must contain at least one pair")
            if self.abstain_reason_code is not None:
                raise ValueError("non-abstained result must not include abstain_reason_code")
            if self.abstain_reason is not None:
                raise ValueError("non-abstained result must not include abstain_reason")

        seen_pair_ids: set[str] = set()
        seen_normalized_questions: set[str] = set()

        for idx, pair in enumerate(self.pairs, start=1):
            if pair.pair_id in seen_pair_ids:
                raise ValueError(f"duplicate pair_id: {pair.pair_id}")
            seen_pair_ids.add(pair.pair_id)

            if self.source_id not in pair.question:
                raise ValueError(
                    f"pair {idx} question must explicitly contain source_id {self.source_id}"
                )

            normalized_question = normalize_text(pair.question)
            if normalized_question in seen_normalized_questions:
                raise ValueError(f"duplicate or near-duplicate question at pair {idx}")
            seen_normalized_questions.add(normalized_question)

        return self


def normalize_text(text: str) -> str:
    """Normalize text for duplicate detection."""
    text = text.lower().strip()
    text = re.sub(r"\s+", " ", text)
    return text


def normalize_quote(text: str) -> str:
    """
    Light normalization for exact-span checks that should tolerate
    whitespace and quote character differences but not substantive wording changes.
    """
    text = text.strip()
    # Normalize all quote variants to straight quotes
    text = text.replace("\u2019", "'")  # curly apostrophe
    text = text.replace("\u2018", "'")  # left single quote
    text = text.replace("\u201c", '"')  # left double quote
    text = text.replace("\u201d", '"')  # right double quote
    text = text.replace("'", '"')       # single to double (LLM often swaps these)
    text = re.sub(r"\s+", " ", text)
    return text


def validate_grounding_against_record(
    result: QRAResult,
    record_sections: dict[str, str],
) -> list[str]:
    """
    Second-pass grounding validator.

    record_sections should look like:
    {
        "description": "...",
        "extended_description": "...",
        "likelihood_of_exploit": "...",
        "common_consequences": "...",
        "modes_of_introduction": "...",
        "potential_mitigations": "...",
        "observed_examples": "...",
    }

    Returns a list of errors. Empty list means grounding checks passed.
    """
    errors: list[str] = []

    for pair_index, pair in enumerate(result.pairs, start=1):
        for ev_index, ev in enumerate(pair.evidence, start=1):
            field_name = ev.field.value
            section_text = record_sections.get(field_name)
            if section_text is None:
                errors.append(
                    f"pair {pair_index} evidence {ev_index}: missing source section '{field_name}'"
                )
                continue

            normalized_section = normalize_quote(section_text)
            normalized_ev_quote = normalize_quote(ev.quote)

            if normalized_ev_quote not in normalized_section:
                errors.append(
                    f"pair {pair_index} evidence {ev_index}: quote not found in section '{field_name}'"
                )

    return errors


def validate_qra_payload(
    payload: dict,
    record_sections: dict[str, str],
) -> QRAResult:
    """
    Full validation:
    1. Pydantic schema + internal consistency
    2. Grounding quotes exist in the declared source sections
    """
    result = QRAResult.model_validate(payload)

    grounding_errors = validate_grounding_against_record(
        result=result,
        record_sections=record_sections,
    )
    if grounding_errors:
        raise ValueError("Grounding validation failed: " + "; ".join(grounding_errors))

    return result
