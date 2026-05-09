"""Deterministic goal-closure checks for /plan.

Inputs are a structured plan YAML file and /orchestrate session artifacts.
Outputs are schema-versioned JSON closure artifacts and, when needed, an
interview request artifact. The module does not call an LLM.
"""

from __future__ import annotations

import json
import os
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

import yaml

import sys

sys.path.append(str(Path(__file__).resolve().parents[3]))
from _shared.structured_plan import load_structured_plan  # type: ignore  # noqa: E402

SKILLS_DIR = Path(__file__).resolve().parents[3]
GOAL_CLOSURE_OUTCOMES = {
    "goal_achieved",
    "partially_achieved",
    "blocked",
    "wrong_plan",
    "insufficient_evidence",
}
GOAL_CLOSURE_ACTIONS = {
    "none",
    "create_followup_plan",
    "revise_existing_plan",
    "ask_human",
}
PASS_STATUSES = {"passed", "completed"}
FAIL_STATUSES = {"failed", "cancelled"}
BLOCKED_STATUSES = {"blocked", "skipped"}


def session_json(session_dir: Path, name: str) -> dict[str, Any]:
    path = session_dir / name
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError:
        return {}


def plan_task_ids(plan: dict[str, Any]) -> set[str]:
    task_ids: set[str] = set()
    for task in plan.get("tasks") or []:
        if isinstance(task, dict) and not bool(task.get("optional", False)):
            task_id = str(task.get("id") or "").strip()
            if task_id:
                task_ids.add(task_id)
    return task_ids


def status_task_map(status: dict[str, Any]) -> dict[str, dict[str, Any]]:
    task_map: dict[str, dict[str, Any]] = {}
    for task in status.get("tasks") or []:
        if not isinstance(task, dict):
            continue
        task_id = str(task.get("id") or "").strip()
        if task_id:
            task_map[task_id] = task
    return task_map


def task_result_artifacts(session_dir: Path, task_id: str) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for path in sorted(session_dir.glob(f"{task_id}.result.json")):
        try:
            data = json.loads(path.read_text())
        except json.JSONDecodeError:
            continue
        results.append(
            {
                "path": str(path),
                "status": data.get("status") or data.get("result") or "",
                "source_commit": data.get("source_commit") or "",
                "source_dod_passed": bool(data.get("source_dod_passed", False)),
                "source_patch_applied": bool(data.get("source_patch_applied", False)),
                "rounds": data.get("rounds"),
            }
        )
    return results


def blind_eval_artifacts(session_dir: Path, task_id: str) -> list[dict[str, Any]]:
    evals: list[dict[str, Any]] = []
    for path in sorted(session_dir.glob(f"{task_id}.blind-eval.json")):
        try:
            data = json.loads(path.read_text())
        except json.JSONDecodeError:
            continue
        evals.append(
            {
                "path": str(path),
                "passed": bool(data.get("passed", False)),
                "status": data.get("status") or "",
            }
        )
    return evals


def assess_plan_result(plan_file: Path, session_dir: Path, output: Path | None = None) -> dict[str, Any]:
    """Assess whether one /orchestrate session achieved the plan goal."""
    plan = load_structured_plan(plan_file)
    status = session_json(session_dir, "status.json")
    report_path = session_dir / "report.txt"
    task_ids = plan_task_ids(plan)
    status_tasks = status_task_map(status)

    missing_tasks = sorted(task_ids - set(status_tasks))
    passed_tasks: list[str] = []
    failed_tasks: list[str] = []
    blocked_tasks: list[str] = []
    unknown_tasks: list[str] = []
    task_evidence: list[dict[str, Any]] = []

    for task_id in sorted(task_ids):
        task_status = str((status_tasks.get(task_id) or {}).get("status") or "").strip()
        if task_status in PASS_STATUSES:
            passed_tasks.append(task_id)
        elif task_status in FAIL_STATUSES:
            failed_tasks.append(task_id)
        elif task_status in BLOCKED_STATUSES:
            blocked_tasks.append(task_id)
        else:
            unknown_tasks.append(task_id)
        task_evidence.append(
            {
                "task_id": task_id,
                "status": task_status or "missing",
                "failure_code": (status_tasks.get(task_id) or {}).get("failure_code") or "",
                "error": (status_tasks.get(task_id) or {}).get("error") or "",
                "result_artifacts": task_result_artifacts(session_dir, task_id),
                "blind_eval_artifacts": blind_eval_artifacts(session_dir, task_id),
            }
        )

    missing_evidence: list[str] = []
    if not status:
        missing_evidence.append("orchestrate status.json missing or invalid")
    if not report_path.exists():
        missing_evidence.append("orchestrate report.txt missing")
    if missing_tasks:
        missing_evidence.append(f"missing task statuses: {', '.join(missing_tasks)}")
    if unknown_tasks:
        missing_evidence.append(f"unknown task statuses: {', '.join(unknown_tasks)}")

    if not status or missing_tasks or unknown_tasks:
        outcome = "insufficient_evidence"
        action = "ask_human"
    elif failed_tasks:
        outcome = "partially_achieved" if passed_tasks else "blocked"
        action = "create_followup_plan" if passed_tasks else "ask_human"
    elif blocked_tasks:
        outcome = "partially_achieved" if passed_tasks else "blocked"
        action = "revise_existing_plan"
    else:
        outcome = "goal_achieved"
        action = "none"

    payload = {
        "schema_version": "plan-goal-closure.v1",
        "plan_file": str(plan_file),
        "session_dir": str(session_dir),
        "goal": (plan.get("metadata") or {}).get("goal") or "",
        "outcome": outcome,
        "recommended_action": action,
        "counts": {
            "required_tasks": len(task_ids),
            "passed": len(passed_tasks),
            "failed": len(failed_tasks),
            "blocked": len(blocked_tasks),
            "missing": len(missing_tasks),
            "unknown": len(unknown_tasks),
        },
        "passed_tasks": passed_tasks,
        "failed_tasks": failed_tasks,
        "blocked_tasks": blocked_tasks,
        "missing_evidence": missing_evidence,
        "task_evidence": task_evidence,
        "closed_vocab": {
            "outcomes": sorted(GOAL_CLOSURE_OUTCOMES),
            "recommended_actions": sorted(GOAL_CLOSURE_ACTIONS),
        },
    }
    if output:
        output.write_text(json.dumps(payload, indent=2))
    return payload


def run_subprocess(args: list[str], *, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    env = {k: v for k, v in os.environ.items() if k != "VIRTUAL_ENV"}
    return subprocess.run(args, cwd=str(cwd) if cwd else None, capture_output=True, text=True, env=env)


def session_dir_from_orchestrate_stdout(stdout: str) -> Path | None:
    for line in stdout.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        session_dir = event.get("session_dir")
        if event.get("event") == "session_started" and session_dir:
            return Path(str(session_dir))
    return None


def write_followup_stub(plan_file: Path, closure: dict[str, Any], iteration: int) -> Path:
    followup = plan_file.with_name(f"{plan_file.stem}.followup-{iteration}.yaml")
    blocked = closure.get("blocked_tasks") or []
    failed = closure.get("failed_tasks") or []
    data = {
        "version": 1,
        "kind": "orchestrate-plan",
        "metadata": {
            "title": "Follow-up plan required",
            "goal": closure.get("goal") or "Close remaining plan goal",
            "plan_type": "code",
            "source_plan": str(plan_file),
            "closure_outcome": closure.get("outcome"),
            "recommended_action": closure.get("recommended_action"),
            "failed_tasks": failed,
            "blocked_tasks": blocked,
        },
        "questions_blockers": [
            "Review the closure artifact and replace this stub with corrected tasks."
        ],
        "capability_overlap": [
            "Follow-up generated from deterministic /plan goal closure."
        ],
        "lanes": [{"id": "0", "label": "Follow-up"}],
        "tasks": [],
    }
    followup.write_text(yaml.safe_dump(data, sort_keys=False))
    return followup


def write_interview_request(plan_file: Path, closure: dict[str, Any], output: Path | None = None) -> Path:
    request_path = output or plan_file.with_suffix(".interview-request.json")
    request = {
        "title": "Plan Goal Closure Needs Human Decision",
        "context": (
            "The deterministic /plan goal-closure assessment could not safely create "
            "the next executable plan without operator input."
        ),
        "source_plan": str(plan_file),
        "closure_outcome": closure.get("outcome"),
        "recommended_action": closure.get("recommended_action"),
        "questions": [
            {
                "id": "next_action",
                "header": "Next Action",
                "text": "How should /plan proceed after this orchestration result?",
                "options": [
                    {
                        "label": "revise_existing_plan (Recommended)",
                        "description": "Update the current plan using the failure evidence, then revalidate and review-plan.",
                    },
                    {
                        "label": "create_followup_plan",
                        "description": "Create a smaller follow-up plan for only failed or blocked work.",
                    },
                    {
                        "label": "mark_blocked",
                        "description": "Stop the loop and record that the goal is blocked on external input.",
                    },
                    {
                        "label": "abandon",
                        "description": "Stop the loop and do not attempt more automated execution.",
                    },
                ],
                "multi_select": False,
                "recommendation": closure.get("recommended_action") or "revise_existing_plan",
                "reason": "Chosen from the deterministic goal-closure outcome.",
            }
        ],
    }
    request_path.write_text(json.dumps(request, indent=2))
    return request_path


def execute_goal_closure(
    plan_file: Path,
    validate_plan_func: Callable[[Path], dict[str, Any]],
    max_replans: int = 0,
    output: Path | None = None,
) -> dict[str, Any]:
    """Run validate -> review-plan -> orchestrate -> assess-result as an opt-in loop."""
    plan_file = plan_file.resolve()
    final_output = output or plan_file.with_suffix(".goal-closure.json")
    history: list[dict[str, Any]] = []
    current_plan = plan_file
    final_closure: dict[str, Any] = {}

    for iteration in range(max_replans + 1):
        validation = validate_plan_func(current_plan)
        if not validation["valid"]:
            final_closure = {
                "schema_version": "plan-goal-closure.v1",
                "plan_file": str(current_plan),
                "session_dir": "",
                "goal": "",
                "outcome": "wrong_plan",
                "recommended_action": "revise_existing_plan",
                "validation": validation,
                "history": history,
            }
            final_closure["interview_request"] = str(write_interview_request(current_plan, final_closure))
            final_output.write_text(json.dumps(final_closure, indent=2))
            return final_closure

        review_runner = Path(os.environ.get("PLAN_REVIEW_PLAN_RUNNER", str(SKILLS_DIR / "review-plan" / "run.sh")))
        if review_runner.exists():
            review = run_subprocess([str(review_runner), "review", str(current_plan), "--json"])
            if review.returncode != 0:
                final_closure = {
                    "schema_version": "plan-goal-closure.v1",
                    "plan_file": str(current_plan),
                    "session_dir": "",
                    "goal": "",
                    "outcome": "wrong_plan",
                    "recommended_action": "revise_existing_plan",
                    "review_stdout": review.stdout,
                    "review_stderr": review.stderr,
                    "history": history,
                }
                final_closure["interview_request"] = str(write_interview_request(current_plan, final_closure))
                final_output.write_text(json.dumps(final_closure, indent=2))
                return final_closure

        orchestrate_runner = Path(os.environ.get("PLAN_ORCHESTRATE_RUNNER", str(SKILLS_DIR / "orchestrate" / "run.sh")))
        orchestrate = run_subprocess([str(orchestrate_runner), "run", str(current_plan)])
        session_dir = session_dir_from_orchestrate_stdout(orchestrate.stdout)
        if session_dir is None:
            final_closure = {
                "schema_version": "plan-goal-closure.v1",
                "plan_file": str(current_plan),
                "session_dir": "",
                "goal": "",
                "outcome": "insufficient_evidence",
                "recommended_action": "ask_human",
                "orchestrate_returncode": orchestrate.returncode,
                "orchestrate_stdout": orchestrate.stdout[-4000:],
                "orchestrate_stderr": orchestrate.stderr[-4000:],
                "history": history,
            }
            final_closure["interview_request"] = str(write_interview_request(current_plan, final_closure))
            final_output.write_text(json.dumps(final_closure, indent=2))
            return final_closure

        closure = assess_plan_result(current_plan, session_dir)
        closure["iteration"] = iteration
        closure["orchestrate_returncode"] = orchestrate.returncode
        history.append(
            {
                "iteration": iteration,
                "plan_file": str(current_plan),
                "session_dir": str(session_dir),
                "outcome": closure["outcome"],
                "recommended_action": closure["recommended_action"],
                "orchestrate_returncode": orchestrate.returncode,
            }
        )
        final_closure = closure
        if closure["outcome"] == "goal_achieved":
            break
        if iteration >= max_replans:
            break
        current_plan = write_followup_stub(current_plan, closure, iteration + 1)

    final_closure["history"] = history
    if final_closure.get("outcome") != "goal_achieved" and history and history[-1]["iteration"] >= max_replans:
        final_closure["recommended_action"] = "ask_human"
    if final_closure.get("outcome") != "goal_achieved" and final_closure.get("recommended_action") == "ask_human":
        final_closure["interview_request"] = str(write_interview_request(current_plan, final_closure))
    final_output.write_text(json.dumps(final_closure, indent=2))
    return final_closure

