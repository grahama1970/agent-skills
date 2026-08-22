"""Evidence-triggered action lane (#1475).

One governed envelope -- live_evidence.action_candidate.v1 -- for exactly
three action kinds: fact_check, remember_fact, open_artifact. Candidates are
proposed by the stage-1 resolver's extended vocabulary (the resolver stays the
single ambient authority; there is no parallel detector), bound to exact
transcript events, and NOTHING executes without an explicit human approval.
Execution is journaled, revision-fenced, and policy-gated in the backend; an
unsupported fact-check reports unresolved, never invented support.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from .models import CapabilityPolicy, SessionPurpose


class ActionCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True, serialize_by_alias=True)

    schema_id: Literal["live_evidence.action_candidate.v1"] = Field(
        default="live_evidence.action_candidate.v1",
        validation_alias="schema", serialization_alias="schema",
    )
    action_id: str = Field(default_factory=lambda: uuid4().hex, min_length=8)
    kind: Literal["fact_check", "remember_fact", "open_artifact"]
    summary: str = Field(min_length=1, max_length=600)
    payload: str = Field(min_length=1, max_length=2_000)
    trigger_event_ids: list[str] = Field(min_length=1, max_length=16)
    question_id: str | None = Field(default=None, min_length=8, max_length=64)
    question_revision: int = Field(default=0, ge=0)
    evidence_refs: list[str] = Field(default_factory=list, max_length=8)
    policy_digest: str = Field(min_length=64, max_length=64)
    status: Literal[
        "proposed", "approved", "executed", "unresolved",
        "fenced_stale", "rejected_by_policy",
    ] = "proposed"
    approved_by: str | None = None
    execution_receipt: dict[str, Any] | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ActionEngine:
    """Proposal + human-approved execution over the one envelope."""

    def __init__(self, *, purpose: SessionPurpose, policy: CapabilityPolicy,
                 policy_digest: str) -> None:
        self._purpose = purpose
        self._policy = policy
        self._policy_digest = policy_digest
        self._pending: dict[str, ActionCandidate] = {}
        self.journal: list[dict[str, Any]] = []

    # -- proposal ---------------------------------------------------------

    def propose(self, raw_candidates: list[dict[str, Any]], *,
                trigger_event_ids: list[str],
                question_id: str | None, question_revision: int) -> list[ActionCandidate]:
        """Resolver-authored candidates enter here. formal_assessment proposes
        NOTHING: the rejection happens in the backend and is journaled."""

        if self._purpose is SessionPurpose.FORMAL_ASSESSMENT:
            if raw_candidates:
                self.journal.append({"kind": "action_rejected_by_policy",
                                     "reason": "formal_assessment_proposes_nothing",
                                     "count": len(raw_candidates)})
            return []
        accepted: list[ActionCandidate] = []
        for raw in raw_candidates[:6]:
            kind = str(raw.get("kind") or "")
            if kind not in {"fact_check", "remember_fact", "open_artifact"}:
                continue
            payload = str(raw.get("payload") or raw.get("claim") or raw.get("fact")
                          or raw.get("artifact") or "").strip()
            if not payload:
                continue
            candidate = ActionCandidate(
                kind=kind,  # type: ignore[arg-type]
                summary=str(raw.get("summary") or payload)[:600],
                payload=payload[:2_000],
                trigger_event_ids=list(trigger_event_ids)[:16],
                question_id=question_id,
                question_revision=question_revision,
                policy_digest=self._policy_digest,
            )
            self._pending[candidate.action_id] = candidate
            accepted.append(candidate)
        if accepted:
            self.journal.append({"kind": "action_candidates_proposed",
                                 "action_ids": [c.action_id for c in accepted]})
        return accepted

    def pending(self) -> list[ActionCandidate]:
        return [c for c in self._pending.values() if c.status == "proposed"]

    # -- execution --------------------------------------------------------

    async def approve(self, action_id: str, *, actor: str,
                      active_question: tuple[str | None, int],
                      coordinator: Any, state: Any) -> ActionCandidate:
        """Human approval executes exactly one candidate, fenced and gated."""

        candidate = self._pending.get(action_id)
        if candidate is None:
            raise KeyError(action_id)
        if candidate.status != "proposed":
            return candidate
        # Revision fence: a candidate proposed against an older question
        # revision is journaled stale, never executed.
        if candidate.question_id and (
            (candidate.question_id, candidate.question_revision) != active_question
        ):
            candidate.status = "fenced_stale"
            self.journal.append({"kind": "action_fenced_stale",
                                 "action_id": action_id, "actor": actor})
            return candidate
        candidate.approved_by = actor
        candidate.status = "approved"
        receipt: dict[str, Any] = {"actor": actor, "kind": candidate.kind}
        try:
            return await self._execute(candidate, receipt, coordinator=coordinator, state=state)
        except Exception as exc:  # execution failure is an outcome, not a 500
            candidate.status = "unresolved"
            receipt["error"] = f"{type(exc).__name__}: {exc}"[:300]
            candidate.execution_receipt = receipt
            self.journal.append({"kind": "action_executed", "action_id": candidate.action_id,
                                 "status": "unresolved", "receipt": receipt})
            return candidate

    async def _execute(self, candidate: ActionCandidate, receipt: dict[str, Any], *,
                       coordinator: Any, state: Any) -> ActionCandidate:

        if candidate.kind == "fact_check":
            if not self._policy.external_search:
                candidate.status = "rejected_by_policy"
                self.journal.append({"kind": "action_rejected_by_policy",
                                     "action_id": candidate.action_id,
                                     "reason": "external_search_disabled"})
                return candidate
            from .models import ManualSearchRequest, RetrievalLane

            card = await coordinator.manual_search(
                ManualSearchRequest(lane=RetrievalLane.BRAVE, query=candidate.payload[:500])
            )
            supported = bool(card.sources)
            receipt.update({"card_id": card.card_id, "sources": len(card.sources),
                            "resolution": "supported" if supported else "unresolved"})
            candidate.status = "executed" if supported else "unresolved"

        elif candidate.kind == "remember_fact":
            from .salient_facts import SalientFact, SalientFactWriter, compute_fact_id

            session_id = state.session_id() or "no-session"
            fact = SalientFact(
                fact_id=compute_fact_id(session_id, "decision", candidate.trigger_event_ids),
                session_id=session_id,
                speaker="participant",
                value=candidate.payload,
                source_event_ids=candidate.trigger_event_ids,
                source_sha256=candidate.policy_digest,
            )
            writer = SalientFactWriter(
                coordinator.settings.memory_url,
                timeout_s=30.0,  # the live boundary slows under full-suite load
            )
            ok, detail = await writer.write_and_confirm(fact)
            receipt.update({"fact_id": fact.fact_id, "readback_ok": ok, "detail": detail[:300]})
            candidate.status = "executed" if ok else "unresolved"

        elif candidate.kind == "open_artifact":
            if not self._policy.retrieve_local_evidence:
                candidate.status = "rejected_by_policy"
                self.journal.append({"kind": "action_rejected_by_policy",
                                     "action_id": candidate.action_id,
                                     "reason": "retrieve_local_evidence_disabled"})
                return candidate
            resolved = _resolve_artifact(candidate.payload, coordinator)
            receipt.update(resolved)
            candidate.status = "executed" if resolved.get("exists") else "unresolved"

        candidate.execution_receipt = receipt
        self.journal.append({"kind": "action_executed", "action_id": candidate.action_id,
                             "status": candidate.status, "receipt": receipt})
        return candidate


def _resolve_artifact(reference: str, coordinator: Any) -> dict[str, Any]:
    """Resolve a spoken artifact reference against the configured repo roots."""

    token = reference.strip().split()[-1] if reference.strip() else ""
    token = token.strip(".,!?\"'")
    roots = getattr(getattr(coordinator, "settings", None), "repo_roots", None) or []
    for root in roots:
        root_path = Path(str(root))
        if not root_path.exists():
            continue
        direct = root_path / token
        if direct.is_file():
            return {"path": str(direct), "exists": True, "root": str(root_path)}
        matches = list(root_path.rglob(token)) if token else []
        if matches:
            return {"path": str(matches[0]), "exists": True, "root": str(root_path)}
    return {"path": token, "exists": False, "roots_searched": [str(r) for r in roots]}


async def propose_research(coordinator: Any, state: Any, journal: Any, *,
                           query: str, trigger_event_ids: list[str],
                           question_id: str, question_revision: int,
                           policy: CapabilityPolicy) -> None:
    """(goal v2) Local evidence came up short for a real question: PROPOSE
    bounded external research with the derived query. The human approves the
    egress; the raw transcript never leaves the workstation."""

    digest = state.session_policy_digest()
    if coordinator.actions is None or coordinator.actions._policy_digest != digest:
        coordinator.actions = ActionEngine(
            purpose=state.session_purpose(), policy=policy, policy_digest=digest,
        )
    coordinator.actions.propose(
        [{"kind": "fact_check",
          "summary": f"Research externally: {query[:140]}",
          "payload": query[:500]}],
        trigger_event_ids=trigger_event_ids,
        question_id=question_id, question_revision=question_revision,
    )
    for entry in coordinator.actions.journal:
        await journal.append(state.session_id(), entry.pop("kind"), entry,
                             policy_digest=digest)
    coordinator.actions.journal.clear()


def research_warranted(card: Any, verdict: Any, ranked: list) -> bool:
    """(goal v2) External research is proposed when local evidence failed OR
    the question is research-shaped with no memory-lane support -- spurious
    ripgrep matches on filler words must not silence the research lane."""

    from .models import CardStatus

    if card.status is CardStatus.INSUFFICIENT:
        return True
    # Research-type questions always get the offer: a live memory service
    # returns weak semantic neighbors for almost anything, so "has local
    # sources" is no evidence the web is not the real answer's home. It is
    # only a proposal; the human decides.
    return verdict is not None and getattr(verdict, "question_type", None) == "research"
