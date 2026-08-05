"""Deterministic multi-agent orchestration check for /ask (agent-skills#1220).

Renders a boss/workers team plan — premium coordinator, cheaper workers, an
independent reviewer (the AICodeKing "Fable orchestrator" pattern) — compiles
it to tau.generic_dag_spec.v1, and asserts the orchestration shape: role→
profile mapping is heterogeneous (boss on the premium profile, workers on the
cheap one), dependencies wire workers under the coordinator, and the reviewer
depends on every worker. Exit 0 with JSON markers on success; exit 1 with the
violated assertion otherwise. No model calls.
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from ask.project_plan import SCHEMA_ID
from ask.project_plan_to_tau import compile_plan_to_tau_spec, heterogeneous_profile_count


def main() -> int:
    plan = {
        "schema": SCHEMA_ID,
        "goal": "Build a settings dashboard with a Python API, React UI, and tests",
        "target": {"repo": "grahama1970/agent-skills"},
        "deliverables": [
            {"name": "API", "acceptance_criteria": ["endpoints covered by focused tests"]},
            {"name": "UI", "acceptance_criteria": ["screens render against fixtures"]},
        ],
        "workstreams": [
            {"id": "coordinator", "role": "coordinator", "prompt": "Plan and delegate the work."},
            {"id": "api", "role": "backend", "depends_on": ["coordinator"]},
            {"id": "ui", "role": "frontend", "depends_on": ["coordinator"]},
            {"id": "tests", "role": "testing", "depends_on": ["api", "ui"]},
            {"id": "review", "role": "independent_reviewer", "depends_on": ["api", "ui", "tests"]},
        ],
        "team": {"preset": "fullstack-premium", "role_profiles": {"testing": "codex-model-turn"}},
        "execution": {"topology": "hybrid", "max_concurrency": 3, "max_retries": 1},
        "unresolved": [],
    }
    spec = compile_plan_to_tau_spec(
        plan, run_id="orchestration-eval", run_dir=Path(tempfile.mkdtemp())
    )
    nodes = {n["node_id"]: n for n in spec["nodes"]}

    checks = {
        "schema_is_tau_generic_dag": spec["schema"] == "tau.generic_dag_spec.v1",
        "five_agents": len(nodes) == 5,
        "heterogeneous_profiles": heterogeneous_profile_count(spec) >= 2,
        "boss_on_premium_profile": nodes["coordinator"]["tau_agent"]["model"] == "profile:claude-model-turn",
        "workers_delegated_under_boss": all(
            "coordinator" in nodes[w]["depends_on"] for w in ("api", "ui")
        ),
        "reviewer_gates_all_workers": set(nodes["review"]["depends_on"]) == {"api", "ui", "tests"},
        "reviewer_independent_profile": nodes["review"]["tau_agent"]["model"] == "profile:codex-model-turn",
        "retry_budget_bounded": all(n["max_attempts"] == 2 for n in spec["nodes"]),
        "frozen": bool(spec["extensions"]["spec_sha256"]),
    }
    print(json.dumps({"schema": "ask.orchestration_eval_check.v1", "checks": checks}, indent=1))
    failed = [name for name, ok in checks.items() if not ok]
    print("ORCHESTRATION_SHAPE_" + ("PASS" if not failed else f"FAIL: {failed}"))
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
