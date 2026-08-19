"""Evidence-bound role-rubric coverage and follow-up suggestions (#1452).

The rubric names what a role actually requires; coverage states are earned by
exact transcript evidence, never by model prose or retrieval relevance. No
aggregate score, ranking, or hire/decline output exists anywhere in this
module -- ``scoring_disabled`` is pinned true at the schema level.

Judgment (which events cover which criterion) is authored upstream by the
model lane; this module is the deterministic floor: it verifies bindings
against the actual transcript, fences revisions, caps suggestions, invalidates
cache on rubric edits, and rejects prohibited criteria outright.
"""

from __future__ import annotations

import hashlib
import json
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

# Criteria over these dimensions are illegitimate for hiring assistance and
# fail rubric validation outright (#1452 non-goals).
PROHIBITED_CRITERION_TERMS = (
    "face", "facial", "gaze", "eye contact", "accent", "emotion", "personality",
    "confidence", "confident", "nervous", "attractive", "appearance", "age",
    "gender", "race", "ethnicity", "religion", "disability", "pregnancy",
    "voice quality", "tone of voice",
)


class RubricCriterion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    criterion_id: str = Field(min_length=1, max_length=100)
    label: str = Field(min_length=1, max_length=300)
    job_relevance: str = Field(min_length=1, max_length=1_000)
    evidence_required: list[str] = Field(min_length=1, max_length=32)
    prohibited_inferences: list[str] = Field(default_factory=list, max_length=32)

    @model_validator(mode="after")
    def reject_prohibited(self) -> "RubricCriterion":
        import re

        blob = f"{self.criterion_id} {self.label} {self.job_relevance}".lower()
        # Word-boundary matching: "pagination" must not trip on "age".
        hits = [
            term for term in PROHIBITED_CRITERION_TERMS
            if re.search(rf"\b{re.escape(term)}\b", blob)
        ]
        if hits:
            raise ValueError(f"prohibited criterion dimension(s): {hits}")
        return self


class RoleRubric(BaseModel):
    """live_evidence.role_rubric.v1 -- versioned, digest-bound, score-free."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True, serialize_by_alias=True)

    schema_id: Literal["live_evidence.role_rubric.v1"] = Field(
        default="live_evidence.role_rubric.v1",
        validation_alias="schema",
        serialization_alias="schema",
    )
    rubric_id: str = Field(min_length=1, max_length=100)
    role_name: str = Field(min_length=1, max_length=200)
    version: int = Field(ge=1)
    criteria: list[RubricCriterion] = Field(min_length=1, max_length=64)
    question_bank: list[str] = Field(default_factory=list, max_length=256)
    scoring_disabled: Literal[True] = True

    def rubric_digest(self) -> str:
        payload = self.model_dump(mode="json", by_alias=True)
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()


class CoverageState(StrEnum):
    COVERED = "covered"
    PARTIALLY_COVERED = "partially_covered"
    UNTESTED = "untested"
    CONTRADICTED = "contradicted"
    NOT_APPLICABLE = "not_applicable"


# States that assert something about the answer and therefore need evidence.
_EVIDENCE_BEARING = {
    CoverageState.COVERED,
    CoverageState.PARTIALLY_COVERED,
    CoverageState.CONTRADICTED,
}


class CriterionCoverage(BaseModel):
    """One criterion's state for one exact question/answer revision."""

    model_config = ConfigDict(extra="forbid")

    criterion_id: str = Field(min_length=1, max_length=100)
    state: CoverageState
    evidence_event_ids: list[str] = Field(default_factory=list, max_length=64)
    artifact_refs: list[str] = Field(default_factory=list, max_length=16)
    rationale: str = Field(default="", max_length=2_000)
    question_id: str = Field(min_length=8, max_length=64)
    question_revision: int = Field(ge=0)
    rubric_digest: str = Field(min_length=64, max_length=64)

    @model_validator(mode="after")
    def evidence_required_for_claims(self) -> "CriterionCoverage":
        if self.state in _EVIDENCE_BEARING and not (
            self.evidence_event_ids or self.artifact_refs
        ):
            raise ValueError(
                f"{self.state.value} requires exact evidence references; "
                "model prose alone cannot mark a criterion"
            )
        return self


class FollowUpSuggestion(BaseModel):
    """Advisory interviewer follow-up, named to the rubric gap it probes."""

    model_config = ConfigDict(extra="forbid")

    question_text: str = Field(min_length=1, max_length=2_000)
    criterion_id: str = Field(min_length=1, max_length=100)
    why_this_is_still_open: str = Field(min_length=1, max_length=2_000)
    supporting_answer_event_ids: list[str] = Field(default_factory=list, max_length=32)
    expected_evidence_type: str = Field(min_length=1, max_length=300)
    question_id: str = Field(min_length=8, max_length=64)
    question_revision: int = Field(ge=0)
    rubric_digest: str = Field(min_length=64, max_length=64)
    unsupported: bool = False

    @model_validator(mode="after")
    def evidence_or_flagged(self) -> "FollowUpSuggestion":
        # An adversarially strong follow-up that cites no answer evidence is
        # either rejected upstream or must carry the unsupported flag visibly.
        if not self.supporting_answer_event_ids and not self.unsupported:
            raise ValueError(
                "suggestion cites no answer evidence; reject it or mark unsupported=true"
            )
        return self


class RubricEngine:
    """Deterministic floor: binding verification, fencing, caching, caps."""

    MAX_SUGGESTIONS = 3

    def __init__(self, rubric: RoleRubric) -> None:
        self._rubric = rubric
        self._digest = rubric.rubric_digest()
        # cache key: (question_id, question_revision, rubric_digest)
        self._coverage: dict[tuple[str, int, str], list[CriterionCoverage]] = {}
        self._suggestions: dict[tuple[str, int, str], list[FollowUpSuggestion]] = {}
        self.journal: list[dict[str, Any]] = []

    @property
    def rubric_digest(self) -> str:
        return self._digest

    def replace_rubric(self, rubric: RoleRubric) -> None:
        """Editing the rubric invalidates every cached result: the digest is
        part of the cache key, so stale coverage cannot be silently reused."""

        old = self._digest
        self._rubric = rubric
        self._digest = rubric.rubric_digest()
        if old != self._digest:
            self._coverage.clear()
            self._suggestions.clear()
            self.journal.append({"kind": "rubric_replaced", "from": old, "to": self._digest})

    def verify_evidence_binding(
        self, record: CriterionCoverage, events: list[dict[str, Any]]
    ) -> list[str]:
        """Deterministic floor checks; returns problem strings (empty = ok).

        - every cited event id must exist in the transcript;
        - an evidence-bearing state must cite at least one event whose text
          contains one of the criterion's evidence_required terms -- a vague
          answer cannot mark scale/failure/testing covered because the cited
          text never states those facts.
        """

        problems: list[str] = []
        criterion = next(
            (c for c in self._rubric.criteria if c.criterion_id == record.criterion_id), None
        )
        if criterion is None:
            return [f"unknown criterion {record.criterion_id}"]
        by_id = {e.get("event_id"): e for e in events}
        missing = [eid for eid in record.evidence_event_ids if eid not in by_id]
        if missing:
            problems.append(f"unknown transcript event id(s) {missing}")
        if record.state in _EVIDENCE_BEARING and not missing:
            cited_text = " ".join(
                str(by_id[eid].get("text") or "") for eid in record.evidence_event_ids
            ).lower()
            if record.evidence_event_ids and not any(
                term.lower() in cited_text for term in criterion.evidence_required
            ):
                problems.append(
                    f"cited events state none of the required evidence for "
                    f"{record.criterion_id}: {criterion.evidence_required}"
                )
        return problems

    def apply_coverage(
        self,
        records: list[CriterionCoverage],
        events: list[dict[str, Any]],
        *,
        active_question_id: str,
        active_revision: int,
    ) -> dict[str, Any]:
        """Accept a coverage analysis only for the ACTIVE revision under the
        CURRENT rubric digest; verify every binding; journal every rejection."""

        accepted: list[CriterionCoverage] = []
        rejected: list[dict[str, Any]] = []
        for record in records:
            if record.rubric_digest != self._digest:
                rejected.append({"criterion_id": record.criterion_id,
                                 "reason": "stale_rubric_digest"})
                continue
            if (record.question_id, record.question_revision) != (
                active_question_id, active_revision
            ):
                rejected.append({"criterion_id": record.criterion_id,
                                 "reason": "stale_question_revision"})
                continue
            problems = self.verify_evidence_binding(record, events)
            if problems:
                rejected.append({"criterion_id": record.criterion_id,
                                 "reason": "evidence_binding_failed",
                                 "problems": problems})
                continue
            accepted.append(record)
        if rejected:
            self.journal.append({"kind": "coverage_rejected", "rejected": rejected})
        if accepted:
            key = (active_question_id, active_revision, self._digest)
            existing = {r.criterion_id: r for r in self._coverage.get(key, [])}
            for record in accepted:
                existing[record.criterion_id] = record
            self._coverage[key] = list(existing.values())
        return {"accepted": len(accepted), "rejected": rejected}

    def coverage(self, question_id: str, revision: int) -> list[CriterionCoverage]:
        return list(self._coverage.get((question_id, revision, self._digest), []))

    def apply_suggestions(
        self,
        suggestions: list[FollowUpSuggestion],
        *,
        active_question_id: str,
        active_revision: int,
    ) -> list[FollowUpSuggestion]:
        """Cap at MAX_SUGGESTIONS, fence revision + rubric digest, drop
        suggestions for criteria the rubric does not contain."""

        known = {c.criterion_id for c in self._rubric.criteria}
        kept: list[FollowUpSuggestion] = []
        for suggestion in suggestions:
            if suggestion.rubric_digest != self._digest:
                continue
            if (suggestion.question_id, suggestion.question_revision) != (
                active_question_id, active_revision
            ):
                continue
            if suggestion.criterion_id not in known:
                continue
            kept.append(suggestion)
            if len(kept) >= self.MAX_SUGGESTIONS:
                break
        self._suggestions[(active_question_id, active_revision, self._digest)] = kept
        return kept

    def dismiss_suggestion(
        self, question_id: str, revision: int, criterion_id: str, actor: str
    ) -> None:
        """Journaled, attributable; deliberately does NOT touch coverage --
        dismissing a suggestion is not evidence the criterion was covered."""

        key = (question_id, revision, self._digest)
        self._suggestions[key] = [
            s for s in self._suggestions.get(key, []) if s.criterion_id != criterion_id
        ]
        self.journal.append({
            "kind": "suggestion_dismissed",
            "criterion_id": criterion_id,
            "question_id": question_id,
            "question_revision": revision,
            "actor": actor,
        })
