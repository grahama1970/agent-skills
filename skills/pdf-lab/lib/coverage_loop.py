"""PDF Lab Coverage plan-loop artifact.

The Coverage page is a control loop, not a passive report. This module turns
artifact-derived status-report JSON into a machine-readable next-action record
that prevents blind repeated replanning.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

NextAction = Literal["complete", "new_plan", "amend_plan", "stop_interview", "stop_dogpile"]

TECHNICAL_AREAS = {
    "Artifacts",
    "Parity Audit",
    "Evidence QA",
    "TOC Audit",
    "Memory / Qdrant Final QA",
    "Agent Second Pass",
}
PRODUCT_AREAS = {
    "Human Triage",
}


@dataclass(frozen=True)
class CoverageLoopConfig:
    status_report_path: Path
    project_knowledge_path: Path
    active_plan_path: Path | None
    output_path: Path
    history_path: Path | None = None


def read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise TypeError(f"{path} must contain a JSON object")
    return data


def _canonical_blockers(blockers: Any) -> list[dict[str, str]]:
    if not isinstance(blockers, list):
        return []
    canonical: list[dict[str, str]] = []
    for blocker in blockers:
        if not isinstance(blocker, dict):
            continue
        canonical.append({
            "area": str(blocker.get("area", "")),
            "severity": str(blocker.get("severity", "")),
            "detail": str(blocker.get("detail", "")),
            "next_action": str(blocker.get("next_action", "")),
        })
    canonical.sort(key=lambda item: (item["area"], item["severity"], item["detail"], item["next_action"]))
    return canonical


def blocker_signature(blockers: Any) -> str:
    canonical = _canonical_blockers(blockers)
    payload = json.dumps(canonical, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def _project_knowledge_policy(project_knowledge_path: Path) -> dict[str, Any]:
    text = project_knowledge_path.read_text(encoding="utf-8")
    required = [
        "Coverage is not a passive status dump",
        "Persistent Coverage blocker triggers interview or dogpile",
    ]
    missing = [phrase for phrase in required if phrase not in text]
    return {
        "project_knowledge_checked": not missing,
        "missing_policy_phrases": missing,
    }


def _load_history(path: Path | None) -> list[dict[str, Any]]:
    if path is None or not path.exists():
        return []
    entries: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict):
            entries.append(data)
    return entries


def _same_blocker_streak(history: list[dict[str, Any]], signature: str) -> int:
    streak = 1
    for entry in reversed(history):
        if entry.get("blocker_signature") == signature:
            streak += 1
        else:
            break
    return streak


def _dominant_area(blockers: list[dict[str, str]]) -> str:
    if not blockers:
        return ""
    severity_rank = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    return sorted(blockers, key=lambda b: (severity_rank.get(b.get("severity", "low"), 9), b.get("area", "")))[0].get("area", "")


def _stop_action_for_area(area: str) -> NextAction:
    if area in PRODUCT_AREAS:
        return "stop_interview"
    return "stop_dogpile"


def _recommended_command(next_action: NextAction, active_plan_path: Path | None, area: str) -> str:
    if next_action == "complete":
        return "No repair command required; maintain artifact freshness and continue final QA sampling."
    if next_action == "stop_interview":
        return f"/interview --topic 'PDF Lab Coverage blocker: {area}'"
    if next_action == "stop_dogpile":
        return f"/dogpile --topic 'PDF Lab Coverage technical blocker: {area}'"
    if active_plan_path:
        return f"/home/graham/workspace/experiments/agent-skills/skills/orchestrate/run.sh run {active_plan_path}"
    return "Create a project-knowledge-checked orchestration plan for the active Coverage blocker, then run /orchestrate."


def _rationale(next_action: NextAction, blockers: list[dict[str, str]], streak: int, area: str) -> str:
    if next_action == "complete":
        return "Coverage currently has no artifact-derived blockers."
    detail = blockers[0].get("detail", "") if blockers else "unknown blocker"
    if next_action in {"stop_interview", "stop_dogpile"}:
        target = "/interview" if next_action == "stop_interview" else "/dogpile"
        return f"The same blocker signature has persisted for {streak} Coverage iterations. Stop automatic replanning and use {target} before generating another plan. Active area: {area}. Detail: {detail}"
    return f"Coverage has an active blocker and can continue with a project-knowledge-checked plan. Active area: {area}. Detail: {detail}"


def build_coverage_loop(config: CoverageLoopConfig, *, append_history: bool = True) -> dict[str, Any]:
    status_report = read_json(config.status_report_path)
    blockers = _canonical_blockers(status_report.get("blockers", []))
    signature = blocker_signature(blockers)
    history_path = config.history_path or config.output_path.with_name("pdf-lab-coverage-loop-history.jsonl")
    history = _load_history(history_path)
    streak = _same_blocker_streak(history, signature) if blockers else 0
    area = _dominant_area(blockers)

    if not blockers:
        next_action: NextAction = "complete"
    elif streak >= 2:
        next_action = _stop_action_for_area(area)
    elif config.active_plan_path:
        next_action = "amend_plan"
    else:
        next_action = "new_plan"

    policy = _project_knowledge_policy(config.project_knowledge_path)
    now = datetime.now(timezone.utc).isoformat()
    artifact = {
        "schema_version": "pdf_lab_coverage_loop.v1",
        "generated_at": now,
        "status_report_path": str(config.status_report_path),
        "project_knowledge_path": str(config.project_knowledge_path),
        "project_knowledge_checked": policy["project_knowledge_checked"],
        "project_knowledge_missing_policy_phrases": policy["missing_policy_phrases"],
        "memory_recall_required": True,
        "active_plan_path": str(config.active_plan_path) if config.active_plan_path else None,
        "active_blocker": blockers[0] if blockers else None,
        "blocker_count": len(blockers),
        "blockers": blockers,
        "blocker_signature": signature,
        "same_blocker_streak": streak,
        "next_action": next_action,
        "recommended_command": _recommended_command(next_action, config.active_plan_path, area),
        "rationale": _rationale(next_action, blockers, streak, area),
        "loop_safe_to_continue": next_action in {"new_plan", "amend_plan"},
        "must_stop_for_interview": next_action == "stop_interview",
        "must_stop_for_dogpile": next_action == "stop_dogpile",
        "status_summary": status_report.get("summary", {}),
    }

    config.output_path.parent.mkdir(parents=True, exist_ok=True)
    config.output_path.write_text(json.dumps(artifact, indent=2, sort_keys=True), encoding="utf-8")

    if append_history:
        history_path.parent.mkdir(parents=True, exist_ok=True)
        with history_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps({
                "generated_at": now,
                "blocker_signature": signature,
                "blocker_count": len(blockers),
                "active_blocker_area": area,
                "next_action": next_action,
            }, sort_keys=True) + "\n")

    return artifact
