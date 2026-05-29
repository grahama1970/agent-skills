"""CAE gap review protocol for evidence-case-backed /ask reviews."""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from .ask_oracle import _run_protocol_turn
from .run_state import AskRunState, NoopRunState, safe_run_id


DEFAULT_CAE_REVIEWERS = "Brandon:cae_policy_evidence,Margaret:cae_technical_enforcement,Jennifer:cae_control_mapping"
DEFAULT_CAE_JUDGE = "CAE Gap Judge"
CAE_MODE = "cae-gap-review"
TERMINAL_ROUTES = {"stop", "human_reviewer", "additional_retrieval"}
REROUTABLE_ROLES = {
    "policy_evidence": "cae_policy_evidence",
    "technical_enforcement": "cae_technical_enforcement",
    "control_mapping": "cae_control_mapping",
}
ROLE_DOCS = {
    "cae_policy_evidence": "cae-policy-evidence.md",
    "cae_technical_enforcement": "cae-technical-enforcement.md",
    "cae_control_mapping": "cae-control-mapping.md",
    "cae_gap_judge": "cae-gap-judge.md",
}
VALID_JUDGE_KEYS = {
    "review_id",
    "decision",
    "decision_summary",
    "cited_basis",
    "missing_evidence",
    "route_to",
    "stop_reason",
    "final_status",
}
SOURCE_ARTIFACT_REQUIREMENTS = [
    "memory_or_dogpile_context_is_not_evidence",
    "retrieved_artifacts_need_source_id",
    "source_artifacts_must_be_in_evidence_case_payload",
    "qra_corrections_require_new_create_evidence_case_run",
]


ModelTurn = Callable[..., tuple[str, str, str | None]]


def parse_cae_reviewer_specs(raw: str | None) -> list[dict[str, str]]:
    """Parse comma-separated `Persona:role` CAE reviewer specs."""
    chunks = [chunk.strip() for chunk in (raw or DEFAULT_CAE_REVIEWERS).split(",") if chunk.strip()]
    reviewers: list[dict[str, str]] = []
    for index, chunk in enumerate(chunks):
        persona = chunk
        role = ""
        if ":" in chunk:
            persona, role = [part.strip() for part in chunk.split(":", 1)]
        if not role:
            role = list(REROUTABLE_ROLES.values())[index % len(REROUTABLE_ROLES)]
        reviewers.append(
            {
                "persona": persona.strip() or f"Reviewer {index + 1}",
                "role": role.replace("-", "_"),
            }
        )
    return reviewers


def run_cae_gap_review(
    *,
    question: str,
    scope: str,
    evidence_case: dict[str, Any],
    reviewers: str | None = None,
    judge: str = DEFAULT_CAE_JUDGE,
    max_rounds: int = 3,
    model: str,
    reasoning_effort: str,
    timeout: float,
    idle_timeout: float,
    heartbeat_interval: float,
    backend: str,
    dogpile_mode: str,
    run_state: AskRunState | NoopRunState | None = None,
    model_turn: ModelTurn | None = None,
) -> dict[str, Any]:
    """Run initial CAE reviewers, then reroute only judge-identified gaps."""
    review_id = safe_run_id(f"cae-{_case_identifier(evidence_case) or question}")[:96]
    max_rounds = max(1, max_rounds)
    participants = parse_cae_reviewer_specs(reviewers)
    turn = model_turn or run_cae_model_turn
    state = _initial_loop_state(
        review_id=review_id,
        question=question,
        scope=scope,
        evidence_case=evidence_case,
        participants=participants,
        judge=judge,
        max_rounds=max_rounds,
        dogpile_mode=dogpile_mode,
    )

    if run_state:
        run_state.step_started("cae_gap_review", review_id=review_id, reviewers=len(participants), max_rounds=max_rounds)

    role_outputs = _run_initial_reviewers(
        state=state,
        participants=participants,
        model=model,
        reasoning_effort=reasoning_effort,
        timeout=timeout,
        idle_timeout=idle_timeout,
        heartbeat_interval=heartbeat_interval,
        backend=backend,
        turn=turn,
    )
    state["role_outputs"] = role_outputs

    seen_missing: set[str] = set()
    final_judge: dict[str, Any] = {}
    halt_reason = "max_rounds"

    for round_number in range(1, max_rounds + 1):
        state["round"] = round_number
        judge_turn = _run_judge_turn(
            state=state,
            judge=judge,
            model=model,
            reasoning_effort=reasoning_effort,
            timeout=timeout,
            idle_timeout=idle_timeout,
            heartbeat_interval=heartbeat_interval,
            backend=backend,
            turn=turn,
        )
        final_judge = judge_turn["parsed"]
        state["judge_turns"].append(judge_turn)
        route_to = str(final_judge.get("route_to") or "").strip()
        decision = str(final_judge.get("decision") or "").strip()
        missing_signature = _missing_signature(final_judge)
        if not _judge_has_required_fields(final_judge):
            halt_reason = "invalid_judge_json"
            break
        if route_to in TERMINAL_ROUTES or decision != "NEEDS_CLARIFICATION":
            halt_reason = "judge_terminal_decision"
            break
        if missing_signature in seen_missing:
            halt_reason = "repeated_missing_evidence"
            break
        seen_missing.add(missing_signature)
        routed_role = REROUTABLE_ROLES.get(route_to)
        if not routed_role:
            halt_reason = "unsupported_route"
            break
        if round_number >= max_rounds:
            halt_reason = "max_rounds"
            break
        routed_participant = _participant_for_role(participants, routed_role)
        routed_turn = _run_rerouted_reviewer(
            state=state,
            participant=routed_participant,
            judge_result=final_judge,
            model=model,
            reasoning_effort=reasoning_effort,
            timeout=timeout,
            idle_timeout=idle_timeout,
            heartbeat_interval=heartbeat_interval,
            backend=backend,
            turn=turn,
        )
        role_outputs[routed_role] = routed_turn
        state["reroute_turns"].append(routed_turn)

    state["final_judge"] = final_judge
    state["halt_reason"] = halt_reason
    state["completed_at"] = datetime.now(timezone.utc).isoformat()
    artifacts = _write_cae_artifacts(state, run_state)
    if run_state:
        run_state.step_finished("cae_gap_review", halt_reason=halt_reason, decision=final_judge.get("decision", ""))

    return {
        "review_id": review_id,
        "mode": CAE_MODE,
        "advisory_only": True,
        "reviewers": participants,
        "judge": judge,
        "max_rounds": max_rounds,
        "rounds_completed": len(state["judge_turns"]),
        "halt_reason": halt_reason,
        "final_judge": final_judge,
        "gap_review_contract": _gap_review_contract(final_judge, state),
        "role_outputs": role_outputs,
        "reroute_turns": state["reroute_turns"],
        "dogpile_mode": dogpile_mode,
        "artifacts": artifacts,
        "answer": format_cae_gap_review_answer(state),
    }


def run_cae_model_turn(
    *,
    prompt: str,
    persona: str,
    turn_number: int,
    model: str,
    reasoning_effort: str,
    timeout: float,
    idle_timeout: float,
    heartbeat_interval: float,
    backend: str,
) -> tuple[str, str, str | None]:
    """Execute one CAE turn through the existing oracle turn adapter."""
    return _run_protocol_turn(
        prompt=prompt,
        persona=persona,
        turn_number=turn_number,
        model=model,
        reasoning_effort=reasoning_effort,
        timeout=timeout,
        idle_timeout=idle_timeout,
        heartbeat_interval=heartbeat_interval,
        backend=backend,
    )


def format_cae_gap_review_answer(state: dict[str, Any]) -> str:
    judge = state.get("final_judge") or {}
    decision = str(judge.get("decision") or "INSUFFICIENT_EVIDENCE")
    status = str(judge.get("final_status") or "INSUFFICIENT_EVIDENCE")
    summary = str(judge.get("decision_summary") or "The CAE gap review did not produce a complete judge summary.")
    route = str(judge.get("route_to") or "human_reviewer")
    missing = judge.get("missing_evidence") if isinstance(judge.get("missing_evidence"), list) else []
    missing_lines = "\n".join(
        f"- {item.get('missing_evidence_type', 'evidence')}: {item.get('description', '')}"
        for item in missing
        if isinstance(item, dict)
    ) or "- None reported by the judge."
    return (
        "## CAE Gap Review\n\n"
        f"- Decision: {decision}\n"
        f"- Final status: {status}\n"
        f"- Route: {route}\n"
        f"- Halt reason: {state.get('halt_reason', 'unknown')}\n"
        f"- Judge rounds: {len(state.get('judge_turns', []))}/{state.get('max_rounds', 1)}\n\n"
        f"{summary}\n\n"
        "### Missing Evidence\n"
        f"{missing_lines}\n\n"
        "This is an analyst workbench result from retrieved evidence only. It is not an approval, "
        "certification, attestation, audit opinion, or assurance outcome."
    )


def _run_initial_reviewers(
    *,
    state: dict[str, Any],
    participants: list[dict[str, str]],
    model: str,
    reasoning_effort: str,
    timeout: float,
    idle_timeout: float,
    heartbeat_interval: float,
    backend: str,
    turn: ModelTurn,
) -> dict[str, dict[str, Any]]:
    outputs: dict[str, dict[str, Any]] = {}

    def run_one(index: int, participant: dict[str, str]) -> dict[str, Any]:
        prompt = _build_reviewer_prompt(state=state, participant=participant, reroute=False)
        try:
            content, served, artifact_dir = turn(
                prompt=prompt,
                persona=participant["persona"],
                turn_number=index + 1,
                model=model,
                reasoning_effort=reasoning_effort,
                timeout=timeout,
                idle_timeout=idle_timeout,
                heartbeat_interval=heartbeat_interval,
                backend=backend,
            )
        except Exception as exc:
            content = json.dumps({
                "parse_ok": False,
                "error": f"{type(exc).__name__}: {exc}",
                "evidence_limits": ["reviewer_turn_failed"],
                "final_status": "INSUFFICIENT_EVIDENCE",
            })
            served = model
            artifact_dir = None
        return _turn_record(
            participant=participant,
            content=content,
            model=served,
            artifact_dir=artifact_dir,
            turn_number=index + 1,
            phase="initial",
        )

    with ThreadPoolExecutor(max_workers=max(1, len(participants))) as executor:
        futures = {executor.submit(run_one, index, participant): participant for index, participant in enumerate(participants)}
        for future in as_completed(futures):
            record = future.result()
            outputs[str(record["role"])] = record
    return outputs


def _run_judge_turn(
    *,
    state: dict[str, Any],
    judge: str,
    model: str,
    reasoning_effort: str,
    timeout: float,
    idle_timeout: float,
    heartbeat_interval: float,
    backend: str,
    turn: ModelTurn,
) -> dict[str, Any]:
    prompt = _build_judge_prompt(state)
    try:
        content, served, artifact_dir = turn(
            prompt=prompt,
            persona=judge,
            turn_number=100 + int(state.get("round", 1)),
            model=model,
            reasoning_effort=reasoning_effort,
            timeout=timeout,
            idle_timeout=idle_timeout,
            heartbeat_interval=heartbeat_interval,
            backend=backend,
        )
    except Exception as exc:
        content = json.dumps({
            "review_id": state["review_id"],
            "parse_ok": False,
            "error": f"{type(exc).__name__}: {exc}",
            "decision": "INSUFFICIENT_EVIDENCE",
            "decision_summary": "The CAE judge turn failed, so no evidence-backed decision can be made.",
            "cited_basis": [],
            "missing_evidence": [{
                "missing_evidence_type": "citation",
                "description": "Judge model call failed before cited basis could be evaluated.",
                "needed_from": "human_reviewer",
            }],
            "route_to": "human_reviewer",
            "stop_reason": "required_input_missing",
            "final_status": "INSUFFICIENT_EVIDENCE",
        })
        served = model
        artifact_dir = None
    parsed = _parse_json_object(content)
    return {
        "phase": "judge",
        "persona": judge,
        "role": "cae_gap_judge",
        "content": content,
        "parsed": parsed,
        "model": served,
        "artifact_dir": artifact_dir,
        "round": state.get("round", 1),
    }


def _run_rerouted_reviewer(
    *,
    state: dict[str, Any],
    participant: dict[str, str],
    judge_result: dict[str, Any],
    model: str,
    reasoning_effort: str,
    timeout: float,
    idle_timeout: float,
    heartbeat_interval: float,
    backend: str,
    turn: ModelTurn,
) -> dict[str, Any]:
    prompt = _build_reviewer_prompt(
        state=state,
        participant=participant,
        reroute=True,
        missing_evidence=judge_result.get("missing_evidence") if isinstance(judge_result.get("missing_evidence"), list) else [],
    )
    try:
        content, served, artifact_dir = turn(
            prompt=prompt,
            persona=participant["persona"],
            turn_number=200 + int(state.get("round", 1)),
            model=model,
            reasoning_effort=reasoning_effort,
            timeout=timeout,
            idle_timeout=idle_timeout,
            heartbeat_interval=heartbeat_interval,
            backend=backend,
        )
    except Exception as exc:
        content = json.dumps({
            "parse_ok": False,
            "error": f"{type(exc).__name__}: {exc}",
            "evidence_limits": ["rerouted_reviewer_turn_failed"],
            "final_status": "INSUFFICIENT_EVIDENCE",
        })
        served = model
        artifact_dir = None
    return _turn_record(
        participant=participant,
        content=content,
        model=served,
        artifact_dir=artifact_dir,
        turn_number=200 + int(state.get("round", 1)),
        phase="reroute",
    )


def _build_reviewer_prompt(
    *,
    state: dict[str, Any],
    participant: dict[str, str],
    reroute: bool,
    missing_evidence: list[Any] | None = None,
) -> str:
    role_doc = _load_role_doc(participant["role"])
    payload = {
        "review_id": state["review_id"],
        "question": state["question"],
        "scope": state["scope"],
        "evidence_case": state["evidence_case"],
        "constraints": state["constraints"],
        "loop_state": _compact_loop_state(state),
        "missing_evidence_to_address": missing_evidence or [],
    }
    phase = "rerouted follow-up" if reroute else "initial independent review"
    return (
        f"{role_doc}\n\n"
        f"Persona identity: {participant['persona']}\n"
        f"Phase: {phase}\n"
        "Access policy: memory and dogpile are context/retrieval aids only; do not treat them as evidence "
        "unless the returned artifact is included in the evidence_case payload with a source id.\n\n"
        "Use only the JSON payload below as evidence. Return JSON only.\n"
        f"{json.dumps(payload, indent=2, sort_keys=True, default=str)[:30000]}"
    )


def _build_judge_prompt(state: dict[str, Any]) -> str:
    role_doc = _load_role_doc("cae_gap_judge")
    payload = {
        "review_id": state["review_id"],
        "question": state["question"],
        "scope": state["scope"],
        "policy_findings": _parsed_for_role(state, "cae_policy_evidence"),
        "enforcement_findings": _parsed_for_role(state, "cae_technical_enforcement"),
        "control_mappings": _parsed_for_role(state, "cae_control_mapping"),
        "role_outputs": state.get("role_outputs", {}),
        "evidence_limits": _collect_evidence_limits(state),
        "constraints": state["constraints"],
        "loop_state": _compact_loop_state(state),
    }
    return (
        f"{role_doc}\n\n"
        "You are the judge for an adaptive CAE gap review. If evidence is missing, route exactly one "
        "missing evidence item to exactly one route_to value. If the same gap repeats, choose a terminal "
        "route instead of looping. Return JSON only.\n\n"
        f"{json.dumps(payload, indent=2, sort_keys=True, default=str)[:30000]}"
    )


def _turn_record(
    *,
    participant: dict[str, str],
    content: str,
    model: str,
    artifact_dir: str | None,
    turn_number: int,
    phase: str,
) -> dict[str, Any]:
    return {
        "phase": phase,
        "persona": participant["persona"],
        "role": participant["role"],
        "turn_number": turn_number,
        "content": content,
        "parsed": _parse_json_object(content),
        "model": model,
        "artifact_dir": artifact_dir,
    }


def _initial_loop_state(
    *,
    review_id: str,
    question: str,
    scope: str,
    evidence_case: dict[str, Any],
    participants: list[dict[str, str]],
    judge: str,
    max_rounds: int,
    dogpile_mode: str,
) -> dict[str, Any]:
    return {
        "review_id": review_id,
        "question": question,
        "scope": scope,
        "evidence_case": evidence_case,
        "participants": participants,
        "judge": judge,
        "max_rounds": max_rounds,
        "dogpile_mode": dogpile_mode,
        "constraints": [
            "Use retrieved evidence only.",
            "Do not issue compliance approval, certification, attestation, audit opinion, or assurance outcome.",
            "Route only unresolved missing evidence; do not loop on resolved findings.",
        ],
        "role_outputs": {},
        "judge_turns": [],
        "reroute_turns": [],
        "round": 1,
        "started_at": datetime.now(timezone.utc).isoformat(),
    }


def _participant_for_role(participants: list[dict[str, str]], role: str) -> dict[str, str]:
    for participant in participants:
        if participant["role"] == role:
            return participant
    return {"persona": role.replace("_", " ").title(), "role": role}


def _parsed_for_role(state: dict[str, Any], role: str) -> dict[str, Any]:
    record = (state.get("role_outputs") or {}).get(role) or {}
    parsed = record.get("parsed")
    return parsed if isinstance(parsed, dict) else {}


def _collect_evidence_limits(state: dict[str, Any]) -> list[str]:
    limits: list[str] = []
    for record in (state.get("role_outputs") or {}).values():
        parsed = record.get("parsed") if isinstance(record, dict) else None
        if not isinstance(parsed, dict):
            continue
        role_limits = parsed.get("evidence_limits")
        if isinstance(role_limits, list):
            limits.extend(str(item) for item in role_limits)
    return limits


def _compact_loop_state(state: dict[str, Any]) -> dict[str, Any]:
    return {
        "round": state.get("round", 1),
        "max_rounds": state.get("max_rounds", 1),
        "previous_judge_decisions": [
            {
                "round": turn.get("round"),
                "decision": (turn.get("parsed") or {}).get("decision"),
                "route_to": (turn.get("parsed") or {}).get("route_to"),
                "missing_evidence": (turn.get("parsed") or {}).get("missing_evidence", []),
            }
            for turn in state.get("judge_turns", [])
            if isinstance(turn, dict)
        ],
        "reroutes_completed": [
            {
                "round": turn.get("turn_number"),
                "persona": turn.get("persona"),
                "role": turn.get("role"),
            }
            for turn in state.get("reroute_turns", [])
            if isinstance(turn, dict)
        ],
    }


def _write_cae_artifacts(state: dict[str, Any], run_state: AskRunState | NoopRunState | None) -> dict[str, str]:
    if not run_state or not hasattr(run_state, "run_dir"):
        return {}
    run_dir = Path(getattr(run_state, "run_dir")) / CAE_MODE
    run_dir.mkdir(parents=True, exist_ok=True)
    json_path = run_dir / "review.json"
    md_path = run_dir / "review.md"
    json_path.write_text(json.dumps(state, indent=2, sort_keys=True, default=str) + "\n")
    md_path.write_text(format_cae_gap_review_answer(state) + "\n")
    artifacts = {"cae_gap_review_json": str(json_path), "cae_gap_review_markdown": str(md_path)}
    run_state.add_artifacts(artifacts)
    return artifacts


def _load_role_doc(role: str) -> str:
    filename = ROLE_DOCS.get(role)
    if not filename:
        return f"You are the {role} prompt-role spec."
    path = Path(__file__).resolve().parents[2] / "docs" / "reviewers" / filename
    return path.read_text() if path.exists() else f"You are the {role} prompt-role spec."


def _parse_json_object(content: str) -> dict[str, Any]:
    text = content.strip()
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        try:
            parsed = json.loads(text[start:end + 1])
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass
    return {"parse_ok": False, "raw_content": content}


def _judge_has_required_fields(judge: dict[str, Any]) -> bool:
    return VALID_JUDGE_KEYS.issubset(judge.keys())


def _gap_review_contract(judge: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
    missing = judge.get("missing_evidence")
    if not isinstance(missing, list):
        missing = []
    correction = judge.get("qra_correction_recommendation")
    if not isinstance(correction, dict):
        correction = {
            "status": "not_proposed",
            "requires_new_evidence_case": True,
        }
    return {
        "advisory_only": True,
        "final_status": str(judge.get("final_status") or "INSUFFICIENT_EVIDENCE"),
        "missing_evidence": missing,
        "qra_correction_recommendation": correction,
        "route_to_persona": _route_to_persona(str(judge.get("route_to") or ""), state.get("participants") or []),
        "source_artifact_requirements": SOURCE_ARTIFACT_REQUIREMENTS,
    }


def _route_to_persona(route_to: str, participants: list[dict[str, str]]) -> str:
    if route_to in {"human_reviewer", "additional_retrieval", "stop"}:
        return route_to
    role = REROUTABLE_ROLES.get(route_to)
    if not role:
        return "human_reviewer"
    for participant in participants:
        if participant.get("role") == role:
            return str(participant.get("persona") or role)
    return role


def _missing_signature(judge: dict[str, Any]) -> str:
    missing = judge.get("missing_evidence")
    if not isinstance(missing, list):
        return ""
    return json.dumps(missing, sort_keys=True, default=str)


def _case_identifier(evidence_case: dict[str, Any]) -> str:
    claim = evidence_case.get("claim")
    if isinstance(claim, dict):
        for key in ("id", "claim_id", "text"):
            value = claim.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    for key in ("review_id", "case_id", "id"):
        value = evidence_case.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""
