"""Deck-context intake and approve-outline-before-slides workflow (#1277).

Two-stage planning: sources + DECK_CONTEXT -> claim analysis -> a versioned
narrative outline (module ids, purpose, CANDIDATE ASSERTIONS drawn verbatim
from ledger claims — never invented prose, unknowns become typed QUESTIONS)
-> explicit human approval record -> only then slide-intent materialization
(#1278). No deck manifest materializes until the outline carries an approval
record; approval is invalidated by any outline content change (hash-bound).
Failure modes are typed codes, not prose: MISSING_CONTEXT_FIELD,
IMPOSSIBLE_SLIDE_RANGE, POLICY_CONFLICT, UNANSWERED_REQUIRED_QUESTION,
UNAPPROVED_OUTLINE, STALE_MODULE.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator

from .design_system import KNOWN_MODULES, Audience, DeckProfile
from .models import ClaimLedger, ClaimStatus, StrictModel, Visibility


class PlanningCode(str):
    MISSING_CONTEXT_FIELD = "MISSING_CONTEXT_FIELD"
    IMPOSSIBLE_SLIDE_RANGE = "IMPOSSIBLE_SLIDE_RANGE"
    POLICY_CONFLICT = "POLICY_CONFLICT"
    UNANSWERED_REQUIRED_QUESTION = "UNANSWERED_REQUIRED_QUESTION"
    UNAPPROVED_OUTLINE = "UNAPPROVED_OUTLINE"
    STALE_MODULE = "STALE_MODULE"
    NO_COMPATIBLE_RECIPE = "NO_COMPATIBLE_RECIPE"


class DeckContext(StrictModel):
    schema_: Literal["pitchdeck.deck_context.v1"] = Field(default="pitchdeck.deck_context.v1", alias="schema")
    objective: str = Field(min_length=1)
    desired_action: str = Field(min_length=1, description="What the audience should DO afterwards.")
    audience: Audience
    audience_roles: list[str] = Field(min_length=1)
    prior_knowledge: Literal["none", "domain", "expert"] = "domain"
    duration_minutes: int = Field(ge=3, le=120)
    target_slide_range: tuple[int, int] = (6, 20)
    primary_ask: str = Field(min_length=1)
    required_modules: list[str] = Field(default_factory=list)
    non_goals: list[str] = Field(default_factory=list)
    forbidden_claims: list[str] = Field(default_factory=list)
    target_outputs: list[Literal["pptx", "html", "react"]] = Field(default_factory=lambda: ["pptx"])
    design_system_id: str = Field(min_length=1)
    deck_profile_id: str = Field(min_length=1)
    style_reference_ids: list[str] = Field(default_factory=list)
    visibility: Visibility = Visibility.PUBLIC
    delivery: Literal["presenter_led", "standalone_reading"] = "presenter_led"

    @model_validator(mode="after")
    def coherent(self) -> "DeckContext":
        low, high = self.target_slide_range
        if low < 1 or high < low:
            raise ValueError(f"{PlanningCode.IMPOSSIBLE_SLIDE_RANGE}: target_slide_range {self.target_slide_range}")
        if high > self.duration_minutes * 4:
            raise ValueError(
                f"{PlanningCode.IMPOSSIBLE_SLIDE_RANGE}: {high} slides cannot fit {self.duration_minutes} minutes"
            )
        unknown = [m for m in self.required_modules if m not in KNOWN_MODULES]
        if unknown:
            raise ValueError(f"{PlanningCode.MISSING_CONTEXT_FIELD}: unknown required modules {unknown}")
        return self


class PlanningQuestion(StrictModel):
    code: str = Field(min_length=1)
    module: str | None = None
    question: str = Field(min_length=1)
    required: bool = True
    answer: str | None = None


class AssertionRendering(StrictModel):
    """A tightened headline RENDERING of a bound claim (#1279 flow).

    Proposals start as candidates — the agent may propose, mechanical
    verification classifies the transform, and only a HUMAN approval promotes
    one into a title. truncation/inflection are auto-verifiable (word-boundary
    substring, case-sensitive/insensitive); generalization can never
    self-verify and stays candidate until a human approves the meaning."""

    claim_id: str = Field(min_length=1)
    text: str = Field(min_length=1, max_length=120)
    transform_class: Literal["truncation", "inflection", "generalization"]
    status: Literal["candidate", "approved"] = "candidate"
    approved_by: str | None = None

    @model_validator(mode="after")
    def approval_provenance(self) -> "AssertionRendering":
        if self.status == "approved" and not self.approved_by:
            raise ValueError("approved renderings require approved_by provenance")
        return self


def verify_rendering(rendering: AssertionRendering, claim_text: str) -> AssertionRendering:
    """Mechanically classify/verify a rendering against its claim text.

    Returns the rendering with a POSSIBLY CORRECTED transform_class; raises if
    a truncation/inflection claim is false (text not a word-boundary excerpt)."""
    import re as _re

    def _word_boundary_excerpt(needle: str, haystack: str) -> bool:
        pattern = r"(?<![A-Za-z0-9])" + _re.escape(needle.strip().rstrip(".")) + r"(?![A-Za-z0-9])"
        return _re.search(pattern, haystack) is not None

    text = rendering.text.strip()
    if _word_boundary_excerpt(text, claim_text):
        cls = "truncation"
    elif _word_boundary_excerpt(text.lower(), claim_text.lower()):
        cls = "inflection"
    else:
        cls = "generalization"
    if rendering.transform_class in {"truncation", "inflection"} and cls == "generalization":
        raise ValueError(
            f"rendering '{text[:40]}' claims {rendering.transform_class} but is not a word-boundary excerpt of the claim"
        )
    return rendering.model_copy(update={"transform_class": cls})


def propose_truncations(claim_text: str, *, max_words: int = 10) -> list[str]:
    """Deterministic clause-boundary truncation candidates within the word cap."""
    import re as _re

    clauses = [c.strip() for c in _re.split(r"[,;:—]| - ", claim_text) if c.strip()]
    candidates: list[str] = []
    for clause in clauses:
        words = clause.split()
        if 2 <= len(words) <= max_words:
            candidates.append(clause.rstrip("."))
    lead = claim_text.split()
    for n in (max_words, max_words - 2, 6):
        if len(lead) > n:
            head = " ".join(lead[:n]).rstrip(",;:—-")
            if head not in candidates:
                candidates.append(head)
    return candidates[:5]


class OutlineModule(StrictModel):
    module: str = Field(min_length=1)
    purpose: str = Field(min_length=1)
    candidate_claim_ids: list[str] = Field(default_factory=list)
    candidate_assertions: list[str] = Field(
        default_factory=list, description="Verbatim ledger claim texts — assertion candidates, never invented prose."
    )
    expected_slides: int = Field(ge=1, le=6, default=1)
    rationale: str = Field(min_length=1)
    stale: bool = False
    omitted: bool = False
    visual_thesis: str | None = Field(default=None, description="What the visual argues, or 'none: <reason>'.")
    diagram: "object | None" = Field(default=None, description="Approved DiagramGraph payload (dict); consumed verbatim by the materializer.")
    visual_asset_id: str | None = None
    renderings: list[AssertionRendering] = Field(default_factory=list)

    @model_validator(mode="after")
    def module_known(self) -> "OutlineModule":
        if self.module not in KNOWN_MODULES:
            raise ValueError(f"unknown narrative module '{self.module}'")
        return self


class OutlineApproval(StrictModel):
    approved_by: str = Field(min_length=1)
    approved_at: str = Field(min_length=1)
    content_sha256: str = Field(min_length=64, max_length=64)


class NarrativeOutline(StrictModel):
    schema_: Literal["pitchdeck.narrative_outline.v1"] = Field(default="pitchdeck.narrative_outline.v1", alias="schema")
    version: int = Field(ge=1)
    context_sha256: str = Field(min_length=64, max_length=64)
    audience: Audience
    modules: list[OutlineModule] = Field(min_length=1)
    questions: list[PlanningQuestion] = Field(default_factory=list)
    approval: OutlineApproval | None = None

    def content_hash(self) -> str:
        payload = self.model_dump(mode="json", by_alias=True, exclude={"approval"})
        return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()

    def assert_approved(self) -> None:
        if self.approval is None:
            raise ValueError(f"{PlanningCode.UNAPPROVED_OUTLINE}: outline has no approval record")
        if self.approval.content_sha256 != self.content_hash():
            raise ValueError(
                f"{PlanningCode.UNAPPROVED_OUTLINE}: outline changed after approval (hash mismatch) — re-approve"
            )
        unanswered = [q.question for q in self.questions if q.required and not q.answer]
        if unanswered:
            raise ValueError(f"{PlanningCode.UNANSWERED_REQUIRED_QUESTION}: {unanswered}")


_MODULE_KEYWORDS: dict[str, tuple[str, ...]] = {
    "thesis": ("scattered", "one evidence thread", "turns scattered"),
    "problem_solution": ("cannot", "without e", "not support", "insufficient", "relevan"),
    "value_prop": ("helps teams", "value", "delivers", "ask why"),
    "architecture": ("framework guidance", "navigate", "governed evidence", "authorized people"),
    "proof": ("prepared-host", "global posture", "threat matrix", "working surfaces", "investigation experience"),
    "roadmap": ("gates", "corpus review", "convergence", "remaining"),
    "ask": ("design-partner", "collaboration", "walkthrough"),
}


def draft_outline(context: DeckContext, ledger: ClaimLedger, profile: DeckProfile) -> NarrativeOutline:
    """Deterministic outline draft: claims are ROUTED to modules by keyword
    evidence (verbatim assertion candidates); gaps become questions."""
    if context.visibility is Visibility.PUBLIC and profile.audience is not context.audience:
        raise ValueError(
            f"{PlanningCode.POLICY_CONFLICT}: context audience '{context.audience.value}' vs profile '{profile.audience.value}'"
        )
    usable = [
        c for c in ledger.claims
        if c.status is not ClaimStatus.REJECTED
        and (context.visibility is not Visibility.PUBLIC or c.visibility is Visibility.PUBLIC)
        and c.id not in set(context.forbidden_claims)
    ]
    ordered_modules = [m for m in profile.module_order if not any(x == m for x in ("boneyard", "discussion", "toc"))]
    for required in context.required_modules:
        if required not in ordered_modules:
            ordered_modules.append(required)
    modules: list[OutlineModule] = []
    questions: list[PlanningQuestion] = []
    for module in ordered_modules:
        keywords = _MODULE_KEYWORDS.get(module, ())
        matched = [c for c in usable if any(k in c.text.lower() for k in keywords)] if keywords else []
        if module == "cover":
            modules.append(OutlineModule(module="cover", purpose="Brand the deck", rationale="always present", expected_slides=1))
            continue
        if not matched and module in {m.module for m in profile.modules if m.required}:
            questions.append(PlanningQuestion(
                code="MISSING_EVIDENCE",
                module=module,
                question=f"No ledger claims route to required module '{module}' — supply evidence or omit the module.",
            ))
            continue
        if not matched:
            continue
        modules.append(OutlineModule(
            module=module,
            purpose=f"Argue the {module.replace('_', ' ')} from bound evidence",
            candidate_claim_ids=[c.id for c in matched[:4]],
            candidate_assertions=[c.text for c in matched[:4]],
            expected_slides=1,
            rationale=f"{len(matched)} claims route here by keyword evidence",
        ))
    low, high = context.target_slide_range
    expected = sum(m.expected_slides for m in modules)
    if expected < low:
        questions.append(PlanningQuestion(
            code="THIN_OUTLINE",
            question=f"Outline yields {expected} slides but the context asks for at least {low} — add modules or evidence, or lower the range.",
            required=False,
        ))
    context_hash = hashlib.sha256(context.model_dump_json(by_alias=True).encode()).hexdigest()
    return NarrativeOutline(version=1, context_sha256=context_hash, audience=context.audience, modules=modules, questions=questions)


def approve_outline(outline: NarrativeOutline, *, approved_by: str, approved_at: str) -> NarrativeOutline:
    return outline.model_copy(update={"approval": OutlineApproval(
        approved_by=approved_by, approved_at=approved_at, content_sha256=outline.content_hash()
    )})


def mark_stale_modules(outline: NarrativeOutline, changed_claim_ids: set[str]) -> NarrativeOutline:
    """A source change stales only the modules whose claims it touches (#1277 proof 5)."""
    modules = [
        m.model_copy(update={"stale": bool(set(m.candidate_claim_ids) & changed_claim_ids)})
        for m in outline.modules
    ]
    return outline.model_copy(update={"modules": modules})
