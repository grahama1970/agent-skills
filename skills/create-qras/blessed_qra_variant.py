"""Pydantic schema for child variants generated from a blessed QRA."""

from __future__ import annotations

import re
from collections import Counter
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


VariantCategory = Literal["layperson", "project_manager", "cybersecurity_expert", "reversal_curse"]
VariantReviewState = Literal["draft_variant"]
SkippedReason = Literal["parent_not_human_blessed", "no_safe_variants"]

ID_PATTERN = re.compile(
    r"\b(?:AC|AT|AU|CA|CM|CP|IA|IR|MA|MP|PE|PL|PM|PS|PT|RA|SA|SC|SI|SR|DE|ST|T|CAPEC|CWE|CVE)-?\d[\w.-]*\b"
)
CAPITALIZED_ENTITY_PATTERN = re.compile(r"\b[A-Z][A-Za-z0-9]*(?:[- ][A-Z][A-Za-z0-9]*)+\b")
CAPITALIZED_TOKEN_PREFIX_STOPWORDS = {
    "Can",
    "Does",
    "For",
    "How",
    "Is",
    "Should",
    "This",
    "What",
    "Which",
    "Why",
}


class RequestedVariantPlanItem(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    variant_category: VariantCategory
    count: int = Field(ge=0, le=20)


class RequestedVariantPlan(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    categories: list[RequestedVariantPlanItem] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_unique_categories(self) -> "RequestedVariantPlan":
        seen: set[str] = set()
        for item in self.categories:
            if item.variant_category in seen:
                raise ValueError(f"duplicate requested category: {item.variant_category}")
            seen.add(item.variant_category)
        return self


class BlessedQRAEvidenceCaseContext(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    case_id: str = Field(min_length=1)
    verdict_state: str | None = None
    answer_hash: str = Field(min_length=1)
    entities: list[str] = Field(default_factory=list)


class BlessedQRAParentContext(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    id: str = Field(min_length=1)
    question: str = Field(min_length=1)
    reasoning: str = Field(min_length=1)
    answer: str = Field(min_length=1)
    qra_type: str = Field(min_length=1)
    source_framework: str | None = None
    source_control_id: str | None = None
    target_framework: str | None = None
    target_control_id: str | None = None
    evidence_case: BlessedQRAEvidenceCaseContext
    review_status: str = Field(min_length=1)
    human_reviewed: bool


class BlessedQRAVariant(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    variant_category: VariantCategory
    question: str = Field(min_length=1)
    reasoning: str = Field(min_length=1)
    answer: str = Field(min_length=1)
    parent_qra_id: str = Field(min_length=1)
    canonical_answer_hash: str = Field(min_length=1)
    inherited_evidence_case_id: str = Field(min_length=1)
    review_state: VariantReviewState

    @field_validator("question", "reasoning")
    @classmethod
    def validate_editable_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("field must not be blank")
        if value != value.strip():
            raise ValueError("field must not include leading or trailing whitespace")
        return value

    @field_validator("answer", "parent_qra_id", "canonical_answer_hash", "inherited_evidence_case_id")
    @classmethod
    def validate_locked_text(cls, value: str) -> str:
        if not value:
            raise ValueError("locked field must not be blank")
        if value != value.strip():
            raise ValueError("locked field must not include leading or trailing whitespace")
        return value

    @field_validator("question")
    @classmethod
    def validate_question_surface(cls, value: str) -> str:
        if not value.endswith("?"):
            raise ValueError("question must end with '?'")
        return value

    @field_validator("reasoning")
    @classmethod
    def validate_reasoning_surface(cls, value: str) -> str:
        if len(re.findall(r"\S+", value)) > 35:
            raise ValueError("reasoning must be 35 words or fewer")
        if sentence_count(value) != 1:
            raise ValueError("reasoning must be exactly one sentence")
        return value


class BlessedQRAVariantResult(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    parent_qra_id: str
    canonical_answer_hash: str
    inherited_evidence_case_id: str
    variants: list[BlessedQRAVariant] = Field(default_factory=list)
    skipped_reason: SkippedReason | None = None

    @field_validator("parent_qra_id", "canonical_answer_hash", "inherited_evidence_case_id")
    @classmethod
    def validate_locked_text(cls, value: str) -> str:
        if value != value.strip():
            raise ValueError("locked field must not include leading or trailing whitespace")
        return value

    @model_validator(mode="after")
    def validate_result_consistency(self) -> "BlessedQRAVariantResult":
        if self.variants and self.skipped_reason is not None:
            raise ValueError("non-empty variants require skipped_reason=null")
        if not self.variants and self.skipped_reason is None:
            raise ValueError("empty variants require skipped_reason")

        seen_questions: set[str] = set()
        for idx, variant in enumerate(self.variants, start=1):
            if variant.parent_qra_id != self.parent_qra_id:
                raise ValueError(f"variant {idx} parent_qra_id differs from result parent_qra_id")
            if variant.canonical_answer_hash != self.canonical_answer_hash:
                raise ValueError(f"variant {idx} canonical_answer_hash differs from result canonical_answer_hash")
            if variant.inherited_evidence_case_id != self.inherited_evidence_case_id:
                raise ValueError(
                    f"variant {idx} inherited_evidence_case_id differs from result inherited_evidence_case_id"
                )
            normalized = normalize_question(variant.question)
            if normalized in seen_questions:
                raise ValueError(f"duplicate question after normalization at variant {idx}")
            seen_questions.add(normalized)
        return self

    @classmethod
    def validate_against_parent(
        cls,
        raw: dict[str, Any],
        canonical_qra: dict[str, Any] | BlessedQRAParentContext,
        requested_variant_plan: dict[str, Any] | RequestedVariantPlan | None = None,
    ) -> "BlessedQRAVariantResult":
        parent = (
            canonical_qra
            if isinstance(canonical_qra, BlessedQRAParentContext)
            else BlessedQRAParentContext.model_validate(canonical_qra)
        )
        result = cls.model_validate(raw)
        validate_top_level_locks(result, parent)

        parent_is_blessed = (
            parent.human_reviewed
            and parent.review_status in {"approved", "blessed"}
            and parent.qra_type == "canonical"
        )
        if not parent_is_blessed:
            if result.variants:
                raise ValueError("non-blessed parent must not produce variants")
            if result.skipped_reason != "parent_not_human_blessed":
                raise ValueError("non-blessed parent requires skipped_reason='parent_not_human_blessed'")
            return result

        if not result.variants and result.skipped_reason != "no_safe_variants":
            raise ValueError("blessed parent with no variants requires skipped_reason='no_safe_variants'")

        for idx, variant in enumerate(result.variants, start=1):
            validate_variant_locks(variant, parent, idx)
            validate_no_new_ids_or_entities(variant, parent, idx)

        if requested_variant_plan is not None and result.variants:
            plan = (
                requested_variant_plan
                if isinstance(requested_variant_plan, RequestedVariantPlan)
                else RequestedVariantPlan.model_validate(requested_variant_plan)
            )
            expected = Counter(
                {
                    item.variant_category: item.count
                    for item in plan.categories
                    if item.count > 0
                }
            )
            actual = Counter(variant.variant_category for variant in result.variants)
            if actual != expected:
                raise ValueError(
                    "variant category counts differ from requested plan: "
                    f"expected {dict(expected)}, got {dict(actual)}"
                )
        return result


def validate_blessed_qra_variant_result(
    payload: dict[str, Any],
    *,
    parent_qra_id: str,
    canonical_answer: str,
    canonical_answer_hash: str,
    inherited_evidence_case_id: str,
    review_status: str,
    human_reviewed: bool,
    requested_variant_plan: dict[str, Any] | RequestedVariantPlan | None = None,
    canonical_qra: dict[str, Any] | BlessedQRAParentContext | None = None,
) -> BlessedQRAVariantResult:
    """Validate a model response against trusted parent QRA context."""
    if canonical_qra is not None:
        return BlessedQRAVariantResult.validate_against_parent(payload, canonical_qra, requested_variant_plan)

    parent = BlessedQRAParentContext(
        id=parent_qra_id,
        question="legacy validation context",
        reasoning="legacy validation context.",
        answer=canonical_answer,
        qra_type="canonical",
        source_framework=None,
        source_control_id=None,
        target_framework=None,
        target_control_id=None,
        evidence_case=BlessedQRAEvidenceCaseContext(
            case_id=inherited_evidence_case_id,
            verdict_state=None,
            answer_hash=canonical_answer_hash,
            entities=[],
        ),
        review_status=review_status,
        human_reviewed=human_reviewed,
    )
    return BlessedQRAVariantResult.validate_against_parent(payload, parent, requested_variant_plan)


def validate_top_level_locks(result: BlessedQRAVariantResult, parent: BlessedQRAParentContext) -> None:
    if result.parent_qra_id != parent.id:
        raise ValueError("result parent_qra_id differs from parent QRA")
    if result.canonical_answer_hash != parent.evidence_case.answer_hash:
        raise ValueError("result canonical_answer_hash differs from parent evidence case")
    if result.inherited_evidence_case_id != parent.evidence_case.case_id:
        raise ValueError("result inherited_evidence_case_id differs from parent evidence case")


def validate_variant_locks(variant: BlessedQRAVariant, parent: BlessedQRAParentContext, idx: int) -> None:
    if variant.answer != parent.answer:
        raise ValueError(f"variant {idx} answer differs from canonical answer")
    if variant.parent_qra_id != parent.id:
        raise ValueError(f"variant {idx} parent_qra_id differs from parent QRA")
    if variant.canonical_answer_hash != parent.evidence_case.answer_hash:
        raise ValueError(f"variant {idx} canonical_answer_hash differs from parent evidence case")
    if variant.inherited_evidence_case_id != parent.evidence_case.case_id:
        raise ValueError(f"variant {idx} inherited_evidence_case_id differs from parent evidence case")


def validate_no_new_ids_or_entities(variant: BlessedQRAVariant, parent: BlessedQRAParentContext, idx: int) -> None:
    allowed_text = build_admissible_text(parent)
    for field_name, text in (("question", variant.question), ("reasoning", variant.reasoning)):
        for token in sorted(extract_guarded_tokens(text)):
            if not token_is_supported(token, allowed_text):
                raise ValueError(f"variant {idx} {field_name} introduces unsupported token: {token}")


def build_admissible_text(parent: BlessedQRAParentContext) -> str:
    fields = [
        parent.question,
        parent.reasoning,
        parent.answer,
        parent.source_framework,
        parent.source_control_id,
        parent.target_framework,
        parent.target_control_id,
        *parent.evidence_case.entities,
    ]
    return "\n".join(value for value in fields if value)


def extract_guarded_tokens(text: str) -> set[str]:
    tokens = set(ID_PATTERN.findall(text))
    tokens.update(CAPITALIZED_ENTITY_PATTERN.findall(text))
    return tokens


def token_is_supported(token: str, allowed_text: str) -> bool:
    if token in allowed_text:
        return True
    normalized_allowed = normalize_guarded_text(allowed_text)
    normalized_token = normalize_guarded_text(token)
    if normalized_token and normalized_token in normalized_allowed:
        return True
    parts = [part for part in re.split(r"\s+", token) if part]
    while parts and parts[0] in CAPITALIZED_TOKEN_PREFIX_STOPWORDS:
        parts = parts[1:]
    if len(parts) <= 1:
        return bool(parts) and token_is_supported(parts[0], allowed_text) if parts and parts[0] != token else False
    return bool(parts) and all(token_is_supported(part, allowed_text) for part in parts)


def normalize_guarded_text(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^A-Za-z0-9]+", " ", text)).strip()


def normalize_question(question: str) -> str:
    return re.sub(r"\s+", " ", question.strip().lower())


def sentence_count(value: str) -> int:
    chunks = [chunk for chunk in re.split(r"[.!?]+(?:\s+|$)", value.strip()) if chunk]
    return len(chunks)
