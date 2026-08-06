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


def test_reviewer_never_shares_provider_with_code_writers(tmp_path: Path) -> None:
    # fullstack-premium: code on anthropic, reviewer on openai — already independent.
    spec = _compile(PLAN, tmp_path)
    assert spec["nodes"][1]["tau_agent"]["model"] == "profile:codex-model-turn"


def test_reviewer_swaps_when_it_would_review_its_own_provider(tmp_path: Path) -> None:
    import copy

    from ask.project_plan_to_tau import PROFILE_PROVIDER_FAMILY

    plan = copy.deepcopy(PLAN)
    # Put the code on openai; preset reviewer is also openai -> must swap to Fable.
    plan["team"] = {"preset": "fullstack-premium", "role_profiles": {"backend": "codex-model-turn"}}
    spec = _compile(plan, tmp_path)
    worker, reviewer = spec["nodes"]
    assert worker["tau_agent"]["model"] == "profile:codex-model-turn"
    assert reviewer["tau_agent"]["model"] == "profile:claude-fable-model-turn"
    assert (
        PROFILE_PROVIDER_FAMILY[reviewer["tau_agent"]["model"].removeprefix("profile:")]
        != PROFILE_PROVIDER_FAMILY[worker["tau_agent"]["model"].removeprefix("profile:")]
    )


def test_review_fails_closed_when_no_independent_provider_exists(tmp_path: Path) -> None:
    import copy

    import pytest as _pytest

    plan = copy.deepcopy(PLAN)
    plan["workstreams"].insert(
        1, {"id": "ui", "role": "frontend", "allowed_paths": [], "depends_on": ["worker"]}
    )
    plan["workstreams"][-1]["depends_on"] = ["worker", "ui"]
    # Code on BOTH families: anthropic backend + openai frontend.
    plan["team"] = {
        "preset": "fullstack-premium",
        "role_profiles": {"backend": "claude-model-turn", "frontend": "codex-model-turn"},
    }
    with _pytest.raises(ValueError, match="independent review impossible"):
        _compile(plan, tmp_path)


REGISTRY_FIXTURE = [
    {"id": "claude-fable-model-turn", "strengths": ["orchestration", "review"], "complexity_tier": "premium", "pricing": {"input_per_mtok": 10, "output_per_mtok": 50}},
    {"id": "claude-model-turn", "strengths": ["standard_code", "review"], "complexity_tier": "high", "pricing": {"input_per_mtok": 3, "output_per_mtok": 15}},
    {"id": "codex-high-model-turn", "strengths": ["complex_code", "review"], "complexity_tier": "high", "pricing": {"input_per_mtok": 5, "output_per_mtok": 30}},
    {"id": "opencode-deepseek-v4", "strengths": ["standard_code"], "complexity_tier": "medium", "pricing": {"input_per_mtok": 0.14, "output_per_mtok": 0.28}},
    {"id": "opencode-kimi-k26", "strengths": ["docs"], "complexity_tier": "medium", "pricing": {"input_per_mtok": 0.95, "output_per_mtok": 4}},
    {"id": "opencode-kimi-k25", "strengths": ["docs"], "complexity_tier": "low", "pricing": {"input_per_mtok": 0.6, "output_per_mtok": 3}},
]

ALL_ROLES = ["coordinator", "backend", "frontend", "documentation", "testing", "independent_reviewer"]


def test_strength_selection_premium_matches_operator_policy() -> None:
    from ask.project_plan_to_tau import select_role_profiles_by_strength

    sel = select_role_profiles_by_strength(REGISTRY_FIXTURE, mode="premium", roles=ALL_ROLES)
    assert sel["coordinator"] == "claude-fable-model-turn"      # Fable orchestrates
    assert sel["backend"] == "codex-high-model-turn"            # GPT 5.5 high for complex code
    assert sel["documentation"] == "opencode-kimi-k26"          # Kimi for docs
    assert sel["independent_reviewer"] == "claude-fable-model-turn"  # highest-tier reviewer


def test_strength_selection_economical_picks_cheapest() -> None:
    from ask.project_plan_to_tau import select_role_profiles_by_strength

    sel = select_role_profiles_by_strength(REGISTRY_FIXTURE, mode="economical", roles=ALL_ROLES)
    assert sel["backend"] == "opencode-deepseek-v4"             # $0.42 combined
    assert sel["documentation"] == "opencode-kimi-k25"          # cheapest docs
    assert sel["coordinator"] == "claude-fable-model-turn"      # only orchestration profile


def test_strength_selection_fails_closed_on_missing_strength() -> None:
    import pytest as _pytest

    from ask.project_plan_to_tau import select_role_profiles_by_strength

    no_docs = [p for p in REGISTRY_FIXTURE if "docs" not in p["strengths"]]
    with _pytest.raises(ValueError, match="no profile satisfies strength 'docs'"):
        select_role_profiles_by_strength(no_docs, mode="economical", roles=["documentation"])
