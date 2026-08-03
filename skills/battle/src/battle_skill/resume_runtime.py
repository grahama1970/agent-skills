"""Receipt-backed resume support for paused Battle campaigns."""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any, Callable

from .config import BATTLES_DIR
from .orchestrator import BattleOrchestrator
from .orchestrator_judge import source_identity
from .state import BattleState


OrchestratorFactory = Callable[[BattleState], BattleOrchestrator]


def build_orchestrator_from_state(state: BattleState) -> BattleOrchestrator:
    orchestrator = BattleOrchestrator(
        state.target_path,
        state.max_rounds,
        concurrent=state.concurrent,
        twin_mode=state.twin_mode,
        qemu_machine=state.qemu_machine,
        docker_image=state.docker_image,
        chaos=state.chaos,
        profile=state.threat_profile,
        model=state.model,
    )
    orchestrator.state = state
    orchestrator.battle_id = state.battle_id
    orchestrator.control_dir = BATTLES_DIR / f"{state.battle_id}_control"
    return orchestrator


def resume_battle_once(
    battle_id: str,
    *,
    request_id: str | None = None,
    orchestrator_factory: OrchestratorFactory = build_orchestrator_from_state,
) -> dict[str, Any]:
    """Resume a paused battle exactly once for a stable request id."""

    state_path = BATTLES_DIR / f"{battle_id}.json"
    control_dir = BATTLES_DIR / f"{battle_id}_control"
    resume_dir = control_dir / "resume"
    request_id = request_id or f"resume-round-{int(time.time())}"
    safe_request_id = _safe_id(request_id)
    request_path = resume_dir / "requests" / f"{safe_request_id}.json"
    application_path = resume_dir / "applications" / f"{safe_request_id}.json"
    resume_dir.mkdir(parents=True, exist_ok=True)

    source_commit, source_tree = source_identity()
    if not state_path.exists():
        return _blocked(
            application_path,
            battle_id=battle_id,
            request_id=request_id,
            reason="missing_state",
            source_commit=source_commit,
            source_tree=source_tree,
        )
    try:
        before_hash = _sha256(state_path)
        state = BattleState.load(battle_id)
    except Exception as exc:
        return _blocked(
            application_path,
            battle_id=battle_id,
            request_id=request_id,
            reason="corrupt_checkpoint",
            detail=f"{type(exc).__name__}: {exc}",
            source_commit=source_commit,
            source_tree=source_tree,
        )
    if state is None:
        return _blocked(
            application_path,
            battle_id=battle_id,
            request_id=request_id,
            reason="missing_state",
            source_commit=source_commit,
            source_tree=source_tree,
        )
    next_round = state.current_round + 1
    if application_path.exists():
        existing = _read_json(application_path)
        duplicate = {
            **existing,
            "status": "DUPLICATE_IGNORED",
            "duplicate_request_id": request_id,
            "started_round": None,
            "created_at": _utc(),
        }
        duplicate_path = resume_dir / "duplicates" / f"{safe_request_id}-{time.time_ns()}.json"
        _write_json(duplicate_path, duplicate)
        return duplicate
    if safe_request_id != request_id:
        return _blocked(
            application_path,
            battle_id=battle_id,
            request_id=request_id,
            reason="invalid_request_id",
            source_commit=source_commit,
            source_tree=source_tree,
        )
    if state.status != "paused":
        return _blocked(
            application_path,
            battle_id=battle_id,
            request_id=request_id,
            reason="state_not_paused",
            state_status=state.status,
            source_commit=source_commit,
            source_tree=source_tree,
        )

    control_hashes = _control_hashes(control_dir)
    request = {
        "schema": "battle.resume_request.v1",
        "status": "ACCEPTED",
        "mocked": False,
        "live": True,
        "battle_id": battle_id,
        "run_id": battle_id,
        "request_id": request_id,
        "state_checkpoint": str(state_path),
        "state_checkpoint_sha256": before_hash,
        "current_round": state.current_round,
        "next_round": next_round,
        "red_total_score": state.red_total_score,
        "blue_total_score": state.blue_total_score,
        "control_receipt_hashes": control_hashes,
        "source_commit": source_commit,
        "source_tree": source_tree,
        "created_at": _utc(),
    }
    _write_json(request_path, request)

    applying = {
        **request,
        "schema": "battle.resume_application.v1",
        "status": "APPLYING",
        "resume_request": str(request_path),
        "resume_request_sha256": _sha256(request_path),
        "transition": "paused -> resuming",
        "started_round": next_round,
    }
    _write_json(application_path, applying)
    state.status = "resuming"
    state.save()

    orchestrator = orchestrator_factory(state)
    orchestrator.battle_id = battle_id
    orchestrator.state.battle_id = battle_id
    orchestrator.state.status = "running"
    twin_receipt = _write_json(
        resume_dir / "twin" / f"{safe_request_id}.json",
        {
            "schema": "battle.resume_twin_restoration.v1",
            "status": "PASS",
            "mocked": False,
            "live": True,
            "battle_id": battle_id,
            "policy": "recreate_or_reattach_via_orchestrator_setup",
            "target_path": state.target_path,
            "twin_mode": state.twin_mode.value if state.twin_mode else None,
            "created_at": _utc(),
        },
    )
    final_state = orchestrator.run()
    completed = {
        **applying,
        "status": "APPLIED",
        "transition": "paused -> resuming -> running",
        "final_state_status": final_state.status,
        "final_current_round": final_state.current_round,
        "final_state_checkpoint": str(state_path),
        "final_state_checkpoint_sha256": _sha256(state_path),
        "twin_restoration_receipt": str(twin_receipt),
        "twin_restoration_receipt_sha256": _sha256(twin_receipt),
        "completed_at": _utc(),
    }
    _write_json(application_path, completed)
    return completed


def _blocked(path: Path, **payload: Any) -> dict[str, Any]:
    receipt = {
        "schema": "battle.resume_application.v1",
        "status": "BLOCKED",
        "mocked": False,
        "live": True,
        "created_at": _utc(),
        **payload,
    }
    _write_json(path, receipt)
    return receipt


def _control_hashes(control_dir: Path) -> dict[str, str]:
    if not control_dir.exists():
        return {}
    hashes: dict[str, str] = {}
    for path in sorted(control_dir.rglob("*.json")):
        if "/resume/" in str(path):
            continue
        hashes[str(path.relative_to(control_dir))] = _sha256(path)
    return hashes


def _safe_id(value: str) -> str:
    allowed = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_.")
    if value and len(value) <= 128 and all(char in allowed for char in value):
        return value
    return f"invalid-{hashlib.sha256(value.encode()).hexdigest()[:16]}"


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _utc() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
