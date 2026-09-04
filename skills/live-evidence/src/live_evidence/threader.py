"""Deterministic question threading for the live timeline."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .scanner_fallback import question_words, same_progressive_question


class ThreadVerdict(BaseModel):
    model_config = ConfigDict(extra="forbid")
    relation: Literal["new_topic", "follow_up"]
    parent_id: str | None = None
    topic_title: str = Field(min_length=1)


@dataclass
class ThreadOutcome:
    verdict: ThreadVerdict | None = None
    error: str | None = None
    error_detail: str | None = None
    raw: str = ""
    elapsed_s: float = 0.0
    course_corrected: bool = field(default=False)


def _validate(raw: str, ledger_ids: set[str]) -> tuple[ThreadVerdict | None, str | None]:
    try:
        payload = json.loads(raw[raw.index("{"): raw.rindex("}") + 1])
    except (ValueError, json.JSONDecodeError):
        return None, "response is not a single JSON object"
    try:
        verdict = ThreadVerdict.model_validate(payload)
    except ValidationError as error:
        detail = "; ".join(
            f"{'.'.join(str(part) for part in item['loc'])}: {item['msg']}" for item in error.errors()
        )
        return None, detail
    if verdict.relation == "follow_up" and verdict.parent_id not in ledger_ids:
        return None, "parent_id: must be an exact id from LEDGER for follow_up"
    if verdict.relation == "new_topic" and verdict.parent_id is not None:
        return None, "parent_id: must be null for new_topic"
    if len(verdict.topic_title.split()) > 6:
        return None, "topic_title: at most 6 words"
    return verdict, None


def _topic_title(text: str) -> str:
    words = question_words(text)
    return " ".join(words[:6]).title() or "Question"


class QuestionThreader:
    """Relate a question to prior ledger entries without provider calls."""

    def classify(self, question_text: str, ledger: list[dict[str, Any]]) -> ThreadOutcome:
        ledger_ids = {str(item.get("id") or "") for item in ledger} - {""}
        if not ledger_ids:
            return ThreadOutcome(verdict=ThreadVerdict(
                relation="new_topic", parent_id=None, topic_title=_topic_title(question_text)
            ))

        matches: list[str] = []
        new_words = set(question_words(question_text))
        for item in ledger:
            item_id = str(item.get("id") or "")
            text = str(item.get("text") or "")
            old_words = set(question_words(text))
            overlap = len(new_words & old_words) / max(1, min(len(new_words), len(old_words)))
            if same_progressive_question(text, question_text) or overlap >= 0.55:
                matches.append(item_id)
        matches = [item for item in dict.fromkeys(matches) if item in ledger_ids]
        relation = "follow_up" if len(matches) == 1 else "new_topic"
        parent_id = matches[0] if relation == "follow_up" else None
        return ThreadOutcome(verdict=ThreadVerdict(
            relation=relation, parent_id=parent_id, topic_title=_topic_title(question_text)
        ))
