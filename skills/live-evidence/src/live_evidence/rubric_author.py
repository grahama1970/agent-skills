"""Model-authored rubric coverage over live transcripts (#1474).

The RubricEngine floor validates; this pass AUTHORS. A streaming SciLLM call
maps candidate answer spans to rubric criteria and proposes coverage records
plus at most one follow-up suggestion. Every authored record flows through the
deterministic floor (exact event refs required, cited text must state the
criterion's required facts, revision + rubric digest fenced); records the
floor rejects are journaled and never rendered. Purpose-gated: authorship runs
only for interviewer_assist and post_interview_review sessions, and no score,
ranking, or hire/decline output exists anywhere in the contract.
"""

from __future__ import annotations

import json
import os
import re
import urllib.request
from typing import Any

from .resolver import resolver_key
from .rubric import (
    CoverageState,
    CriterionCoverage,
    FollowUpSuggestion,
    RoleRubric,
    RubricEngine,
)

DEFAULT_URL = "http://127.0.0.1:4001"
DEFAULT_MODEL = "claude-sonnet-5"

_JSON_RE = re.compile(r"\{.*\}", re.S)

PROMPT = (
    "You map a candidate's answer to a role rubric. Use ONLY the transcript "
    "events below; cite event ids EXACTLY. A criterion is covered only when the "
    "cited event text literally states the required facts -- a polished vague "
    "answer leaves criteria untested. Never invent evidence. No scores, no "
    "verdicts.\n\n"
    "Return ONLY JSON:\n"
    '{"coverage":[{"criterion_id":str,"state":"covered|partially_covered|untested|'
    'contradicted","evidence_event_ids":[str],"rationale":str}],'
    '"followup":{"criterion_id":str,"question_text":str,"why":str,'
    '"supporting_answer_event_ids":[str]}}\n'
    "followup: exactly one, for the most job-relevant OPEN criterion; null if none.\n\n"
)


class RubricAuthor:
    """One bounded live authorship call; output is floor-validated upstream."""

    def __init__(self, *, url: str | None = None, model: str | None = None,
                 timeout_s: float = 60.0) -> None:
        self._url = (url or os.getenv("LIVE_EVIDENCE_SCILLM_URL") or DEFAULT_URL).rstrip("/")
        self._model = model or os.getenv("LIVE_EVIDENCE_RUBRIC_MODEL") or DEFAULT_MODEL
        self._timeout_s = timeout_s

    def author(self, rubric: RoleRubric, events: list[dict[str, Any]]) -> dict[str, Any] | None:
        key = resolver_key()
        if not key:
            return None
        criteria = [
            {"criterion_id": c.criterion_id, "label": c.label,
             "evidence_required": c.evidence_required}
            for c in rubric.criteria
        ]
        body = (
            PROMPT
            + "RUBRIC CRITERIA:\n" + json.dumps(criteria)
            + "\n\nCANDIDATE ANSWER EVENTS:\n"
            + json.dumps([{"event_id": e.get("event_id"), "text": e.get("text")}
                           for e in events][:24])
        )
        request = urllib.request.Request(
            f"{self._url}/v1/chat/completions",
            data=json.dumps({
                "model": self._model,
                "reasoning_effort": "low",
                "messages": [{"role": "user", "content": body}],
            }).encode(),
            headers={"Authorization": f"Bearer {key}",
                     "X-Caller-Skill": "live-evidence-rubric",
                     "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self._timeout_s) as response:
                payload = json.loads(response.read().decode())
            content = str(payload["choices"][0]["message"]["content"])
            match = _JSON_RE.search(content)
            return json.loads(match.group(0)) if match else None
        except Exception:
            return None


def apply_authored(
    engine: RubricEngine,
    authored: dict[str, Any],
    events: list[dict[str, Any]],
    *,
    question_id: str,
    question_revision: int,
) -> dict[str, Any]:
    """Push model output through the deterministic floor. Records that fail the
    contract (missing refs, non-stated facts, unknown criteria) are rejected by
    the floor and reported, never rendered."""

    records: list[CriterionCoverage] = []
    invalid: list[dict[str, Any]] = []
    for raw in authored.get("coverage") or []:
        try:
            records.append(CriterionCoverage(
                criterion_id=str(raw.get("criterion_id") or ""),
                state=CoverageState(str(raw.get("state") or "untested")),
                evidence_event_ids=[str(e) for e in raw.get("evidence_event_ids") or []][:16],
                rationale=str(raw.get("rationale") or "")[:2_000],
                question_id=question_id,
                question_revision=question_revision,
                rubric_digest=engine.rubric_digest,
            ))
        except Exception as exc:
            invalid.append({"raw": raw, "error": str(exc)[:200]})
    result = engine.apply_coverage(
        records, events,
        active_question_id=question_id, active_revision=question_revision,
    )
    followups: list[FollowUpSuggestion] = []
    raw_followup = authored.get("followup")
    if isinstance(raw_followup, dict) and raw_followup.get("criterion_id"):
        try:
            followups.append(FollowUpSuggestion(
                question_text=str(raw_followup.get("question_text") or "")[:2_000],
                criterion_id=str(raw_followup["criterion_id"]),
                why_this_is_still_open=str(raw_followup.get("why") or "open")[:2_000],
                supporting_answer_event_ids=[
                    str(e) for e in raw_followup.get("supporting_answer_event_ids") or []][:32],
                expected_evidence_type="concrete statement or measurement",
                question_id=question_id, question_revision=question_revision,
                rubric_digest=engine.rubric_digest,
                unsupported=not (raw_followup.get("supporting_answer_event_ids") or []),
            ))
        except Exception as exc:
            invalid.append({"raw": raw_followup, "error": str(exc)[:200]})
    kept = engine.apply_suggestions(
        followups, active_question_id=question_id, active_revision=question_revision,
    )
    return {"applied": result, "suggestions": len(kept), "invalid": invalid}
