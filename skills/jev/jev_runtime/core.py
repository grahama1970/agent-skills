"""Native Jev judgments with strict response validation and content-bound receipts.

Inputs are typed requests and explicit egress policy. Outputs are decisions, never
execution authority. SDK errors, uncertainty and malformed data do not become success.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import math
import os
import struct
import time
from importlib.resources import files
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue, ValidationError, model_validator

CONTRACT = json.loads(files("jev_runtime").joinpath("contract.json").read_text())


class Strict(BaseModel):
    """Closed, immutable boundary; callers must construct a new policy to change it."""
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True, allow_inf_nan=False)


class Policy(Strict):
    allow_egress: bool = False
    data_class: Literal["public", "approved_internal", "restricted", "unknown"] = "unknown"
    threshold: float = Field(default=0.98, gt=0.5, le=1)
    timeout_ms: int = Field(default=1500, ge=100, le=10000)
    blocked_terms: list[str] = Field(default_factory=list)


class Request(Strict):
    task: str = Field(min_length=1, max_length=128)
    state: JsonValue
    questions: dict[str, dict[str, JsonValue]]
    model: str = Field(default="jev-latest", min_length=1, max_length=128)

    @model_validator(mode="after")
    def check_questions(self) -> Request:
        validate_questions(self.questions)
        fingerprint(self.model_dump())
        return self


class Noul(Strict):
    type: Literal["noul"]
    noul: float = Field(ge=0, le=1)


class Choice(Strict):
    type: Literal["choice"]
    choice: str
    confidence: float = Field(ge=0, le=1)
    probabilities: dict[str, float]


class Score(Strict):
    type: Literal["score"]
    score: float
    confidence: float = Field(ge=0, le=1)
    probabilities: dict[str, float]
    legend: dict[str, JsonValue] | None = None


Answer = Annotated[Noul | Choice | Score, Field(discriminator="type")]


class Response(Strict):
    model: str = Field(min_length=1)
    answers: dict[str, Answer]
    usage: dict[str, int] | None = None


class Decision(Strict):
    schema_version: Literal["jev.decision.v1"] = "jev.decision.v1"
    status: Literal["accepted", "abstain", "blocked", "error"]
    reason: str
    request_hash: str
    policy_hash: str
    requested_model: str
    resolved_model: str | None = None
    answers: dict[str, JsonValue] = Field(default_factory=dict)
    confident: list[str] = Field(default_factory=list)
    usage: dict[str, int] | None = None
    duration_ms: float = 0.0
    validation_errors: list[dict[str, JsonValue]] = Field(default_factory=list)


def fingerprint(value: Any) -> str:
    """Cross-language v1 binding: typed JSON tree with IEEE-754 number encoding.

    Safe integers, finite doubles and Unicode scalar strings only. The typed tree
    avoids collisions between application strings and encoded numeric values.
    """
    def encode(v: Any) -> Any:
        if v is None:
            return ["null"]
        if isinstance(v, bool):
            return ["bool", v]
        if isinstance(v, (int, float)):
            if not math.isfinite(v) or (float(v).is_integer() and abs(v) > 2**53 - 1):
                raise ValueError("unsupported_number")
            return ["number", struct.pack(">d", float(v) if v else 0.0).hex()]
        if isinstance(v, str):
            v.encode("utf-8", errors="strict")
            return ["string", v]
        if isinstance(v, list):
            return ["array", [encode(x) for x in v]]
        if isinstance(v, dict) and all(isinstance(k, str) for k in v):
            return ["object", [[encode(k), encode(v[k])] for k in sorted(v)]]
        raise ValueError("not_json")
    wire = json.dumps(encode(value), ensure_ascii=False, separators=(",", ":")).encode()
    return hashlib.sha256(wire).hexdigest()


def validate_questions(questions: dict) -> None:
    if not 1 <= len(questions) <= CONTRACT["max_questions"]:
        raise ValueError("question_count")
    for qid, q in questions.items():
        if not qid or not isinstance(q, dict) or set(q) - {"type", "instructions", "criteria"}:
            raise ValueError("question_shape")
        kind, criteria = q.get("type"), q.get("criteria")
        if kind == "choice":
            if not isinstance(criteria, dict) or len(criteria) < 2:
                raise ValueError("choice_criteria")
        elif kind == "score":
            if not isinstance(criteria, list) or len(criteria) < 2:
                raise ValueError("score_criteria")
        elif kind == "noul":
            if criteria is not None and (not isinstance(criteria, dict) or set(criteria) - {"true", "false"}):
                raise ValueError("noul_criteria")
        else:
            raise ValueError("question_type")


def wire_request(request: Request) -> dict:
    return {"state": request.state, "questions": request.questions, "model": request.model}


def egress_reason(body: Any, policy: Policy) -> str | None:
    # Markers supplement authorization; they are NOT a general DLP classifier.
    if not policy.allow_egress or policy.data_class not in {"public", "approved_internal"}:
        return "egress_not_authorized"
    text = json.dumps(body, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
    if len(text.encode()) > CONTRACT["max_payload_bytes"]:
        return "payload_budget"
    if any(term.lower() in text.lower() for term in [*CONTRACT["blocked_markers"], *policy.blocked_terms] if term):
        return "restricted_payload"
    return None


def validate_response(request: Request, raw: Any) -> Response:
    fingerprint(raw)
    response = Response.model_validate(raw)
    if request.model != "jev-latest" and response.model != request.model:
        raise ValueError("model_binding")
    if set(response.answers) != set(request.questions):
        raise ValueError("answer_keys")
    if response.usage and any(v < 0 for v in response.usage.values()):
        raise ValueError("usage_domain")
    for qid, answer in response.answers.items():
        q = request.questions[qid]
        if answer.type != q["type"]:
            raise ValueError("answer_type")
        if isinstance(answer, Noul):
            continue
        labels = set(q["criteria"]) if isinstance(answer, Choice) else {str(i) for i in range(len(q["criteria"]))}
        probabilities = answer.probabilities
        if set(probabilities) != labels or any(not math.isfinite(v) or not 0 <= v <= 1 for v in probabilities.values()):
            raise ValueError("probability_domain")
        if abs(sum(probabilities.values()) - 1) > 0.001:
            raise ValueError("probability_sum")
        if isinstance(answer, Choice):
            if answer.choice not in labels or probabilities[answer.choice] + 1e-9 < max(probabilities.values()):
                raise ValueError("choice_domain")
        else:
            expected = sum(int(k) * p for k, p in probabilities.items())
            if abs(answer.score - expected) > 0.001:
                raise ValueError("score_domain")
            if answer.legend is not None and answer.legend != {str(i): v for i, v in enumerate(q["criteria"])}:
                raise ValueError("score_legend")
    return response


def confident_ids(response: Response, threshold: float) -> list[str]:
    ids = []
    for qid, answer in response.answers.items():
        if isinstance(answer, Noul):
            confident = answer.noul >= threshold or answer.noul <= 1 - threshold
        elif isinstance(answer, Choice):
            confident = answer.confidence >= threshold and answer.probabilities[answer.choice] >= threshold
        else:
            confident = answer.confidence >= threshold
        if confident:
            ids.append(qid)
    return ids


class Jev:
    """Reusable, lazy native SDK client. No retries, execution or hidden fallback."""
    def __init__(self, policy: Policy | None = None, *, transport=None):
        self.policy = policy or Policy()
        self.transport = transport
        self._sdk = None

    async def _send(self, body: dict) -> Any:
        if self.transport is not None:
            return await self.transport(body)
        if self._sdk is None:
            from typesafe_sdk import AsyncTypeSafeClient, RetryPolicy
            logging.getLogger("typesafe_sdk").setLevel(logging.CRITICAL)
            self._sdk = AsyncTypeSafeClient(
                api_key=os.getenv("JEV_API_KEY") or os.getenv("TYPESAFE_API_KEY"),
                base_url="https://api.typesafe.ai", retry=RetryPolicy(max_retries=0),
                timeout=self.policy.timeout_ms / 1000,
            )
        logging.getLogger("typesafe_sdk").setLevel(logging.CRITICAL)
        result = await self._sdk.system_one(**body)
        return result.model_dump(mode="json", exclude_none=True)

    async def ask(self, request: Request, *, required: list[str] | None = None) -> Decision:
        # Snapshot before awaiting: mutation cannot invalidate the gate/hash binding.
        request = Request.model_validate(request.model_dump())
        policy = Policy.model_validate(self.policy.model_dump())
        needed = list(request.questions) if required is None else list(required)
        if not needed or not set(needed) <= set(request.questions):
            raise ValueError("required_questions")
        start = time.monotonic()
        base = dict(request_hash=fingerprint(request.model_dump()), policy_hash=fingerprint(policy.model_dump()), requested_model=request.model)
        def finish(status: str, reason: str, **kwargs) -> Decision:
            return Decision(**base, status=status, reason=reason, duration_ms=(time.monotonic()-start)*1000, **kwargs)
        body = wire_request(request)
        reason = egress_reason(body, policy)
        if reason:
            return finish("blocked", reason)
        try:
            async with asyncio.timeout(policy.timeout_ms / 1000):
                raw = await self._send(body)
        except asyncio.CancelledError:
            raise
        except TimeoutError:
            return finish("abstain", "deadline")
        except Exception:
            return finish("error", "provider_error")  # Never echo SDK error bodies/secrets.
        try:
            response = validate_response(request, raw)
        except (ValueError, TypeError, OverflowError) as exc:
            errors = [{"type": "response_validation", "loc": [], "msg": "Response violates submitted question contract"}]
            if isinstance(exc, ValidationError):
                errors = [{"type": e["type"], "loc": list(e["loc"]), "msg": "Invalid typed response"} for e in exc.errors()[:8]]
            return finish("error", "invalid_response", validation_errors=errors)
        confident = confident_ids(response, policy.threshold)
        accepted = set(needed) <= set(confident)
        return finish("accepted" if accepted else "abstain", "qualified" if accepted else "uncertain",
                      answers={k: v.model_dump(exclude_none=True) for k, v in response.answers.items()},
                      confident=confident, usage=response.usage, resolved_model=response.model)

    async def aclose(self) -> None:
        if self._sdk is not None:
            await self._sdk.aclose()
            self._sdk = None

    async def __aenter__(self) -> Jev:
        return self

    async def __aexit__(self, *_args) -> None:
        await self.aclose()
