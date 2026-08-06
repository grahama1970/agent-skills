"""Compile ask.project_plan.v1 into tau.generic_dag_spec.v1 (agent-skills#1220).

This is the /ask → Tau handoff seam. /ask owns the plan (intent, roles,
dependencies, acceptance); Tau owns execution. Each workstream becomes one
``tau_agent`` node targeting the ``tau_native_agent_loop`` adapter shipped by
tau#310, with the model expressed as a ``profile:<id>`` SciLLM transport
profile reference (scillm#27/28) — /ask never selects providers itself.

Deterministic: no I/O, no model calls, stable node ordering, and a canonical
sha256 of the emitted spec so the plan → DAG freeze is reproducible.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from ask.project_plan import DEFAULT_HARNESS_MODE, validate_project_plan

TAU_SPEC_SCHEMA = "tau.generic_dag_spec.v1"

# Role → SciLLM transport profile id, per named team preset. Profiles are the
# scillm#27 contract ids; Tau performs authoritative eligibility/selection.
TEAM_PRESETS: dict[str, dict[str, str]] = {
    "fullstack-premium": {
        "coordinator": "claude-fable-model-turn",
        "backend": "claude-model-turn",
        "frontend": "claude-model-turn",
        "documentation": "codex-model-turn",
        "testing": "codex-model-turn",
        "independent_reviewer": "codex-model-turn",
    },
    "economical": {
        "coordinator": "codex-model-turn",
        "backend": "codex-model-turn",
        "frontend": "codex-model-turn",
        "documentation": "codex-model-turn",
        "testing": "codex-model-turn",
        "independent_reviewer": "claude-model-turn",
    },
}


# Provider family per profile id — POLICY MIRROR of the scillm registry's
# provider field, used only for the independent-review invariant below.
# test_provider_map_matches_live_registry guards drift; scillm#33 will let
# this resolve from the registry's strengths/provider fields directly.
PROFILE_PROVIDER_FAMILY: dict[str, str] = {
    "claude-fable-model-turn": "anthropic",
    "claude-model-turn": "anthropic",
    "codex-model-turn": "openai",
    "gemini-vlm": "google",
    "local-text": "ollama",
    "opencode-serve-compat": "opencode",
}

# Roles whose output is code; the reviewer must come from a different
# provider family than ALL of these (a provider never reviews its own code).
CODE_ROLES = frozenset({"backend", "frontend", "testing"})


def enforce_independent_review(profiles: dict[str, str], workstream_roles: list[str]) -> dict[str, str]:
    """Reviewer provider must differ from every code-writing provider.

    Deterministic reassignment per operator policy: if the current reviewer
    shares a provider family with any code role, swap to codex-model-turn
    (GPT 5.5) when OpenAI wrote no code, else to claude-fable-model-turn
    (Fable) when Anthropic wrote no code. If every candidate family also
    wrote code, fail closed — independent review needs a third provider.
    """
    if "independent_reviewer" not in workstream_roles:
        return profiles
    code_families = {
        PROFILE_PROVIDER_FAMILY.get(profiles[r], "unknown")
        for r in workstream_roles
        if r in CODE_ROLES
    }
    if not code_families:
        return profiles
    reviewer_profile = profiles["independent_reviewer"]
    if PROFILE_PROVIDER_FAMILY.get(reviewer_profile, "unknown") not in code_families:
        return profiles
    for candidate in ("codex-model-turn", "claude-fable-model-turn"):
        if PROFILE_PROVIDER_FAMILY[candidate] not in code_families:
            return {**profiles, "independent_reviewer": candidate}
    raise ValueError(
        "independent review impossible: every reviewer-capable provider family "
        f"also wrote code ({sorted(code_families)}); add a third-provider profile"
    )


def _canonical_sha256(payload: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def resolve_role_profiles(plan: dict[str, Any]) -> dict[str, str]:
    """Resolve each workstream role to a transport profile id from the team preset."""
    team = plan.get("team") or {}
    preset_name = str(team.get("preset") or "fullstack-premium")
    preset = TEAM_PRESETS.get(preset_name)
    if preset is None:
        raise ValueError(f"unknown team preset {preset_name!r}; known: {sorted(TEAM_PRESETS)}")
    overrides = team.get("role_profiles") or {}
    return {**preset, **{str(k): str(v) for k, v in overrides.items()}}


def compile_plan_to_tau_spec(
    plan: dict[str, Any],
    *,
    run_id: str,
    run_dir: Path,
) -> dict[str, Any]:
    """Compile a validated plan into a frozen tau.generic_dag_spec.v1 payload.

    Returns the spec with a ``spec_sha256`` freeze stamp computed over the
    node payload (excluding the stamp itself). Raises ValueError on an
    invalid plan — compilation never silently repairs proposal data.
    """
    ok, errors = validate_project_plan(plan)
    if not ok:
        raise ValueError(f"invalid ask.project_plan.v1: {errors}")

    profiles = resolve_role_profiles(plan)
    profiles = enforce_independent_review(
        profiles, [str(ws["role"]) for ws in plan["workstreams"]]
    )
    goal = str(plan["goal"])
    receipts_dir = run_dir / "receipts"
    nodes: list[dict[str, Any]] = []
    for ws in plan["workstreams"]:
        role = str(ws["role"])
        mode = str(ws.get("harness_mode", DEFAULT_HARNESS_MODE))
        deps = [str(d) for d in (ws.get("depends_on") or [])]
        profile = profiles[role]
        prompt = str(ws.get("prompt") or "").strip() or (
            f"You are the {role} agent for this goal: {goal}. "
            f"Deliver your workstream ({ws['id']}) and state exactly what you produced."
        )
        nodes.append(
            {
                "node_id": str(ws["id"]),
                "role": role,
                "tau_agent": {
                    "prompt": prompt,
                    "role": role,
                    "model": f"profile:{profile}",
                    "allowed_paths": [str(p) for p in (ws.get("allowed_paths") or [])],
                    "required_evidence": ["tool_effect_receipt"]
                    if ws.get("allowed_paths")
                    else [],
                    "harness_mode": mode,
                },
                "depends_on": deps,
                "accepted_context_from": deps,
                "receipt_path": str(receipts_dir / f"{ws['id']}.json"),
                "timeout_seconds": int(ws.get("timeout_seconds") or 300),
                "max_attempts": int(plan.get("execution", {}).get("max_retries", 0)) + 1,
            }
        )

    spec: dict[str, Any] = {
        "schema": TAU_SPEC_SCHEMA,
        "run_id": run_id,
        "run_dir": str(run_dir / "run"),
        "nodes": nodes,
    }
    spec["extensions"] = {"source_plan": {
        "schema": plan.get("schema"),
        "goal": goal,
        "goal_hash": _canonical_sha256({"goal": goal, "target": plan.get("target")}),
        "team_preset": str((plan.get("team") or {}).get("preset") or "fullstack-premium"),
        "role_profiles": {ws["id"]: profiles[str(ws["role"])] for ws in plan["workstreams"]},
    }}
    spec["extensions"]["spec_sha256"] = _canonical_sha256(
        {k: v for k, v in spec.items() if k != "extensions"} | {"source_plan": spec["extensions"]["source_plan"]}
    )
    return spec


def heterogeneous_profile_count(spec: dict[str, Any]) -> int:
    """Distinct transport profiles across nodes — the #1220 canary needs >= 2."""
    return len(
        {
            str(node["tau_agent"]["model"])
            for node in spec.get("nodes", [])
            if isinstance(node.get("tau_agent"), dict)
        }
    )
