#!/usr/bin/env python3
"""Validate lazy_report_shame collaboration JSON packets."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator
from pydantic_core import PydanticCustomError


def is_minted_code(value: str) -> bool:
    marker = "_unclassified_"
    idx = value.rfind(marker)
    if idx <= 0:
        return False
    suffix = value[idx + len(marker):]
    return len(suffix) == 8 and all(c in "0123456789abcdef" for c in suffix)


class CollabTriage(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: str = Field(min_length=1)
    layer: str = Field(min_length=1)
    cause: str = Field(min_length=1)

    @model_validator(mode="after")
    def code_shape(self) -> "CollabTriage":
        # ponytail: shape-only minted-code gate; use triage-error catalog import if non-minted codes need strict validation here.
        if is_minted_code(self.code) or self.code in {"missing_answer_to_question", "collab_acceptor_must_differ"}:
            return self
        raise PydanticCustomError("collab_triage_code_unrecognized", "triage.code must be minted or known", {"field": "triage.code"})


class CollabQuestion(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_: Literal["lazy_report_shame.collab_question.v1"] = Field(alias="schema")
    question_id: str = Field(min_length=1)
    triage: CollabTriage
    question: str = Field(min_length=1)
    required_response_schema: Literal["lazy_report_shame.collab_answer.v1"]
    allowed_answers: list[str] = Field(min_length=1)


class SmallestPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    files: list[str] = Field(default_factory=list)
    changes: list[str] = Field(default_factory=list)
    proof_command: str | None = Field(default=None, min_length=1)


class CollabAnswer(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_: Literal["lazy_report_shame.collab_answer.v1"] = Field(alias="schema")
    question_id: str = Field(min_length=1)
    answer: str = Field(min_length=1)
    triage: CollabTriage
    allowed_answers: list[str] = Field(min_length=1)
    smallest_patch: SmallestPatch | None = None
    proof_boundary: str | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def answer_allowed(self) -> "CollabAnswer":
        if self.answer not in self.allowed_answers:
            raise PydanticCustomError("collab_answer_not_allowed", "answer must be one of allowed_answers", {"field": "answer"})
        return self


class ExchangeRef(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question_id: str = Field(min_length=1)
    question_valid: bool
    answer_valid: bool


class CollabAcceptance(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_: Literal["lazy_report_shame.collab_acceptance.v1"] = Field(alias="schema")
    implementer: str = Field(min_length=1)
    acceptor: str = Field(min_length=1)
    task_msg_id: str = Field(min_length=1)
    peer_rejection_msg_id: str = Field(min_length=1)
    changed_action: str = Field(min_length=1)
    acceptance_msg_id: str = Field(min_length=1)
    exchange_refs: list[ExchangeRef] = Field(default_factory=list)
    verified_command: str | None = Field(default=None, min_length=1)
    verified_result: str | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def peer_must_accept(self) -> "CollabAcceptance":
        if self.acceptor == self.implementer:
            raise PydanticCustomError("collab_acceptor_must_differ", "acceptor must differ from implementer", {"field": "acceptor"})
        if any(not (ref.question_valid and ref.answer_valid) for ref in self.exchange_refs):
            raise PydanticCustomError("collab_exchange_not_validated", "exchange_refs must be valid", {"field": "exchange_refs"})
        return self


SCHEMAS: dict[str, type[BaseModel]] = {
    "lazy_report_shame.collab_question.v1": CollabQuestion,
    "lazy_report_shame.collab_answer.v1": CollabAnswer,
    "lazy_report_shame.collab_acceptance.v1": CollabAcceptance,
}


def invalid(errors: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "schema": "lazy_report_shame.collab_acceptance.validation_result.v1",
        "valid": False,
        "errors": [
            {
                "type": str(e.get("type") or "invalid_collab_acceptance"),
                "loc": [str(p) for p in e.get("loc", ())],
                "msg": str(e.get("msg") or "invalid collab acceptance"),
                "ctx": e.get("ctx") if isinstance(e.get("ctx"), dict) else {},
            }
            for e in errors
        ],
    }


def validate_json(raw: str) -> BaseModel:
    data = json.loads(raw)
    model = SCHEMAS.get(data.get("schema") if isinstance(data, dict) else None)
    if model is None:
        raise PydanticCustomError("collab_schema_unknown", "unknown collaboration schema", {"field": "schema"})
    return model.model_validate(data)


def validate_exchange(question_raw: str, answer_raw: str) -> tuple[CollabQuestion, CollabAnswer]:
    question = CollabQuestion.model_validate(json.loads(question_raw))
    answer = CollabAnswer.model_validate(json.loads(answer_raw))
    if answer.question_id != question.question_id:
        raise PydanticCustomError("collab_question_id_mismatch", "answer.question_id must match question.question_id", {"field": "question_id"})
    if answer.allowed_answers != question.allowed_answers:
        raise PydanticCustomError("collab_allowed_answers_mismatch", "answer.allowed_answers must match question.allowed_answers", {"field": "allowed_answers"})
    if answer.schema_ != question.required_response_schema:
        raise PydanticCustomError("collab_response_schema_mismatch", "answer schema must match question.required_response_schema", {"field": "schema"})
    return question, answer


def main() -> int:
    if len(sys.argv) == 3 and sys.argv[1] == "validate":
        raw = sys.stdin.read() if sys.argv[2] == "-" else Path(sys.argv[2]).read_text()
        try:
            validate_json(raw)
        except ValidationError as exc:
            print(json.dumps(invalid(exc.errors(include_url=False))))
            return 1
        except Exception as exc:
            error_type = getattr(exc, "type", "invalid_json")
            print(json.dumps(invalid([{"type": error_type, "loc": [], "msg": str(exc), "ctx": {}}])))
            return 1
        print(json.dumps({"schema": "lazy_report_shame.collab_acceptance.validation_result.v1", "valid": True}))
        return 0
    if len(sys.argv) == 4 and sys.argv[1] == "validate-exchange":
        try:
            validate_exchange(Path(sys.argv[2]).read_text(), Path(sys.argv[3]).read_text())
        except ValidationError as exc:
            print(json.dumps(invalid(exc.errors(include_url=False))))
            return 1
        except Exception as exc:
            error_type = getattr(exc, "type", "invalid_json")
            print(json.dumps(invalid([{"type": error_type, "loc": [], "msg": str(exc), "ctx": {}}])))
            return 1
        print(json.dumps({"schema": "lazy_report_shame.collab_acceptance.validation_result.v1", "valid": True, "exchange_valid": True}))
        return 0
    print(__doc__, file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
