"""Post-run audit over Live Evidence session journals."""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


Disposition = Literal["visible", "held", "superseded", "missed"]


class AuditedQuestion(BaseModel):
    """One answer-needed moment reconstructed from journal rows."""

    model_config = ConfigDict(extra="forbid")

    question_id: str
    question_revision: int = Field(ge=1)
    disposition: Disposition
    reason_codes: list[str] = Field(default_factory=list)
    visible_card_ids: list[str] = Field(default_factory=list)


class MissAuditReport(BaseModel):
    """Complete post-run classification from an append-only journal."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True, serialize_by_alias=True)

    schema_id: Literal["live_evidence.miss_audit_report.v1"] = Field(
        default="live_evidence.miss_audit_report.v1",
        validation_alias="schema",
        serialization_alias="schema",
    )
    questions: list[AuditedQuestion]
    counts: dict[str, int]
    status: Literal["PASS"] = "PASS"


def build_miss_audit(journal_path: Path) -> MissAuditReport:
    """Classify answer-needed moments from a `session.jsonl` readback."""

    rows = _load_rows(journal_path)
    moments: dict[tuple[str, int], dict[str, Any]] = {}
    decisions: dict[tuple[str, int], list[dict[str, Any]]] = defaultdict(list)
    held_by_ledger: dict[tuple[str, int], list[str]] = defaultdict(list)

    for row in rows:
        kind = row.get("kind")
        payload = row.get("payload") or {}
        if kind == "answer_needed_moment":
            key = _key(payload)
            if key is not None:
                moments.setdefault(key, payload)
        elif kind == "card_publication_decision":
            key = _key(payload)
            if key is not None:
                decisions[key].append(payload)
        elif kind == "requirement_ledger_opened":
            key = _key(payload)
            if key is not None and _has_unresolved_blocking_requirement(payload):
                held_by_ledger[key].append("unresolved_blocking_requirement")

    terminal_by_question: dict[str, list[int]] = defaultdict(list)
    for key in set(decisions) | set(held_by_ledger):
        terminal_by_question[key[0]].append(key[1])

    audited: list[AuditedQuestion] = []
    for key in sorted(moments, key=lambda item: (item[0], item[1])):
        qid, revision = key
        visible_decision = _latest_status(decisions.get(key, []), "visible")
        if visible_decision is not None:
            audited.append(
                AuditedQuestion(
                    question_id=qid,
                    question_revision=revision,
                    disposition="visible",
                    reason_codes=list(visible_decision.get("reason_codes") or []),
                    visible_card_ids=list(visible_decision.get("visible_card_ids") or []),
                )
            )
            continue

        held_reasons = list(held_by_ledger.get(key, []))
        held_decision = _latest_status(decisions.get(key, []), "held")
        if held_decision is not None:
            held_reasons.extend(held_decision.get("reason_codes") or [])
        if held_reasons:
            audited.append(
                AuditedQuestion(
                    question_id=qid,
                    question_revision=revision,
                    disposition="held",
                    reason_codes=_unique(held_reasons),
                )
            )
            continue

        superseded_decision = _latest_status(decisions.get(key, []), "superseded")
        later_terminal = any(item > revision for item in terminal_by_question.get(qid, []))
        if superseded_decision is not None or later_terminal:
            reasons = (
                list(superseded_decision.get("reason_codes") or [])
                if superseded_decision is not None
                else ["later_revision_terminal"]
            )
            audited.append(
                AuditedQuestion(
                    question_id=qid,
                    question_revision=revision,
                    disposition="superseded",
                    reason_codes=_unique(reasons),
                )
            )
            continue

        audited.append(
            AuditedQuestion(
                question_id=qid,
                question_revision=revision,
                disposition="missed",
                reason_codes=["no_terminal_publication_decision"],
            )
        )

    counts: dict[str, int] = {name: 0 for name in ("visible", "held", "superseded", "missed")}
    for item in audited:
        counts[item.disposition] += 1
    return MissAuditReport(questions=audited, counts=counts)


def _load_rows(journal_path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in journal_path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def _key(payload: dict[str, Any]) -> tuple[str, int] | None:
    question_id = payload.get("question_id")
    revision = payload.get("question_revision")
    if isinstance(question_id, str) and isinstance(revision, int) and revision > 0:
        return question_id, revision
    return None


def _latest_status(decisions: list[dict[str, Any]], status: str) -> dict[str, Any] | None:
    matches = [item for item in decisions if item.get("status") == status]
    return matches[-1] if matches else None


def _has_unresolved_blocking_requirement(payload: dict[str, Any]) -> bool:
    for entry in payload.get("entries") or []:
        if entry.get("blocking") and entry.get("status") in {"unresolved", "UNRESOLVED"}:
            return True
    return False


def _unique(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        if value not in result:
            result.append(value)
    return result
