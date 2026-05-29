"""Configurable DAG repair policy and timeout profiles for /ask."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable

import yaml

from .skills_exec import SKILLS_DIR


ASK_SKILL_DIR = Path(__file__).resolve().parents[2]
CONFIG_DIR = ASK_SKILL_DIR / "config"
REPAIR_POLICY_PATH = CONFIG_DIR / "ask_dag_repair_policy.yaml"
TIMEOUT_PROFILES_PATH = CONFIG_DIR / "ask_dag_timeout_profiles.yaml"


def _read_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError):
        return {}
    return payload if isinstance(payload, dict) else {}


@lru_cache(maxsize=1)
def load_timeout_profiles() -> dict[str, Any]:
    return _read_yaml(TIMEOUT_PROFILES_PATH)


@lru_cache(maxsize=1)
def load_repair_policy() -> dict[str, Any]:
    policy = _read_yaml(REPAIR_POLICY_PATH)
    repairs = list(policy.get("repairs") or [])
    for skill_dir in sorted(SKILLS_DIR.iterdir()) if SKILLS_DIR.exists() else []:
        hints_path = skill_dir / "config" / "ask_dag_repair_hints.yaml"
        if not hints_path.exists():
            continue
        hints = _read_yaml(hints_path)
        for repair in hints.get("repairs") or []:
            if isinstance(repair, dict):
                repair = {**repair, "skill_hint_source": str(skill_dir.name)}
                repairs.append(repair)
    policy["repairs"] = repairs
    return policy


def resolve_node_timeout(node: dict[str, Any]) -> int:
    """Resolve timeout using explicit node input, then skill/node profiles."""
    node_input = dict(node.get("input") or {})
    explicit = node_input.get("timeout")
    if explicit is not None:
        return int(explicit)
    profiles = load_timeout_profiles()
    defaults = profiles.get("defaults") or {}
    skills = profiles.get("skills") or {}
    node_type = str(node.get("type") or "")
    if node_type in defaults:
        return int(defaults[node_type])
    if node_type == "skill.run":
        skill = str(node_input.get("skill") or "")
        if skill in skills:
            return int(skills[skill])
    return 60


def _match_rule(rule: dict[str, Any], result: dict[str, Any]) -> bool:
    match = rule.get("match") or {}
    if not isinstance(match, dict):
        return False
    if "returncode" in match and result.get("returncode") != match.get("returncode"):
        return False
    if "returncode_not" in match and result.get("returncode") == match.get("returncode_not"):
        return False
    stderr = str(result.get("stderr") or "")
    contains = match.get("stderr_contains")
    if contains and contains not in stderr:
        return False
    return True


def _skill_dir_for_action(action: dict[str, Any], node: dict[str, Any]) -> Path | None:
    skill = str(action.get("skill") or "")
    if not skill and node.get("type") == "dogpile.search":
        skill = "dogpile"
    if not skill and node.get("type") == "skill.run":
        skill = str((node.get("input") or {}).get("skill") or "")
    if not skill:
        return None
    candidate = SKILLS_DIR / skill
    return candidate if candidate.is_dir() else None


def _consume_partial_artifact(
    node: dict[str, Any],
    result: dict[str, Any],
    action: dict[str, Any],
) -> dict[str, Any] | None:
    skill_dir = _skill_dir_for_action(action, node)
    if skill_dir is None:
        return None
    artifact_name = str(action.get("artifact") or "dogpile_partial_results.json")
    artifact_path = skill_dir / artifact_name
    if not artifact_path.exists():
        return None
    try:
        partial = json.loads(artifact_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(partial, dict):
        return None
    min_chars = int(action.get("min_report_chars") or 200)
    report = str(partial.get("final_report") or "").strip()
    if len(report) >= min_chars:
        context_text = report[:12000]
        source = "dogpile_partial_report"
    else:
        results = partial.get("results") or {}
        if not results:
            return None
        context_text = json.dumps(results, indent=2, sort_keys=True, default=str)[:12000]
        source = "dogpile_partial_results"
        if len(context_text.strip()) < min_chars:
            return None
    query = str((node.get("input") or {}).get("query") or (node.get("input") or {}).get("q") or "")
    repaired = {
        **result,
        "ok": True,
        "returncode": 0,
        "partial_recovery": True,
        "partial_artifact_path": str(artifact_path),
        "partial_status": partial.get("status"),
        "payload": {"partial": partial.get("results"), "final_report_excerpt": report[:4000]},
        "stdout_excerpt": context_text[:8000],
        "context_items": [{
            "problem": query,
            "solution": context_text,
            "via": "ask_dag",
            "source": source,
            "dag_node_id": node.get("id"),
            "dag_node_type": node.get("type"),
        }],
    }
    return repaired


def _bump_timeout_node(node: dict[str, Any], action: dict[str, Any]) -> dict[str, Any]:
    node_input = dict(node.get("input") or {})
    original = int(node_input.get("timeout") or resolve_node_timeout(node))
    target = int(action.get("target_seconds") or 360)
    only_if_below = int(action.get("only_if_below") or target)
    if original >= only_if_below:
        return node
    return {**node, "input": {**node_input, "timeout": target}}


def apply_dag_repairs(
    node: dict[str, Any],
    result: dict[str, Any],
    *,
    execute_fn: Callable[..., dict[str, Any]],
    execute_args: tuple[Any, ...],
    execute_kwargs: dict[str, Any],
    run_state: Any | None = None,
) -> dict[str, Any] | None:
    """Apply configured repair actions for a failed DAG node result."""
    if result.get("ok"):
        return None
    policy = load_repair_policy()
    node_type = str(node.get("type") or "")
    repairs = policy.get("repairs") or []
    repair_records: list[dict[str, Any]] = []
    current = result
    current_node = node

    for rule in repairs:
        if node_type not in (rule.get("node_types") or []):
            continue
        if not _match_rule(rule, current):
            continue
        for action in rule.get("actions") or []:
            if not isinstance(action, dict):
                continue
            action_type = str(action.get("type") or "")
            reason = str(action.get("reason") or rule.get("id") or action_type)
            if action_type == "consume_partial_artifact":
                partial = _consume_partial_artifact(current_node, current, action)
                if partial is None:
                    continue
                record = {"reason": reason, "action": action_type, "ok": True}
                repair_records.append(record)
                if run_state is not None:
                    run_state.event(
                        "dag_node_auto_repair_finished",
                        node_id=node.get("id", ""),
                        node_type=node_type,
                        ok=True,
                        repair=record,
                    )
                partial.setdefault("repairs", []).extend(repair_records)
                partial["auto_repaired"] = True
                return partial
            if action_type == "bump_timeout":
                bumped = _bump_timeout_node(current_node, action)
                if bumped is current_node:
                    continue
                if run_state is not None:
                    run_state.event(
                        "dag_node_auto_repair_started",
                        node_id=node.get("id", ""),
                        node_type=node_type,
                        reason=reason,
                        original_timeout_seconds=int((current_node.get("input") or {}).get("timeout") or 0),
                        repaired_timeout_seconds=int((bumped.get("input") or {}).get("timeout") or 0),
                    )
                repaired_args = (bumped, *execute_args[1:]) if execute_args else execute_args
                repaired_kwargs = {**execute_kwargs}
                if not execute_args:
                    repaired_kwargs["node"] = bumped
                current = execute_fn(*repaired_args, **repaired_kwargs)
                record = {
                    "reason": reason,
                    "action": action_type,
                    "original_timeout_seconds": int((node.get("input") or {}).get("timeout") or resolve_node_timeout(node)),
                    "repaired_timeout_seconds": int((bumped.get("input") or {}).get("timeout") or 0),
                    "original_returncode": result.get("returncode"),
                    "ok": bool(current.get("ok")),
                }
                repair_records.append(record)
                current_node = bumped
                if current.get("ok"):
                    current.setdefault("repairs", []).extend(repair_records)
                    current["auto_repaired"] = True
                    if run_state is not None:
                        run_state.event(
                            "dag_node_auto_repair_finished",
                            node_id=node.get("id", ""),
                            node_type=node_type,
                            ok=True,
                            repair=record,
                        )
                    return current
    if repair_records and not current.get("ok"):
        current.setdefault("repairs", []).extend(repair_records)
    return None
