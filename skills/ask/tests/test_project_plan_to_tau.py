"""Deterministic compiler tests: ask.project_plan.v1 → tau.generic_dag_spec.v1 (#1220)."""

from __future__ import annotations

import copy
from pathlib import Path

import pytest

from ask.project_plan import SCHEMA_ID
from ask.project_plan_to_tau import (
    compile_plan_to_tau_spec,
    heterogeneous_profile_count,
    resolve_role_profiles,
)

PLAN = {
    "schema": SCHEMA_ID,
    "goal": "Prove /ask compiles prompts into Tau-native multi-agent DAGs",
    "target": {"repo": "grahama1970/agent-skills"},
    "deliverables": [
        {"name": "canary artifact", "acceptance_criteria": ["reviewer reads back the worker artifact"]},
    ],
    "workstreams": [
        {
            "id": "worker",
            "role": "backend",
            "prompt": "Write the proof artifact.",
            "allowed_paths": ["proof.txt"],
        },
        {
            "id": "reviewer",
            "role": "independent_reviewer",
            "prompt": "Read the proof artifact and give a verdict.",
            "allowed_paths": ["proof.txt"],
            "depends_on": ["worker"],
        },
    ],
    "team": {"preset": "fullstack-premium"},
    "execution": {"topology": "sequential", "max_concurrency": 1, "max_retries": 0},
    "unresolved": [],
}


def _compile(plan: dict, tmp_path: Path) -> dict:
    return compile_plan_to_tau_spec(plan, run_id="test-run", run_dir=tmp_path)


def test_compiles_to_tau_generic_dag_spec(tmp_path: Path) -> None:
    spec = _compile(PLAN, tmp_path)
    assert spec["schema"] == "tau.generic_dag_spec.v1"
    assert [n["node_id"] for n in spec["nodes"]] == ["worker", "reviewer"]
    worker, reviewer = spec["nodes"]
    assert worker["tau_agent"]["model"] == "profile:claude-model-turn"
    assert reviewer["tau_agent"]["model"] == "profile:codex-model-turn"
    assert reviewer["depends_on"] == ["worker"]
    assert reviewer["accepted_context_from"] == ["worker"]
    assert worker["tau_agent"]["harness_mode"] == "tau_native_agent_loop"


def test_canary_shape_is_heterogeneous(tmp_path: Path) -> None:
    spec = _compile(PLAN, tmp_path)
    assert heterogeneous_profile_count(spec) >= 2


def test_freeze_stamp_is_deterministic(tmp_path: Path) -> None:
    a = _compile(PLAN, tmp_path)
    b = _compile(copy.deepcopy(PLAN), tmp_path)
    assert a["extensions"]["spec_sha256"] == b["extensions"]["spec_sha256"]


def test_invalid_plan_refused(tmp_path: Path) -> None:
    bad = copy.deepcopy(PLAN)
    bad["goal"] = ""
    with pytest.raises(ValueError, match="invalid ask.project_plan.v1"):
        _compile(bad, tmp_path)


def test_unknown_preset_refused(tmp_path: Path) -> None:
    bad = copy.deepcopy(PLAN)
    bad["team"] = {"preset": "imaginary"}
    with pytest.raises(ValueError, match="unknown team preset"):
        resolve_role_profiles(bad)


def test_role_override_wins(tmp_path: Path) -> None:
    plan = copy.deepcopy(PLAN)
    plan["team"] = {"preset": "fullstack-premium", "role_profiles": {"backend": "codex-model-turn"}}
    spec = _compile(plan, tmp_path)
    assert spec["nodes"][0]["tau_agent"]["model"] == "profile:codex-model-turn"


def test_evidence_required_only_with_paths(tmp_path: Path) -> None:
    plan = copy.deepcopy(PLAN)
    plan["workstreams"][1].pop("allowed_paths")
    spec = _compile(plan, tmp_path)
    assert spec["nodes"][0]["tau_agent"]["required_evidence"] == ["tool_effect_receipt"]
    assert spec["nodes"][1]["tau_agent"]["required_evidence"] == []
