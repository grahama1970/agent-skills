"""Memory tracking for classifier-lab self-improvement loop.

Stores every /dogpile call and every training round to /memory (ArangoDB)
and local .artifacts/ for cross-session recall and trajectory analysis.

NON-NEGOTIABLE: Every round and every dogpile MUST be tracked.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import TYPE_CHECKING

from loguru import logger

if TYPE_CHECKING:
    from e2e_pipeline import PipelineState, RoundResult

SKILL_DIR = Path(__file__).resolve().parent.parent
ARTIFACTS_DIR = SKILL_DIR / ".artifacts"
SKILLS_DIR = SKILL_DIR.parent


def run_skill(skill: str, args: str, timeout: int = 300) -> tuple[int, str, str]:
    """Run a skill's run.sh with args."""
    import os
    import subprocess
    skill_dir = SKILLS_DIR / skill
    cmd = f"cd {skill_dir} && ./run.sh {args}"
    proc = subprocess.run(
        ["bash", "-lc", cmd],
        capture_output=True, text=True, timeout=timeout, check=False,
        env={**os.environ, "VIRTUAL_ENV": "", "PYTORCH_ALLOC_CONF": "expandable_segments:True"},
    )
    return proc.returncode, proc.stdout, proc.stderr


def notify_ux(msg_type: str, payload: dict) -> None:
    """Send message to UX Lab WebSocket (best-effort)."""
    try:
        import httpx
        httpx.post("http://localhost:3001/api/agent-bus", json={"type": msg_type, "payload": payload}, timeout=2)
    except Exception:
        pass


def store_round_artifact(state: PipelineState, result: RoundResult, gate_threshold: float) -> None:
    """Store round result as artifact + /memory learn."""
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    artifact = {
        "event_type": "self_improvement_round",
        "timestamp": int(time.time()),
        "project_id": state.project_id,
        "task": state.task,
        "round": result.round_num,
        "strategy": result.strategy,
        "backbone": result.backbone,
        "modality": result.modality,
        "f1": result.f1,
        "accuracy": result.accuracy,
        "wilson_lower": result.wilson_lower,
        "diagnosis": result.diagnosis,
        "dogpile_query": result.dogpile_query,
        "hps": result.hps,
        "errors": result.errors,
    }
    artifact_path = ARTIFACTS_DIR / f"round_{state.project_id}_{result.round_num}_{int(time.time())}.json"
    artifact_path.write_text(json.dumps(artifact, indent=2))

    # Store to /memory for cross-session recall — full trajectory tracking
    problem = (
        f"SELF-IMPROVE:{state.project_id}:round{result.round_num} — "
        f"{state.task} | strategy={result.strategy} | F1={result.f1:.3f} | gate={'PASS' if result.f1 >= gate_threshold else 'FAIL'}"
    )
    solution = json.dumps({
        "project_id": state.project_id,
        "task": state.task,
        "round": result.round_num,
        "strategy": result.strategy,
        "backbone": result.backbone,
        "modality": result.modality,
        "f1": result.f1,
        "accuracy": result.accuracy,
        "wilson_lower": result.wilson_lower,
        "gate_threshold": gate_threshold,
        "gate_passed": result.f1 >= gate_threshold,
        "diagnosis": result.diagnosis,
        "hps": result.hps,
        "previous_rounds": [{"round": r.round_num, "strategy": r.strategy, "f1": r.f1} for r in state.rounds[:-1]],
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    })
    run_skill(
        "memory",
        f'learn --problem "{problem}" --solution \'{solution}\' '
        f'--scope classifier-lab --tag self-improvement --tag {state.project_id} --tag round-{result.round_num}',
        timeout=15,
    )


def store_dogpile_to_memory(state: PipelineState, query: str, result: str, round_num: int, phase: str) -> None:
    """NON-NEGOTIABLE: Store every /dogpile call to /memory for tracking."""
    problem = (
        f"DOGPILE:{state.project_id}:round{round_num}:{phase} — "
        f"Classifier Lab dogpile for {state.task}"
    )
    solution = json.dumps({
        "project_id": state.project_id,
        "task": state.task,
        "round": round_num,
        "phase": phase,
        "modality": state.modality,
        "query": query,
        "result_preview": (result or "")[:1500],
        "result_length": len(result or ""),
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "current_f1": state.winner_f1,
        "strategies_tried": [r.strategy for r in state.rounds],
    })
    run_skill(
        "memory",
        f'learn --problem "{problem}" --solution \'{solution}\' '
        f'--scope classifier-lab --tag dogpile-tracking --tag {state.project_id} --tag self-improvement',
        timeout=15,
    )
    logger.info(f"Stored dogpile to /memory: project={state.project_id} round={round_num} phase={phase}")

    # Also store artifact for local tracking
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    artifact_path = ARTIFACTS_DIR / f"dogpile_{state.project_id}_r{round_num}_{int(time.time())}.json"
    artifact_path.write_text(json.dumps({
        "event_type": "dogpile_research",
        "project_id": state.project_id,
        "task": state.task,
        "round": round_num,
        "phase": phase,
        "query": query,
        "result_length": len(result or ""),
        "timestamp": int(time.time()),
    }, indent=2))


def generate_next_steps(
    state: "PipelineState",
    gate_threshold: float,
    detect_plateau_fn: "Any",
    diagnose_fn: "Any",
) -> None:
    """Generate /dogpile-backed next-steps hypothesis after all rounds exhausted.

    Writes next-steps.json to both the project dir and .artifacts/ so the UX
    can display actionable recommendations instead of just 'GATE NOT MET'.
    """
    diagnosis = diagnose_fn(state)

    trajectory = ""
    for r in state.rounds:
        trajectory += (
            f"  Round {r.round_num}: strategy={r.strategy} backbone={r.backbone} "
            f"modality={r.modality} F1={r.f1:.3f} diagnosis={r.diagnosis}\n"
        )

    gap = gate_threshold - state.winner_f1
    dogpile_query = (
        f"Classifier training FAILED after {len(state.rounds)} rounds.\n"
        f"Task: {state.task} | Modality: {state.modality}\n"
        f"Best: {state.winner} F1={state.winner_f1:.3f} (need {gate_threshold}, gap={gap:.3f})\n"
        f"Data: {state.data_audit.get('total_samples', '?')} samples, "
        f"{state.data_audit.get('n_classes', '?')} classes, "
        f"min/class={state.data_audit.get('min_per_class', '?')}\n"
        f"Full trajectory:\n{trajectory}\n"
        f"Plateau detected: {detect_plateau_fn(state.rounds)}\n\n"
        f"Generate 3-5 SPECIFIC next-step hypotheses to close the F1 gap of {gap:.3f}. "
        f"For each hypothesis: (1) what to try, (2) why it should help, (3) expected F1 lift. "
        f"Consider: larger models, data augmentation, curriculum learning, focal loss, "
        f"knowledge distillation, cross-validation, label noise detection, contrastive pretraining."
    )

    logger.info(f"Generating next-steps via /dogpile ({len(dogpile_query)} chars)")
    rc, out, err = run_skill("dogpile", f'search "{dogpile_query}"', timeout=300)

    dogpile_text = out.strip() if rc == 0 and out.strip() else ""
    if not dogpile_text:
        logger.warning(f"/dogpile failed or empty (rc={rc}): {err[:200]}")

    next_steps = {
        "project_id": state.project_id,
        "task": state.task,
        "modality": state.modality,
        "best_backbone": state.winner,
        "best_f1": state.winner_f1,
        "gate_threshold": gate_threshold,
        "gap": round(gap, 4),
        "total_rounds": len(state.rounds),
        "plateau_detected": detect_plateau_fn(state.rounds),
        "diagnosis": diagnosis,
        "strategies_exhausted": [r.strategy for r in state.rounds],
        "dogpile_query": dogpile_query,
        "dogpile_hypotheses": dogpile_text,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }

    # Write to project dir
    proj_dir = SKILLS_DIR / "create-classifier" / "projects" / state.project_id
    if proj_dir.exists():
        next_steps_path = proj_dir / "next-steps.json"
        next_steps_path.write_text(json.dumps(next_steps, indent=2))
        logger.info(f"Next-steps written: {next_steps_path}")

    # Also write to .artifacts for failure-analysis endpoint
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    artifact_path = ARTIFACTS_DIR / f"next_steps_{state.project_id}_{int(time.time())}.json"
    artifact_path.write_text(json.dumps({**next_steps, "event_type": "next_steps"}, indent=2))

    # Store to /memory for cross-session recall
    problem = f"NEXT-STEPS:{state.project_id} — {state.task} failed gate F1={state.winner_f1:.3f}<{gate_threshold}"
    run_skill(
        "memory",
        f'learn --problem "{problem}" --solution \'{json.dumps(next_steps)}\' '
        f'--scope classifier-lab --tag next-steps --tag {state.project_id}',
        timeout=15,
    )

    # Notify UX
    notify_ux("training-update", {
        "projectId": state.project_id,
        "phase": "next-steps",
        "nextSteps": next_steps,
    })
