"""Bounded candidate selection and deterministic scheduling/response disposition.

Memory retrieves; Jev ranks; host policy admits and executes. Model selection here
is a recommendation from a fresh host snapshot, not a provider capacity reservation.
"""
from __future__ import annotations

from typing import Literal
from pydantic import Field, JsonValue, model_validator
from .core import CONTRACT, Decision, Jev, Request, Strict


class Candidate(Strict):
    id: str = Field(min_length=1, max_length=128)
    description: str = Field(min_length=1, max_length=16000)
    payload: dict[str, JsonValue] = Field(default_factory=dict)
    pinned: bool = False


class Selection(Strict):
    status: Literal["selected", "no_match", "abstain", "error", "blocked"]
    ids: list[str]
    excluded: list[str] = Field(default_factory=list)
    uncertain: list[str] = Field(default_factory=list)
    receipt: Decision | None = None


def check_candidates(candidates: list[Candidate]) -> None:
    if len(candidates) > CONTRACT["max_candidates"] or len({c.id for c in candidates}) != len(candidates):
        raise ValueError("candidate_count_or_duplicates")
    if any(c.id == "no_match" for c in candidates):
        raise ValueError("reserved_candidate_id")


async def select(jev: Jev, state: JsonValue, candidates: list[Candidate], *, task: str = "tool", model: str = "jev-latest") -> Selection:
    check_candidates(candidates)
    if not candidates:
        return Selection(status="no_match", ids=[])
    req = Request(task=task, model=model, state={"task": state, "candidates": [c.model_dump() for c in candidates]},
                  questions={"selection": {"type": "choice", "instructions": CONTRACT["selection_instruction"],
                  "criteria": {**{c.id: c.description for c in candidates}, "no_match": "No candidate satisfies the request."}}})
    result = await jev.ask(req)
    if result.status != "accepted":
        return Selection(status=result.status, ids=[], receipt=result)
    selected = result.answers["selection"]["choice"]
    return Selection(status="no_match" if selected == "no_match" else "selected",
                     ids=[] if selected == "no_match" else [selected], receipt=result)


async def rank(jev: Jev, state: JsonValue, candidates: list[Candidate], *, task: str = "memory_relevance", model: str = "jev-latest") -> Selection:
    check_candidates(candidates)
    if not candidates:
        return Selection(status="no_match", ids=[])
    req = Request(task=task, model=model, state={"task": state, "candidates": [c.model_dump() for c in candidates]},
                  questions={f"c{i}": {"type": "noul", "instructions": CONTRACT["relevance_instruction"].format(index=i)}
                             for i in range(len(candidates))})
    result = await jev.ask(req)
    if result.status in {"error", "blocked"} or not result.answers:
        return Selection(status=result.status, ids=[c.id for c in candidates], uncertain=[c.id for c in candidates], receipt=result)
    kept, excluded, uncertain = [], [], []
    for i, c in enumerate(candidates):
        p = result.answers[f"c{i}"]["noul"]
        certain = f"c{i}" in result.confident
        if not c.pinned and certain and p < 0.5:
            excluded.append(c.id)
        else:
            kept.append((i, c.id, p))
        if not certain:
            uncertain.append(c.id)
    kept.sort(key=lambda row: (-row[2], row[0]))
    return Selection(status="abstain" if uncertain else "selected" if kept else "no_match",
                     ids=[row[1] for row in kept], excluded=excluded, uncertain=uncertain, receipt=result)


class ModelOption(Strict):
    id: str
    capabilities: list[str]
    qualified: bool
    authorized: bool
    available_slots: int = Field(ge=0)
    observed_at_ms: int = Field(ge=0)
    expires_at_ms: int = Field(ge=0)
    cooldown_until_ms: int = Field(ge=0)
    estimated_total_cost: float = Field(ge=0)
    estimated_latency_ms: int = Field(ge=0)

    @model_validator(mode="after")
    def timestamps(self):
        if self.expires_at_ms < self.observed_at_ms:
            raise ValueError("snapshot_timestamps")
        return self


def choose_model(options: list[ModelOption], *, required: list[str], now_ms: int,
                 max_cost: float, deadline_ms: int, pinned: str | None = None) -> str | None:
    """Pure recommendation. Host must atomically reserve and recheck before dispatch."""
    eligible = [m for m in options if m.qualified and m.authorized and m.available_slots > 0
                and m.observed_at_ms <= now_ms < m.expires_at_ms and m.cooldown_until_ms <= now_ms
                and set(required) <= set(m.capabilities) and m.estimated_total_cost <= max_cost
                and now_ms + m.estimated_latency_ms <= deadline_ms and (pinned is None or m.id == pinned)]
    return min(eligible, key=lambda m: (m.estimated_total_cost, m.estimated_latency_ms, m.id)).id if eligible else None


def memory_disposition(route: str, *, work_requested: bool, covers_request: bool = False,
                       policy_denied: bool = False, human_checkpoint: bool = False,
                       scope_only: bool = False, dependency_required: bool = False) -> str:
    """Consume host-validated Memory flags, never Jev's speculation about authority."""
    if any(type(x) is not bool for x in (work_requested, covers_request, policy_denied, human_checkpoint, scope_only, dependency_required)):
        raise ValueError("memory_flags")
    if policy_denied:
        return "blocked"
    if route == "CLARIFY" or route == "DRAFT":
        return "await_human" if human_checkpoint else "blocked"
    if route == "ANSWER":
        return "respond" if covers_request and not work_requested else "continue_agent"
    if route == "NO_MATCH":
        return "continue_agent"
    if route == "DEFLECT":
        return "continue_agent" if scope_only else "blocked"
    if route == "ERROR":
        return "blocked" if dependency_required else "continue_agent"
    return "blocked"


async def classify(jev: Jev, state: JsonValue, *, model: str = "jev-latest") -> Decision:
    """Batch task intent and capability judgment; neither is a permission decision."""
    return await jev.ask(Request(task="harness_classification", state=state, model=model,
        questions={name: {"type": "choice", "instructions": "Classify the actual request; choose no_match if uncertain or unsupported.",
                          "criteria": {**CONTRACT[name], "no_match": "None of the specified categories fits."}}
                   for name in ("intents", "capabilities")}))
