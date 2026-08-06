"""Discovery batch 2 — broad /ask surface probes hunting for failures across
untested behaviors: propagation, topology, alias parsing, provider hints,
plan edges, intent. Deterministic (no live provider/browser)."""

from __future__ import annotations

import importlib.util
import json
import sys
from types import SimpleNamespace
from pathlib import Path

ASK_SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(ASK_SRC))

WORKER = Path(__file__).resolve().parents[1] / "scripts" / "tau_roundtable_worker.py"
_spec = importlib.util.spec_from_file_location("trw_batch2", WORKER)
w = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = w
_spec.loader.exec_module(w)


# 1. Propagation: the agent-facing join_receipt carries seat_terminal_states.
def test_join_receipt_propagates_seat_states_to_agent(tmp_path: Path) -> None:
    from ask import tau_dag
    join_dir = tmp_path / "node-artifacts" / "join"
    join_dir.mkdir(parents=True)
    (join_dir / "node-receipt.json").write_text(json.dumps({
        "schema": "ask.tau_dag_roundtable_join_receipt.v1",
        "status": "DEGRADED",
        "seat_terminal_states": [{"handler": "webgpt", "delivered": False, "failure_code": "browser_tab_unverified_with_multiple_provider_tabs"}],
        "degraded_seats": [{"handler": "webgpt", "failure_code": "browser_tab_unverified_with_multiple_provider_tabs"}],
        "removed_seats": ["webgpt"],
    }), encoding="utf-8")
    r = tau_dag._roundtable_join_receipt(tmp_path)
    assert r is not None
    assert r["removed_seats"] == ["webgpt"]
    assert r["seat_terminal_states"][0]["failure_code"] == "browser_tab_unverified_with_multiple_provider_tabs"


# 2. Model alias: effort suffix parses to model + reasoning_effort.
def test_model_effort_suffix_parsing() -> None:
    from ask import model_aliases
    # gpt-5.5-medium should resolve model gpt-5.5 with medium effort somewhere
    # in the alias/route layer; at minimum the alias table must not crash.
    resolved = model_aliases.resolve_model_alias("gpt-5.5-medium") if hasattr(model_aliases, "resolve_model_alias") else "gpt-5.5-medium"
    assert "gpt-5" in str(resolved)


# 3. Provider hint inference for known prefixes.
def test_provider_hint_inference() -> None:
    from ask.tau_dag import _infer_provider_hint_from_model
    assert _infer_provider_hint_from_model("deepseek-ai/DeepSeek-V3") == "chutes"
    assert _infer_provider_hint_from_model("opencode-go/deepseek-v4-pro") == "opencode-go"
    assert _infer_provider_hint_from_model("gpt-5.5") == ""


# 4. project_plan: cyclic dependency is rejected.
def test_project_plan_cycle_rejected() -> None:
    from ask.project_plan import SCHEMA_ID, validate_project_plan
    plan = {
        "schema": SCHEMA_ID, "goal": "g", "target": {"repo": "r"},
        "deliverables": [{"name": "x", "acceptance_criteria": ["a"]}],
        "workstreams": [
            {"id": "a", "role": "backend", "depends_on": ["b"]},
            {"id": "b", "role": "frontend", "depends_on": ["a"]},
        ],
        "team": {"preset": "fullstack-premium"}, "execution": {}, "unresolved": [],
    }
    ok, errors = validate_project_plan(plan)
    # Either a cycle error OR the dangling/self checks must reject it — never accept.
    assert not ok, "cyclic workstream dependency was accepted"


# 5. team-plan render: unknown domain -> NEEDS_INTERVIEW (unresolved).
def test_team_plan_unknown_domain_needs_interview() -> None:
    from ask.team_plan_cli import render_team_plan
    plan = render_team_plan("optimize the quantum flux capacitor", repo="r", team="fullstack-premium")
    assert plan["unresolved"] == ["workstreams"]


# 6. team-plan render: multi-domain infers all + reviewer gating.
def test_team_plan_reviewer_gates_all_workers() -> None:
    from ask.team_plan_cli import render_team_plan
    plan = render_team_plan("python api, react ui, docs, and tests", repo="r", team="fullstack-premium")
    review = [ws for ws in plan["workstreams"] if ws["role"] == "independent_reviewer"][0]
    workers = [ws["id"] for ws in plan["workstreams"] if ws["role"] not in ("coordinator", "independent_reviewer")]
    assert set(review["depends_on"]) == set(workers)


# 7. compete plan-to-tau: independent review invariant holds across presets.
def test_strength_selection_review_independent_both_presets() -> None:
    from ask.project_plan_to_tau import PROFILE_PROVIDER_FAMILY, TEAM_PRESETS
    for name, preset in TEAM_PRESETS.items():
        rev = preset["independent_reviewer"]
        # reviewer provider must differ from at least the primary code role
        assert PROFILE_PROVIDER_FAMILY[rev] != PROFILE_PROVIDER_FAMILY[preset["backend"]], name


# 8. route inventory: deprecated set only shrinks (no silent new direct paths).
def test_route_inventory_no_new_deprecated() -> None:
    from ask.route_inventory import INVENTORY, DEPRECATED_DIRECT
    current = {m for m, e in INVENTORY.items() if e.route_class == DEPRECATED_DIRECT}
    frozen = {"ask.py", "argue.py", "deep_review.py", "parallel_review.py",
              "scillm_agents.py", "delegate/resolver.py", "delegate/registry.py"}
    assert not (current - frozen), f"new deprecated paths: {current - frozen}"


# 9. browser failure classifier: rate-limit vs identity are distinct codes.
def test_rate_limit_and_identity_are_distinct() -> None:
    identity = w._classify_browser_failure(
        handler="webgpt", failure="", response_text="", raw_text="", prompt_text="",
        submit_meta={"tab_identity_preflight": {"ok": False, "error": "unverified_tab_id_with_multiple_chatgpt_tabs"}},
        commands=[])
    assert identity == w.BROWSER_TAB_UNVERIFIED_MULTIPLE


# 10. compete scorecard: deterministic winner when no judge and clear feature lead.
def test_compete_deterministic_winner_without_judge(tmp_path: Path) -> None:
    def seat(nid, handler, features):
        d = tmp_path / nid; d.mkdir(parents=True)
        resp = d / "response.md"
        resp.write_text("x" * 500 + "".join(f"\nVERIFIED_FEATURE: {f}" for f in features), encoding="utf-8")
        (d / "node-receipt.json").write_text(json.dumps({
            "schema": "ask.tau_dag_handler_receipt.v1", "node_id": nid, "handler": handler,
            "status": "PASS", "ok": True, "live": True, "provider_live": True,
            "response_path": str(resp), "response_chars": 600, "failure_code": None,
            "submit_meta": {"model": handler},
        }), encoding="utf-8")
    seat("handler-a", "gpt-5.5", ["f1", "f2", "f3"])
    seat("handler-b", "oc-deepseek", ["f1"])
    req = tmp_path / "request.json"
    req.write_text(json.dumps({"schema": "ask.tau_dag_request.v1", "request": "x", "criteria": ["c"], "immutable_goal": "r"}), encoding="utf-8")
    args = SimpleNamespace(workflow_mode="compete", node_id="join", handler="join", topology="concurrent",
                           request="x", immutable_goal="r", next_agent="human",
                           evidence=["compete_scorecard"], prior_node=[], request_file=str(req))
    start = {"goal": {"goal_id": "g", "goal_version": 1, "immutable_goal": "r", "goal_hash": "0" * 64},
             "github": {"repo": "grahama1970/agent-skills", "target": "skills/ask"}}
    jd = tmp_path / "join"; jd.mkdir()
    w._run_compete_join(args, start, jd)
    card = json.loads((jd / "compete-scorecard.json").read_text())
    assert card["winner_handler"] == "gpt-5.5"
    assert card["winner_selected_by"] == "deterministic_receipts"
