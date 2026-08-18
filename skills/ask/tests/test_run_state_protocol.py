"""Runtime artifact protocol tests for ask."""

import asyncio
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import pytest
from typer.testing import CliRunner

import ask.ask as ask_module
import ask.argue as argue_module
import ask.nightly as nightly_module
import ask.os_learn as os_learn_module
import ask.os_query as os_query_module
import ask.parallel_review as parallel_review_module
import ask.parallel_review as parallel_review_module
import ask.pipeline as pipeline_module
import ask.preflight as preflight_module
import ask.status as status_module
from ask.doctor import run_doctor
from ask.run_viewer import viewer_snapshot
from ask.runtime_schema import validate_run_dir, validate_runtime_tree
from ask.run_state import AskRunState, make_run_id, list_runs, prune_runs, read_status, watch_status


def age_run_status(run: AskRunState, days: int = 30) -> None:
    old_time = time.time() - days * 24 * 60 * 60
    payload = json.loads(run.status_path.read_text())
    payload["updated_at"] = datetime.fromtimestamp(old_time, tz=timezone.utc).isoformat()
    run.status_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    os.utime(run.status_path, (old_time, old_time))
    os.utime(run.run_dir, (old_time, old_time))


def _question_citation(text: str = "Should we ship?", supports: str = "verdict") -> dict:
    return {
        "source_id": "QUESTION",
        "source_kind": "question",
        "quote_or_summary": text,
        "supports": supports,
    }


def _target_citation(text: str = "target.py returns 42", supports: str = "verdict") -> dict:
    return {
        "source_id": "TARGET_BUNDLE",
        "source_kind": "target_bundle",
        "quote_or_summary": text,
        "supports": supports,
    }


def test_run_state_writes_request_status_and_events(tmp_path):
    run = AskRunState("protocol-test", output_root=tmp_path)
    run.write_request({"question": "what changed?", "scope": "ask"})
    run.event("custom_event", detail="ok")
    run.finish({"question": "what changed?", "scope": "ask", "items": [{"solution": "ok"}]})

    assert run.request_path.exists()
    assert run.status_path.exists()
    assert run.events_path.exists()
    assert (run.run_dir / "artifact_manifest.json").exists()

    request = json.loads(run.request_path.read_text())
    status = json.loads(run.status_path.read_text())
    manifest = json.loads((run.run_dir / "artifact_manifest.json").read_text())
    events = [json.loads(line) for line in run.events_path.read_text().splitlines()]

    assert request["runtime_protocol_version"] == "ask.runtime.v1"
    assert status["state"] == "answered"
    assert status["artifacts"]["request"] == str(run.request_path)
    assert status["artifacts"]["artifact_manifest"] == str(run.run_dir / "artifact_manifest.json")
    assert manifest["schema_version"] == "ask.artifact_manifest.v1"
    assert manifest["state"] == "answered"
    assert manifest["request"] == str(run.request_path)
    assert manifest["status"] == str(run.status_path)
    assert manifest["events"] == str(run.events_path)
    assert [event["event"] for event in events] == ["request_written", "custom_event", "finished"]
    assert validate_run_dir(run.run_dir)["ok"]


def test_run_state_preserves_route_decision_through_finish(tmp_path):
    run = AskRunState("route-decision", output_root=tmp_path)
    route_decision = {
        "schema_version": "ask.route_decision.v1",
        "selected_mode": "oracle",
        "selected_backend": "scillm",
        "reasons": ["oracle_requested_or_inferred"],
    }
    run.write_request({"question": "route?", "scope": "ask", "route_decision": route_decision})
    run.update("running", route_decision=route_decision)
    run.finish({"question": "route?", "scope": "ask", "items": [{"solution": "ok"}]})

    status = json.loads(run.status_path.read_text())
    manifest = json.loads((run.run_dir / "artifact_manifest.json").read_text())

    assert status["request"]["route_decision"] == route_decision
    assert status["route_decision"] == route_decision
    assert manifest["route_decision"] == route_decision


def test_runtime_tree_schema_validation_reports_invalid_runs(tmp_path):
    valid = AskRunState("schema-valid", output_root=tmp_path)
    valid.write_request({"question": "schema"})
    valid.finish({"question": "schema", "items": []})
    invalid = tmp_path / "schema-invalid"
    invalid.mkdir()
    (invalid / "schema-invalid.status.json").write_text("{}")

    result = validate_runtime_tree(tmp_path)

    assert not result["ok"]
    assert result["runs_checked"] == 2
    assert any(item["run_dir"].endswith("schema-invalid") for item in result["invalid_runs"])


def test_read_status_includes_event_tail(tmp_path):
    run = AskRunState("tail-test", output_root=tmp_path)
    run.write_request({"question": "tail?", "scope": "ask"})
    run.event("middle")
    run.finish({"question": "tail?", "scope": "ask", "items": []})

    status = read_status("tail-test", tail_events=2, output_root=tmp_path)

    assert status["state"] == "no_results"
    assert [event["event"] for event in status["event_tail"]] == ["middle", "finished"]


def test_read_status_marks_dead_running_controller_stale(tmp_path):
    run = AskRunState("dead-controller", output_root=tmp_path)
    run.write_request({"question": "stuck?", "scope": "ask"})
    payload = json.loads(run.status_path.read_text())
    payload["state"] = "running"
    payload["controller_pid"] = 999999
    run.status_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")

    status = read_status("dead-controller", output_root=tmp_path)

    assert status["state"] == "stale"
    assert status["recorded_state"] == "running"
    assert status["stale_reason"] == "controller_pid_not_alive"


def test_run_state_needs_attention_and_artifact_registration_survive_finish(tmp_path):
    run = AskRunState("attention-test", output_root=tmp_path)
    run.write_request({"question": "safe to proceed?", "scope": "ask"})
    attention = run.needs_attention(
        reason="missing_deep_review_target",
        question="Deep review needs an explicit target.",
        resume_hint="Run again with --deep-review-target <target>.",
    )
    run.add_artifacts({"review_md": tmp_path / "review.md", "review_json": tmp_path / "review.json"})
    run.finish({"question": "safe to proceed?", "items": []}, state="needs_attention")

    status = read_status("attention-test", tail_events=10, output_root=tmp_path)

    assert attention["reason"] == "missing_deep_review_target"
    assert status["state"] == "needs_attention"
    assert status["artifacts"]["review_md"].endswith("review.md")
    assert status["needs_attention"]["resume_hint"] == "Run again with --deep-review-target <target>."
def test_sparta_preflight_routes_grounded_mustard_cm0001_to_evidence_case():
    decision = preflight_module.decide_sparta_preflight(
        "How does NIST AC-3 map to the mustard SPARTA countermeasure CM0001?",
        {
            "entities": [
                {
                    "id": "CM0001",
                    "label": "mustard access-control countermeasure",
                    "corpus": "sparta",
                    "source_corpus": "nist",
                    "type": "control_crosswalk",
                    "status": "resolved",
                }
            ]
        },
        [],
    )

    assert decision["route"] == "evidence_case"
    assert decision["reason"] == "grounded_sparta_corpora_signal"
    assert decision["grounded_entities"][0]["id"] == "CM0001"
    assert "mustard" in decision["grounded_entities"][0]["label"]


def test_sparta_preflight_unresolved_cm0001_pauses_needs_attention():
    decision = preflight_module.decide_sparta_preflight(
        "Can we claim the mustard SPARTA CM0001 evidence is compliant?",
        {
            "entities": [
                {
                    "id": "CM0001",
                    "label": "mustard SPARTA evidence claim",
                    "corpus": "sparta",
                    "status": "unresolved",
                }
            ]
        },
        [],
    )

    assert decision["route"] == "needs_attention"
    assert decision["reason"] == "unresolved_or_fabricated_sparta_identifier"
    assert decision["unresolved_entities"][0]["id"] == "CM0001"


def test_cli_sparta_evidence_case_required_fails_closed(monkeypatch, tmp_path):
    monkeypatch.setattr(
        ask_module,
        "run_sparta_preflight",
        lambda *args, **kwargs: {
            "route": "evidence_case",
            "reason": "grounded_sparta_corpora_signal",
            "grounded_entities": [{"id": "CM0001", "label": "grounded SPARTA entity"}],
        },
    )
    monkeypatch.setattr(ask_module, "run_memory_recall", lambda *args, **kwargs: {"returncode": 0, "stdout": "[]", "stderr": ""})
    monkeypatch.setattr(ask_module, "_try_evidence_case", lambda *args, **kwargs: None)
    monkeypatch.setattr(ask_module.SessionWriter, "write", lambda self: None)
    monkeypatch.setattr(ask_module, "_record_ask_telemetry", lambda **kwargs: None)

    result = CliRunner().invoke(
        ask_module.app,
        [
            "Can",
            "we",
            "claim",
            "CM0001",
            "coverage?",
            "--ask-id",
            "sparta-evidence-required",
            "--run-output-root",
            str(tmp_path),
            "--json",
        ],
    )

    assert result.exit_code == 2
    payload = json.loads(result.stdout)
    status = read_status("sparta-evidence-required", tail_events=10, output_root=tmp_path)
    assert payload["needs_attention"]["reason"] == "evidence_case_required_but_unavailable"
    assert payload["needs_attention"]["safe_default"] == "do_not_answer_as_grounded"
    assert status["state"] == "needs_attention"
    assert status["needs_attention"]["reason"] == "evidence_case_required_but_unavailable"
    assert any(event["event"] == "needs_attention" for event in status["event_tail"])


def test_status_run_writes_html_viewer_artifacts(tmp_path):
    run = AskRunState("viewer-run", output_root=tmp_path)
    run.write_request({"command": "ask", "question": "what happened?", "scope": "ask"})
    run.finish({"question": "what happened?", "scope": "ask", "items": [{"solution": "ok"}]})

    snapshot = viewer_snapshot("viewer-run", output_root=tmp_path)

    status = read_status("viewer-run", output_root=tmp_path)
    run_dir = tmp_path / "viewer-run"
    assert (run_dir / "index.html").exists()
    assert (run_dir / "ask-viewer.css").exists()
    assert (run_dir / "ask-viewer.js").exists()
    assert (run_dir / "viewer.json").exists()
    assert snapshot["artifacts"]["index"].endswith("index.html")
    assert status["artifacts"]["viewer"].endswith("index.html")



def test_cli_ask_writes_runtime_artifacts(monkeypatch, tmp_path):
    captured = {}

    def fake_ask(**kwargs):
        captured.update(kwargs)
        return {"question": kwargs["question"], "scope": kwargs["scope"], "items": [{"solution": "ok"}]}

    monkeypatch.setattr(ask_module, "ask", fake_ask)
    result = CliRunner().invoke(
        ask_module.app,
        [
            "what",
            "changed?",
            "--ask-id",
            "cli-protocol",
            "--run-output-root",
            str(tmp_path),
        ],
    )

    assert result.exit_code == 0
    status = read_status("cli-protocol", tail_events=10, output_root=tmp_path)
    request = json.loads((tmp_path / "cli-protocol" / "cli-protocol.request.json").read_text())

    assert captured["question"] == "what changed?"
    assert request["question"] == "what changed?"
    assert request["route_decision"]["schema_version"] == "ask.route_decision.v1"
    assert request["route_decision"]["selected_mode"] == "memory_ask"
    assert request["route_decision"]["selected_backend"] == "memory"
    assert status["route_decision"]["selected_mode"] == "memory_ask"
    assert status["state"] == "answered"
    assert [event["event"] for event in status["event_tail"]] == [
        "request_written",
        "ask_started",
        "route_decision",
        "finished",
    ]


def test_cli_deep_review_missing_target_pauses_with_needs_attention(tmp_path):
    result = CliRunner().invoke(
        ask_module.app,
        [
            "safe",
            "to",
            "proceed?",
            "--ask-id",
            "missing-target",
            "--run-output-root",
            str(tmp_path),
            "--json",
        ],
    )

    assert result.exit_code == 2
    status = read_status("missing-target", tail_events=10, output_root=tmp_path)
    assert status["state"] == "needs_attention"
    assert status["needs_attention"]["reason"] == "missing_deep_review_target"
    assert status["needs_attention"]["safe_default"] == "do_not_run_review"
    assert any(event["event"] == "needs_attention" for event in status["event_tail"])
    payload = json.loads(result.stdout)
    assert payload["needs_attention"]["safe_default"] == "do_not_run_review"


def test_cli_parallel_review_missing_target_pauses_with_needs_attention(tmp_path):
    result = CliRunner().invoke(
        ask_module.app,
        [
            "review",
            "this",
            "--parallel-review",
            "--ask-id",
            "missing-parallel-target",
            "--run-output-root",
            str(tmp_path),
            "--json",
        ],
    )

    assert result.exit_code == 2
    status = read_status("missing-parallel-target", tail_events=10, output_root=tmp_path)
    payload = json.loads(result.stdout)
    assert status["state"] == "needs_attention"
    assert status["needs_attention"]["reason"] == "missing_parallel_review_target"
    assert payload["needs_attention"]["safe_default"] == "do_not_run_review"


def _valid_argue_result(verdict="FOR", confidence="medium", decision_required=False, tie_breaker=""):
    return {
        "schema_version": argue_module.ARGUE_SCHEMA_VERSION,
        "question": "Should we ship?",
        "source_bundle": {
            "sources": [
                {"source_id": "QUESTION", "kind": "question", "content": "Should we ship?"},
            ],
        },
        "for_case": {
            "side": "FOR",
            "position": "Ship the reversible change.",
            "strongest_argument": "The change is small and reversible.",
            "evidence": ["The change is small and reversible."],
            "evidence_citations": [_question_citation("The change is small and reversible.", "advocate_evidence")],
            "assumptions": [],
            "weaknesses": [],
            "missing_evidence": [],
            "response_to_opposition": "Risk is bounded by reversibility.",
            "what_would_change_my_mind": ["Evidence of hidden coupling."],
            "confidence": "medium",
        },
        "against_case": {
            "side": "AGAINST",
            "position": "Do not ship without more evidence.",
            "strongest_argument": "The tests do not cover rollback.",
            "evidence": ["The tests do not cover rollback."],
            "evidence_citations": [_question_citation("The tests do not cover rollback.", "advocate_evidence")],
            "assumptions": [],
            "weaknesses": [],
            "missing_evidence": ["Rollback behavior evidence."],
            "response_to_opposition": "Small changes can still break rollback.",
            "what_would_change_my_mind": ["Passing rollback test."],
            "confidence": "medium",
        },
        "judge": {
            "schema_version": argue_module.ARGUE_SCHEMA_VERSION,
            "verdict": verdict,
            "confidence": confidence,
            "decision_required": decision_required,
            "tie_breaker": tie_breaker,
            "decision_criterion": "Prefer reversible changes when risk is bounded.",
            "winning_side": verdict if verdict in {"FOR", "AGAINST"} else "none",
            "deciding_factors": ["The change is small and reversible."],
            "strongest_for_argument": "The change is small and reversible.",
            "strongest_against_argument": "The tests do not cover rollback.",
            "strongest_counterargument": "The tests do not cover rollback.",
            "why_counterargument_does_or_does_not_win": "Rollback coverage matters, but reversibility bounds the decision.",
            "evidence_used": ["The change is small and reversible."],
            "evidence_citations": [_question_citation("The change is small and reversible.", "verdict")],
            "assumptions": [],
            "missing_evidence": [],
            "what_would_change_the_verdict": ["Evidence of hidden coupling."],
            "recommended_next_action": "Ship with rollback monitoring.",
            "uncertainty_disclosure": "This remains uncertain.",
        },
    }


def test_argue_verifier_rejects_for_without_counterargument():
    payload = _valid_argue_result()
    payload["judge"]["strongest_counterargument"] = ""

    result = argue_module.verify_argue_result(payload)

    assert result["status"] == "FAIL"
    assert any("strongest_counterargument" in failure for failure in result["failures"])


def test_argue_verifier_rejects_against_without_evidence_used():
    payload = _valid_argue_result(verdict="AGAINST")
    payload["judge"]["evidence_used"] = []

    result = argue_module.verify_argue_result(payload)

    assert result["status"] == "FAIL"
    assert "empty evidence_used requires INSUFFICIENT_EVIDENCE" in result["failures"]


def test_argue_verifier_rejects_high_confidence_with_missing_evidence():
    payload = _valid_argue_result(confidence="high")
    payload["judge"]["missing_evidence"] = ["Production latency data."]

    result = argue_module.verify_argue_result(payload)

    assert result["status"] == "FAIL"
    assert "high confidence is not allowed when missing_evidence is non-empty" in result["failures"]


def test_argue_verifier_rejects_for_when_grounding_fell_back():
    payload = _valid_argue_result(verdict="FOR")
    payload["source_bundle"]["sources"].append(
        {"source_id": "MEMORY.1", "kind": "memory", "content": "The change is small and reversible."}
    )
    payload["judge"]["evidence_citations"] = [
        {
            "source_id": "MEMORY.1",
            "source_kind": "memory",
            "quote_or_summary": "The change is small and reversible.",
            "supports": "verdict",
        }
    ]
    payload["judge"]["scillm"] = {
        "source_grounding_status": "retry_without_source_after_error",
        "grounding_passed": False,
        "metadata_requested": {
            "ask_id": "argue-grounding",
            "protocol": "argue",
            "node_id": "judge",
            "batch_id": "ask-argue-argue-grounding",
            "item_id": "judge",
        },
        "metadata_returned": {
            "ask_id": "argue-grounding",
            "protocol": "argue",
            "node_id": "judge",
            "batch_id": "ask-argue-argue-grounding",
            "item_id": "judge",
        },
    }

    result = argue_module.verify_argue_result(payload)

    assert result["status"] == "FAIL"
    assert result["grounding_degraded"] is True
    assert any("grounding" in failure for failure in result["failures"])


def test_argue_verifier_allows_grounding_fallback_for_direct_question_evidence():
    payload = _valid_argue_result(verdict="FOR")
    payload["judge"]["scillm"] = {
        "source_grounding_status": "retry_without_source_after_error",
        "grounding_passed": False,
        "metadata_requested": {
            "ask_id": "argue-question-grounding",
            "protocol": "argue",
            "node_id": "judge",
            "batch_id": "ask-argue-argue-question-grounding",
            "item_id": "judge",
        },
        "metadata_returned": {
            "ask_id": "argue-question-grounding",
            "protocol": "argue",
            "node_id": "judge",
            "batch_id": "ask-argue-argue-question-grounding",
            "item_id": "judge",
        },
    }

    result = argue_module.verify_argue_result(payload)

    assert result["status"] == "PASS"
    assert result["grounding_degraded"] is True


def test_argue_verifier_rejects_scillm_metadata_return_mismatch():
    payload = _valid_argue_result(verdict="FOR")
    payload["judge"]["scillm"] = {
        "source_grounding_status": "requested",
        "metadata_requested": {
            "ask_id": "argue-metadata",
            "protocol": "argue",
            "node_id": "judge",
            "batch_id": "ask-argue-argue-metadata",
            "item_id": "judge",
        },
        "metadata_returned": {
            "ask_id": "argue-metadata",
            "protocol": "argue",
            "node_id": "wrong-node",
            "batch_id": "ask-argue-argue-metadata",
            "item_id": "judge",
        },
    }

    result = argue_module.verify_argue_result(payload)

    assert result["status"] == "FAIL"
    assert any("metadata" in failure for failure in result["failures"])


def test_argue_judge_prompt_calibrates_missing_evidence_and_confidence():
    payload = _valid_argue_result()

    prompt = argue_module.build_judge_prompt(
        payload["question"],
        payload["for_case"],
        payload["against_case"],
    )

    assert "missing_evidence must contain only decision-blocking evidence" in prompt
    assert "If missing_evidence is non-empty, confidence must not be high." in prompt
    assert "cite QUESTION and set missing_evidence to []" in prompt
    assert "not missing_evidence" in prompt


def test_argue_verifier_requires_tie_breaker_for_decision_required():
    payload = _valid_argue_result(decision_required=True, tie_breaker="more-reversible")

    assert argue_module.verify_argue_result(payload)["status"] == "PASS"

    payload["judge"]["uncertainty_disclosure"] = ""
    result = argue_module.verify_argue_result(payload)
    assert result["status"] == "FAIL"
    assert any("uncertainty_disclosure" in failure for failure in result["failures"])


def test_argue_verifier_rejects_judge_evidence_not_from_advocates():
    payload = _valid_argue_result()
    payload["judge"]["evidence_used"] = ["Private judge-only evidence."]

    result = argue_module.verify_argue_result(payload)

    assert result["status"] == "FAIL"
    assert any("not present in advocate outputs" in failure for failure in result["failures"])


def test_argue_verifier_requires_structured_citations_for_verdict():
    payload = _valid_argue_result()
    payload["judge"]["evidence_citations"] = []

    result = argue_module.verify_argue_result(payload)

    assert result["status"] == "FAIL"
    assert any("structured citation" in failure for failure in result["failures"])


def test_argue_verifier_allows_advocate_missing_evidence_as_judge_evidence():
    payload = _valid_argue_result(verdict="NO_CLEAR_WINNER")
    payload["judge"]["evidence_used"] = ["Rollback behavior evidence."]
    payload["judge"]["confidence"] = "medium"

    result = argue_module.verify_argue_result(payload)

    assert result["status"] == "PASS"


def test_cli_argue_runs_two_parallel_advocates_then_judge(monkeypatch, tmp_path):
    active_advocates = 0
    max_active_advocates = 0
    call_order = []
    metadata_by_role = {}
    source_by_role = {}

    async def fake_scillm_json_call_async(client, *, model, reasoning_effort, timeout, role, prompt, metadata=None, source=None):
        nonlocal active_advocates, max_active_advocates
        call_order.append(role)
        metadata_by_role[role] = metadata
        source_by_role[role] = source
        if "advocate" in role:
            active_advocates += 1
            max_active_advocates = max(max_active_advocates, active_advocates)
            await asyncio.sleep(0.01)
            active_advocates -= 1
        if role == "FOR advocate":
            return {
                "position": "Ship the reversible change.",
                "strongest_argument": "The change is small and reversible.",
                "evidence": ["The change is small and reversible."],
                "evidence_citations": [_question_citation("The change is small and reversible.", "advocate_evidence")],
                "what_would_change_my_mind": ["Evidence of hidden coupling."],
                "confidence": "medium",
            }, model, {"metadata_requested": metadata, "metadata_returned": metadata, "call_id": f"call-{role}"}
        if role == "AGAINST advocate":
            return {
                "position": "Do not ship without more evidence.",
                "strongest_argument": "The tests do not cover rollback.",
                "evidence": ["The tests do not cover rollback."],
                "evidence_citations": [_question_citation("The tests do not cover rollback.", "advocate_evidence")],
                "missing_evidence": ["Rollback behavior evidence."],
                "what_would_change_my_mind": ["Passing rollback test."],
                "confidence": "medium",
            }, model, {"metadata_requested": metadata, "metadata_returned": metadata, "call_id": f"call-{role}"}
        return {
            "verdict": "FOR",
            "confidence": "medium",
            "decision_criterion": "Prefer reversible changes when risk is bounded.",
            "winning_side": "FOR",
            "deciding_factors": ["The change is small and reversible."],
            "strongest_for_argument": "The change is small and reversible.",
            "strongest_against_argument": "The tests do not cover rollback.",
            "strongest_counterargument": "The tests do not cover rollback.",
            "why_counterargument_does_or_does_not_win": "Rollback coverage matters, but reversibility bounds the decision.",
            "evidence_used": ["The change is small and reversible."],
            "evidence_citations": [_question_citation("The change is small and reversible.", "verdict")],
            "what_would_change_the_verdict": ["Evidence of hidden coupling."],
            "recommended_next_action": "Ship with rollback monitoring.",
            "uncertainty_disclosure": "This remains uncertain.",
        }, model, {"metadata_requested": metadata, "metadata_returned": metadata, "call_id": "call-judge"}

    monkeypatch.setattr(argue_module, "_scillm_json_call_async", fake_scillm_json_call_async)
    monkeypatch.setattr(ask_module, "run_memory_recall", lambda *args, **kwargs: {"returncode": 0, "stdout": "[]", "stderr": ""})
    monkeypatch.setattr(ask_module, "_try_evidence_case", lambda *args, **kwargs: None)
    monkeypatch.setattr(ask_module.SessionWriter, "write", lambda self: None)
    monkeypatch.setattr(ask_module, "_record_ask_telemetry", lambda **kwargs: None)

    result = CliRunner().invoke(
        ask_module.app,
        [
            "Should",
            "we",
            "ship?",
            "--argue",
            "--ask-id",
            "argue-dag",
            "--run-output-root",
            str(tmp_path),
            "--json",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    status = read_status("argue-dag", tail_events=30, output_root=tmp_path)
    artifacts = status["artifacts"]
    assert payload["argue"]["verdict"] == "FOR"
    assert payload["argue"]["verifier_status"] == "PASS"
    assert max_active_advocates == 2
    assert set(call_order[:2]) == {"FOR advocate", "AGAINST advocate"}
    assert call_order[-1] == "sequential judge"
    assert (tmp_path / "argue-dag" / "argue" / "for.json").exists()
    assert (tmp_path / "argue-dag" / "argue" / "against.json").exists()
    assert (tmp_path / "argue-dag" / "argue" / "judge.json").exists()
    assert (tmp_path / "argue-dag" / "argue" / "source_bundle.json").exists()
    assert artifacts["argue_result"].endswith("argue.json")
    assert metadata_by_role["FOR advocate"]["protocol"] == "argue"
    assert metadata_by_role["FOR advocate"]["node_id"] == "FOR"
    assert metadata_by_role["FOR advocate"]["batch_id"].startswith("ask-argue-argue-dag-")
    assert metadata_by_role["sequential judge"]["node_id"] == "judge"
    assert "QUESTION" in source_by_role["FOR advocate"]
    for_case = json.loads((tmp_path / "argue-dag" / "argue" / "for.json").read_text())
    assert for_case["scillm"]["metadata_returned"]["item_id"] == "FOR"


def test_cli_argue_verifier_failure_exits_needs_attention(monkeypatch, tmp_path):
    async def fake_scillm_json_call_async(client, *, model, reasoning_effort, timeout, role, prompt, metadata=None, source=None):
        if role == "FOR advocate":
            return {
                "strongest_argument": "The change is small and reversible.",
                "evidence": ["The change is small and reversible."],
                "evidence_citations": [_question_citation("The change is small and reversible.", "advocate_evidence")],
                "confidence": "medium",
            }, model
        if role == "AGAINST advocate":
            return {
                "strongest_argument": "The tests do not cover rollback.",
                "evidence": ["The tests do not cover rollback."],
                "evidence_citations": [_question_citation("The tests do not cover rollback.", "advocate_evidence")],
                "confidence": "medium",
            }, model
        return {
            "verdict": "FOR",
            "confidence": "medium",
            "decision_criterion": "Prefer reversible changes.",
            "winning_side": "FOR",
            "evidence_used": ["The change is small and reversible."],
            "evidence_citations": [_question_citation("The change is small and reversible.", "verdict")],
            "why_counterargument_does_or_does_not_win": "Not addressed.",
            "what_would_change_the_verdict": ["Evidence of hidden coupling."],
        }, model

    monkeypatch.setattr(argue_module, "_scillm_json_call_async", fake_scillm_json_call_async)
    monkeypatch.setattr(ask_module, "run_memory_recall", lambda *args, **kwargs: {"returncode": 0, "stdout": "[]", "stderr": ""})
    monkeypatch.setattr(ask_module, "_try_evidence_case", lambda *args, **kwargs: None)
    monkeypatch.setattr(ask_module.SessionWriter, "write", lambda self: None)
    monkeypatch.setattr(ask_module, "_record_ask_telemetry", lambda **kwargs: None)

    result = CliRunner().invoke(
        ask_module.app,
        [
            "Should",
            "we",
            "ship?",
            "--argue",
            "--ask-id",
            "argue-fail",
            "--run-output-root",
            str(tmp_path),
            "--json",
        ],
    )

    assert result.exit_code == 2
    payload = json.loads(result.stdout)
    assert payload["needs_attention"]["reason"] == "argue_verifier_failed"
    assert read_status("argue-fail", output_root=tmp_path)["state"] == "needs_attention"
    assert (tmp_path / "argue-fail" / "argue" / "verifier.log").exists()


def test_cli_argue_advocate_failure_preserves_partial_artifacts(monkeypatch, tmp_path):
    async def fake_scillm_json_call_async(client, *, model, reasoning_effort, timeout, role, prompt, metadata=None, source=None):
        if role == "FOR advocate":
            raise TimeoutError("advocate timed out")
        if role == "AGAINST advocate":
            return {
                "strongest_argument": "The tests do not cover rollback.",
                "evidence": ["The tests do not cover rollback."],
                "evidence_citations": [_question_citation("The tests do not cover rollback.", "advocate_evidence")],
                "confidence": "medium",
            }, model
        raise AssertionError("judge should not run after advocate failure")

    monkeypatch.setattr(argue_module, "_scillm_json_call_async", fake_scillm_json_call_async)
    monkeypatch.setattr(ask_module, "run_memory_recall", lambda *args, **kwargs: {"returncode": 0, "stdout": "[]", "stderr": ""})
    monkeypatch.setattr(ask_module, "_try_evidence_case", lambda *args, **kwargs: None)
    monkeypatch.setattr(ask_module.SessionWriter, "write", lambda self: None)
    monkeypatch.setattr(ask_module, "_record_ask_telemetry", lambda **kwargs: None)

    result = CliRunner().invoke(
        ask_module.app,
        [
            "Should",
            "we",
            "ship?",
            "--argue",
            "--ask-id",
            "argue-advocate-timeout",
            "--run-output-root",
            str(tmp_path),
            "--json",
        ],
    )

    assert result.exit_code == 2
    payload = json.loads(result.stdout)
    argue_dir = tmp_path / "argue-advocate-timeout" / "argue"
    for_case = json.loads((argue_dir / "for.json").read_text())
    against_case = json.loads((argue_dir / "against.json").read_text())
    judge = json.loads((argue_dir / "judge.json").read_text())
    status = read_status("argue-advocate-timeout", tail_events=30, output_root=tmp_path)
    events = [event["event"] for event in status["event_tail"]]

    assert payload["needs_attention"]["reason"] == "argue_scillm_call_failed"
    assert payload["needs_attention"]["stage"] == "advocate"
    assert for_case["status"] == "failed"
    assert for_case["error_type"] == "TimeoutError"
    assert against_case["status"] == "ok"
    assert judge["status"] == "skipped"
    assert "argue_advocate_failed" in events
    assert "argue_judge_skipped" in events


def test_cli_argue_judge_failure_preserves_advocate_artifacts(monkeypatch, tmp_path):
    async def fake_scillm_json_call_async(client, *, model, reasoning_effort, timeout, role, prompt, metadata=None, source=None):
        if role == "FOR advocate":
            return {
                "strongest_argument": "The change is small and reversible.",
                "evidence": ["The change is small and reversible."],
                "evidence_citations": [_question_citation("The change is small and reversible.", "advocate_evidence")],
                "confidence": "medium",
            }, model
        if role == "AGAINST advocate":
            return {
                "strongest_argument": "The tests do not cover rollback.",
                "evidence": ["The tests do not cover rollback."],
                "evidence_citations": [_question_citation("The tests do not cover rollback.", "advocate_evidence")],
                "confidence": "medium",
            }, model
        raise RuntimeError("judge backend failed")

    monkeypatch.setattr(argue_module, "_scillm_json_call_async", fake_scillm_json_call_async)
    monkeypatch.setattr(ask_module, "run_memory_recall", lambda *args, **kwargs: {"returncode": 0, "stdout": "[]", "stderr": ""})
    monkeypatch.setattr(ask_module, "_try_evidence_case", lambda *args, **kwargs: None)
    monkeypatch.setattr(ask_module.SessionWriter, "write", lambda self: None)
    monkeypatch.setattr(ask_module, "_record_ask_telemetry", lambda **kwargs: None)

    result = CliRunner().invoke(
        ask_module.app,
        [
            "Should",
            "we",
            "ship?",
            "--argue",
            "--ask-id",
            "argue-judge-fail",
            "--run-output-root",
            str(tmp_path),
            "--json",
        ],
    )

    assert result.exit_code == 2
    payload = json.loads(result.stdout)
    argue_dir = tmp_path / "argue-judge-fail" / "argue"
    for_case = json.loads((argue_dir / "for.json").read_text())
    against_case = json.loads((argue_dir / "against.json").read_text())
    judge = json.loads((argue_dir / "judge.json").read_text())
    status = read_status("argue-judge-fail", tail_events=30, output_root=tmp_path)
    events = [event["event"] for event in status["event_tail"]]

    assert payload["needs_attention"]["reason"] == "argue_scillm_call_failed"
    assert payload["needs_attention"]["stage"] == "judge"
    assert for_case["status"] == "ok"
    assert against_case["status"] == "ok"
    assert judge["status"] == "failed"
    assert judge["error_type"] == "RuntimeError"
    assert "argue_judge_failed" in events


def test_parallel_review_reviewer_payloads_include_scillm_metadata_and_source(tmp_path):
    captured_payloads = []

    class CapturingAdapter:
        async def review(self, payload):
            captured_payloads.append(payload)
            return {
                "reviewer": payload["reviewer"]["name"],
                "verdict": "SAFE",
                "summary": "ok",
                "files_inspected": [],
                "evidence": ["TARGET_BUNDLE"],
                "findings": [],
                "test_gaps": [],
                "read_only_claim": True,
                "confidence": "medium",
            }

    run_state = AskRunState("parallel-metadata", output_root=tmp_path)
    run_state.write_request({"question": "review", "scope": "ask"})
    plan = parallel_review_module.build_parallel_review_plan(
        question="review target",
        target="target.py",
        reviewers=1,
        personas="Brandon",
    )
    plan["target_bundle"] = {"entries": [{"kind": "file", "path": "target.py"}]}
    source_bundle = parallel_review_module.build_source_bundle(
        question="review target",
        target_bundle="# target",
        target_entries=plan["target_bundle"]["entries"],
    )

    outputs = parallel_review_module._run_reviewers(
        CapturingAdapter(),
        plan,
        "# target",
        5,
        run_state,
        source_bundle,
        tmp_path / "parallel_review",
    )

    assert outputs[0]["reviewer"] == "Brandon"
    payload = captured_payloads[0]
    metadata = payload["scillm_metadata"]
    assert metadata["ask_id"] == "parallel-metadata"
    assert metadata["protocol"] == "parallel_review"
    assert metadata["node_role"] == "reviewer"
    assert metadata["batch_id"].startswith("ask-parallel_review-parallel-metadata-")
    assert metadata["item_id"] == "reviewer-1"
    assert metadata["source_bundle_id"] == source_bundle["source_bundle_id"]
    assert "TARGET_BUNDLE" in payload["source"]


def test_source_bundle_chunks_large_target_bundle():
    source_bundle = parallel_review_module.build_source_bundle(
        question="review",
        target_bundle="a" * 9000,
        target_entries=[{"kind": "file", "path": "target.py"}],
    )

    source_ids = [source["source_id"] for source in source_bundle["sources"]]

    assert "TARGET_BUNDLE.1" in source_ids
    assert "TARGET_BUNDLE.2" in source_ids
    assert all(len(source["content"]) <= 4000 for source in source_bundle["sources"])


def test_cli_ask_dry_run_includes_argue_dag_options(tmp_path):
    result = CliRunner().invoke(
        ask_module.app,
        [
            "Should",
            "we",
            "ship?",
            "--argue",
            "--decision-required",
            "--tie-breaker",
            "more-reversible",
            "--dry-run",
            "--json",
            "--ask-id",
            "argue-dry",
            "--run-output-root",
            str(tmp_path),
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["options"]["argue"] is True
    assert "argue FOR advocate via scillm" in payload["risk_analysis"]["external_calls"]
    assert "argue sequential judge via scillm" in payload["risk_analysis"]["external_calls"]
    assert "argue/argue.json" in payload["risk_analysis"]["filesystem_writes"]
    assert not (tmp_path / "argue-dry").exists()


def test_cli_parallel_review_runs_three_reviewers_then_judge(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    target = tmp_path / "target.py"
    target.write_text("def answer():\n    return 42\n")
    calls = []

    class FakeScillmReviewerAdapter:
        def __init__(self, **kwargs):
            pass

        async def review(self, payload):
            reviewer = payload["reviewer"]["name"]
            calls.append(reviewer)
            if reviewer == "review-judge":
                return {
                    "reviewer": "review-judge",
                    "judge": "review-judge",
                    "best_reviewer": "Brandon",
                    "best_review_reason": "Most specific evidence.",
                    "hybrid_summary": "The reviewers inspected target.py and found no blocking issues.",
                    "verdict": "SAFE",
                    "summary": "Judge synthesis complete.",
                    "files_inspected": [str(target)],
                    "evidence": ["target.py returns 42"],
                    "evidence_citations": [_target_citation("target.py returns 42", "verdict")],
                    "findings": [],
                    "test_gaps": [],
                    "read_only_claim": True,
                    "confidence": "medium",
                }
            return {
                "reviewer": reviewer,
                "verdict": "SAFE",
                "summary": f"{reviewer} inspected the target.",
                "files_inspected": [str(target)],
                "evidence": ["target.py returns 42"],
                "evidence_citations": [_target_citation("target.py returns 42", "verdict")],
                "findings": [],
                "test_gaps": [],
                "read_only_claim": True,
                "confidence": "medium",
            }

    monkeypatch.setattr(parallel_review_module, "ScillmReviewerAdapter", FakeScillmReviewerAdapter)
    monkeypatch.setattr(ask_module.SessionWriter, "write", lambda self: None)
    monkeypatch.setattr(ask_module, "_record_ask_telemetry", lambda **kwargs: None)

    result = CliRunner().invoke(
        ask_module.app,
        [
            "review",
            "target",
            "--parallel-review",
            "--review-target",
            str(target),
            "--parallel-review-personas",
            "Brandon,Margaret,Jennifer",
            "--parallel-reviewers",
            "3",
            "--ask-id",
            "parallel-dag",
            "--run-output-root",
            str(tmp_path),
        ],
    )

    assert result.exit_code == 0
    assert set(calls[:3]) == {"Brandon", "Margaret", "Jennifer"}
    assert calls[-1] == "review-judge"
    status = read_status("parallel-dag", tail_events=20, output_root=tmp_path)
    artifacts = status["artifacts"]
    verdict = json.loads((tmp_path / "parallel-dag" / "parallel_review" / "verdict.json").read_text())
    assert status["state"] == "answered"
    assert artifacts["judge_json"].endswith("judge.json")
    assert verdict["best_reviewer"] == "Brandon"
    assert verdict["verifier"]["status"] == "PASS"


def test_cli_parallel_review_writes_code_runner_handoff_when_requested(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    target = tmp_path / "target.py"
    target.write_text("def answer():\n    return 42\n")

    class FakeScillmReviewerAdapter:
        def __init__(self, **kwargs):
            pass

        async def review(self, payload):
            reviewer = payload["reviewer"]["name"]
            finding = {
                "severity": "medium",
                "title": "Add regression test",
                "evidence": "target.py has behavior but no adjacent test in the target bundle.",
                "evidence_citations": [_target_citation("target.py has behavior but no adjacent test in the target bundle.", "finding")],
                "impact": "Behavior can regress silently.",
                "fix": "Add a focused regression test for answer().",
                "verification": "Run the new test file.",
            }
            if reviewer == "review-judge":
                return {
                    "reviewer": "review-judge",
                    "judge": "review-judge",
                    "best_reviewer": "Brandon",
                    "best_review_reason": "Only reviewer with a complete finding.",
                    "hybrid_summary": "Add the missing regression test before relying on this behavior.",
                    "verdict": "SAFE_WITH_CONDITIONS",
                    "summary": "Judge synthesis complete.",
                    "files_inspected": [str(target)],
                    "evidence": ["target.py has answer()"],
                    "evidence_citations": [_target_citation("target.py has answer()", "verdict")],
                    "findings": [finding],
                    "test_gaps": ["answer() lacks a regression test"],
                    "read_only_claim": True,
                    "confidence": "medium",
                }
            return {
                "reviewer": reviewer,
                "verdict": "SAFE_WITH_CONDITIONS",
                "summary": f"{reviewer} found a test gap.",
                "files_inspected": [str(target)],
                "evidence": ["target.py has answer()"],
                "evidence_citations": [_target_citation("target.py has answer()", "verdict")],
                "findings": [finding] if reviewer == "Brandon" else [],
                "test_gaps": ["answer() lacks a regression test"],
                "read_only_claim": True,
                "confidence": "medium",
            }

    monkeypatch.setattr(parallel_review_module, "ScillmReviewerAdapter", FakeScillmReviewerAdapter)
    monkeypatch.setattr(ask_module.SessionWriter, "write", lambda self: None)
    monkeypatch.setattr(ask_module, "_record_ask_telemetry", lambda **kwargs: None)

    result = CliRunner().invoke(
        ask_module.app,
        [
            "review",
            "target",
            "--parallel-review",
            "--review-target",
            str(target),
            "--parallel-review-personas",
            "Brandon,Margaret,Jennifer",
            "--code-runner-handoff",
            "--ask-id",
            "parallel-handoff",
            "--run-output-root",
            str(tmp_path),
        ],
    )

    assert result.exit_code == 0
    handoff = tmp_path / "parallel-handoff" / "parallel_review" / "code_runner_handoff.md"
    task_path = tmp_path / "parallel-handoff" / "parallel_review" / "code_runner_task.json"
    verdict = json.loads((tmp_path / "parallel-handoff" / "parallel_review" / "verdict.json").read_text())
    assert handoff.exists()
    assert not task_path.exists()
    assert "Add regression test" in handoff.read_text()
    assert verdict["artifact_paths"]["code_runner_handoff"] == str(handoff)
    assert "code_runner_task_json" not in verdict["artifact_paths"]


def test_cli_parallel_review_apply_fixes_prepares_code_runner_task_without_editing(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    target = tmp_path / "target.py"
    target.write_text("def answer():\n    return 42\n")

    class FakeScillmReviewerAdapter:
        def __init__(self, **kwargs):
            pass

        async def review(self, payload):
            reviewer = payload["reviewer"]["name"]
            finding = {
                "severity": "medium",
                "title": "Add regression test",
                "evidence": "target.py has behavior but no adjacent test in the target bundle.",
                "evidence_citations": [_target_citation("target.py has behavior but no adjacent test in the target bundle.", "finding")],
                "impact": "Behavior can regress silently.",
                "fix": "Add a focused regression test for answer().",
                "verification": "uv run pytest tests/test_target.py",
            }
            if reviewer == "review-judge":
                return {
                    "reviewer": "review-judge",
                    "judge": "review-judge",
                    "best_reviewer": "Brandon",
                    "best_review_reason": "Only reviewer with a complete finding.",
                    "hybrid_summary": "Add the missing regression test before relying on this behavior.",
                    "verdict": "SAFE_WITH_CONDITIONS",
                    "summary": "Judge synthesis complete.",
                    "files_inspected": [str(target)],
                    "evidence": ["target.py has answer()"],
                    "evidence_citations": [_target_citation("target.py has answer()", "verdict")],
                    "findings": [finding],
                    "test_gaps": ["answer() lacks a regression test"],
                    "read_only_claim": True,
                    "confidence": "medium",
                }
            return {
                "reviewer": reviewer,
                "verdict": "SAFE_WITH_CONDITIONS",
                "summary": f"{reviewer} found a test gap.",
                "files_inspected": [str(target)],
                "evidence": ["target.py has answer()"],
                "evidence_citations": [_target_citation("target.py has answer()", "verdict")],
                "findings": [finding] if reviewer == "Brandon" else [],
                "test_gaps": ["answer() lacks a regression test"],
                "read_only_claim": True,
                "confidence": "medium",
            }

    monkeypatch.setattr(parallel_review_module, "ScillmReviewerAdapter", FakeScillmReviewerAdapter)
    monkeypatch.setattr(ask_module.SessionWriter, "write", lambda self: None)
    monkeypatch.setattr(ask_module, "_record_ask_telemetry", lambda **kwargs: None)

    result = CliRunner().invoke(
        ask_module.app,
        [
            "review",
            "and",
            "fix",
            "target",
            "--parallel-review",
            "--review-target",
            str(target),
            "--parallel-review-personas",
            "Brandon,Margaret,Jennifer",
            "--apply-fixes",
            "--code-runner-dod-command",
            "uv run pytest tests/test_target.py",
            "--implementation-non-goal",
            "Do not change public API.",
            "--implementation-risk-note",
            "Keep fix scoped to answer().",
            "--ask-id",
            "parallel-apply-fixes",
            "--run-output-root",
            str(tmp_path),
            "--json",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    task_path = tmp_path / "parallel-apply-fixes" / "parallel_review" / "code_runner_task.json"
    task = json.loads(task_path.read_text())
    assert payload["parallel_review"]["implementation_requested"] is True
    assert task["execution"]["requested"] is True
    assert task["execution"]["backend"] == "code-runner"
    assert task["execution"]["status"] == "prepared_not_executable"
    assert task["code_runner_invocation"]["status"] == "not_generated"
    assert task["definition_of_done"]["commands"] == ["uv run pytest tests/test_target.py"]
    assert task["non_goals"] == ["Do not change public API."]
    assert task["risk_notes"] == ["Keep fix scoped to answer()."]
    assert target.read_text() == "def answer():\n    return 42\n"


def test_cli_parallel_review_apply_fixes_requires_explicit_dod_command(tmp_path):
    target = tmp_path / "target.py"
    target.write_text("def answer():\n    return 42\n")

    result = CliRunner().invoke(
        ask_module.app,
        [
            "review",
            "and",
            "fix",
            "target",
            "--parallel-review",
            "--review-target",
            str(target),
            "--apply-fixes",
            "--ask-id",
            "unsafe-inferred-dod",
            "--run-output-root",
            str(tmp_path),
            "--json",
        ],
    )

    assert result.exit_code == 2
    payload = json.loads(result.stdout)
    assert payload["needs_attention"]["reason"] == "missing_code_runner_dod"
    task_path = tmp_path / "unsafe-inferred-dod" / "parallel_review" / "code_runner_task.json"
    assert not task_path.exists()


def test_cli_parallel_review_allowed_file_rejects_outside_repo(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    target = tmp_path / "target.py"
    target.write_text("def answer():\n    return 42\n")
    outside = tmp_path.parent / "outside.py"
    outside.write_text("secret = True\n")

    result = CliRunner().invoke(
        ask_module.app,
        [
            "review",
            "and",
            "fix",
            "target",
            "--parallel-review",
            "--review-target",
            str(target),
            "--apply-fixes",
            "--code-runner-allowed-file",
            str(outside),
            "--code-runner-dod-command",
            "pytest",
        ],
    )

    assert result.exit_code != 0
    assert "allowed file outside" in result.output
    assert "repository" in result.output


def test_cli_parallel_review_rejects_unknown_implementation_backend(tmp_path):
    result = CliRunner().invoke(
        ask_module.app,
        [
            "review",
            "target",
            "--parallel-review",
            "--review-target",
            "git:diff",
            "--implement-with",
            "pi-subagents",
        ],
    )

    assert result.exit_code != 0
    assert "scillm-agent is supported" in result.output


def test_cli_code_runner_handoff_requires_parallel_review():
    result = CliRunner().invoke(
        ask_module.app,
        [
            "review",
            "target",
            "--apply-fixes",
        ],
    )

    assert result.exit_code != 0
    assert "Implementation handoff options require" in result.output


def test_parallel_review_verifier_rejects_missing_judge():
    result = parallel_review_module.verify_parallel_review_bundle(
        {
            "schema_version": parallel_review_module.PARALLEL_REVIEW_SCHEMA_VERSION,
            "verdict": "SAFE",
            "target_reviewed": "target.py",
            "read_only": True,
            "reviewers": [
                {
                    "reviewer": "Brandon",
                    "verdict": "SAFE",
                    "summary": "ok",
                    "evidence": ["target.py"],
                    "evidence_citations": [_target_citation("target.py", "verdict")],
                    "files_inspected": ["target.py"],
                    "read_only_claim": True,
                    "findings": [],
                }
            ],
            "files_inspected": ["target.py"],
            "execution": {"unexpected_file_changes": []},
        }
    )

    assert result["status"] == "FAIL"
    assert "missing judge output" in result["failures"]


def _valid_parallel_safe_verdict():
    metadata = {
        "ask_id": "parallel-metadata",
        "protocol": "parallel_review",
        "node_id": "reviewer-1",
        "batch_id": "ask-parallel_review-parallel-metadata",
        "item_id": "reviewer-1",
    }
    target_citation = {
        "source_id": "TARGET_BUNDLE",
        "source_kind": "target_bundle",
        "quote_or_summary": "target.py is fine",
        "supports": "verdict",
    }
    return {
        "schema_version": parallel_review_module.PARALLEL_REVIEW_SCHEMA_VERSION,
        "verdict": "SAFE",
        "target_reviewed": "target.py",
        "read_only": True,
        "target_bundle": {
            "entries": [{"target": "target.py", "path": "target.py", "kind": "file"}],
            "truncated": False,
        },
        "source_bundle": {
            "sources": [
                {"source_id": "TARGET_BUNDLE", "kind": "target_bundle", "content": "target.py is fine"},
            ],
        },
        "evidence_citations": [target_citation],
        "reviewers": [
            {
                "reviewer": "Brandon",
                "verdict": "SAFE",
                "summary": "Looks fine.",
                "files_inspected": ["target.py"],
                "evidence": ["target.py is fine"],
                "evidence_citations": [_target_citation("target.py is fine", "verdict")],
                "findings": [],
                "read_only_claim": True,
                "scillm": {
                    "source_grounding_status": "requested",
                    "grounding_passed": True,
                    "metadata_requested": dict(metadata),
                    "metadata_returned": dict(metadata),
                },
            }
        ],
        "judge": {
            "best_reviewer": "Brandon",
            "verdict": "SAFE",
            "hybrid_summary": "Safe.",
            "evidence_citations": [target_citation],
            "scillm": {
                "source_grounding_status": "requested",
                "grounding_passed": True,
                "metadata_requested": {**metadata, "node_id": "judge", "item_id": "judge"},
                "metadata_returned": {**metadata, "node_id": "judge", "item_id": "judge"},
            },
        },
        "files_inspected": ["target.py"],
        "execution": {"unexpected_file_changes": []},
    }


def test_parallel_review_verifier_rejects_safe_when_grounding_fell_back():
    verdict = _valid_parallel_safe_verdict()
    verdict["reviewers"][0]["scillm"]["source_grounding_status"] = "retry_without_source_after_error"
    verdict["reviewers"][0]["scillm"]["grounding_passed"] = False

    result = parallel_review_module.verify_parallel_review_bundle(verdict)

    assert result["status"] == "FAIL"
    assert result["grounding_degraded"] is True
    assert "safe verdict requires successful source grounding" in result["failures"]


def test_parallel_review_verifier_rejects_scillm_metadata_return_mismatch():
    verdict = _valid_parallel_safe_verdict()
    verdict["reviewers"][0]["scillm"]["metadata_returned"]["node_id"] = "wrong-reviewer"

    result = parallel_review_module.verify_parallel_review_bundle(verdict)

    assert result["status"] == "FAIL"
    assert any("metadata" in failure for failure in result["failures"])


def test_parallel_review_safe_requires_structured_target_citation():
    verdict = _valid_parallel_safe_verdict()
    verdict["evidence_citations"] = []
    verdict["reviewers"][0]["evidence_citations"] = []
    verdict["judge"]["evidence_citations"] = []

    result = parallel_review_module.verify_parallel_review_bundle(verdict)

    assert result["status"] == "FAIL"
    assert any("structured citation" in failure for failure in result["failures"])


def test_parallel_review_safe_rejects_memory_only_citation():
    verdict = _valid_parallel_safe_verdict()
    memory_citation = {
        "source_id": "MEMORY.1",
        "source_kind": "memory",
        "quote_or_summary": "Memory says it is safe.",
        "supports": "verdict",
    }
    verdict["source_bundle"]["sources"].append({"source_id": "MEMORY.1", "kind": "memory", "content": "Memory says it is safe."})
    verdict["evidence_citations"] = [memory_citation]
    verdict["reviewers"][0]["evidence_citations"] = [memory_citation]
    verdict["judge"]["evidence_citations"] = [memory_citation]

    result = parallel_review_module.verify_parallel_review_bundle(verdict)

    assert result["status"] == "FAIL"
    assert any("inadmissible source_kind memory" in failure for failure in result["failures"])


def test_parallel_review_rejects_target_outside_review_root(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    secret = tmp_path / "secret.env"
    secret.write_text("API_KEY=super-secret\n")

    with pytest.raises(parallel_review_module.ParallelReviewError):
        parallel_review_module.build_target_bundle(str(secret), review_root=root)


def test_parallel_review_rejects_symlink_target_outside_review_root(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    secret = tmp_path / "secret.env"
    secret.write_text("API_KEY=super-secret\n")
    link = root / "secret.env"
    link.symlink_to(secret)

    with pytest.raises(parallel_review_module.ParallelReviewError):
        parallel_review_module.build_target_bundle(str(link), review_root=root)


def test_parallel_review_redacts_obvious_secrets(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    target = root / "config.env"
    target.write_text("API_KEY=super-secret\npassword = hunter2\n")

    bundle = parallel_review_module.build_target_bundle(str(target), review_root=root)

    assert "super-secret" not in bundle["markdown"]
    assert "hunter2" not in bundle["markdown"]
    assert "[REDACTED]" in bundle["markdown"]


def test_verifier_rejects_safe_verdict_for_unresolved_target():
    verdict = {
        "schema_version": parallel_review_module.PARALLEL_REVIEW_SCHEMA_VERSION,
        "verdict": "SAFE",
        "target_reviewed": "missing.py",
        "read_only": True,
        "target_bundle": {
            "entries": [{"target": "missing.py", "kind": "declared"}],
            "truncated": False,
        },
        "reviewers": [
            {
                "reviewer": "Brandon",
                "verdict": "SAFE",
                "summary": "Looks fine.",
                "files_inspected": ["missing.py"],
                "evidence": ["missing.py is fine"],
                "evidence_citations": [_target_citation("missing.py is fine", "verdict")],
                "findings": [],
                "read_only_claim": True,
            }
        ],
        "judge": {
            "best_reviewer": "Brandon",
            "hybrid_summary": "Safe.",
        },
        "files_inspected": ["missing.py"],
        "execution": {"unexpected_file_changes": []},
    }

    result = parallel_review_module.verify_parallel_review_bundle(verdict)

    assert result["status"] == "FAIL"
    assert any("declared target" in failure for failure in result["failures"])


def test_verifier_rejects_safe_verdict_for_directory_only_target():
    verdict = {
        "schema_version": parallel_review_module.PARALLEL_REVIEW_SCHEMA_VERSION,
        "verdict": "SAFE",
        "target_reviewed": "src",
        "read_only": True,
        "target_bundle": {
            "entries": [{"target": "src", "kind": "directory"}],
            "truncated": False,
        },
        "reviewers": [
            {
                "reviewer": "Brandon",
                "verdict": "SAFE",
                "summary": "Looks fine.",
                "files_inspected": ["src"],
                "evidence": ["src is fine"],
                "evidence_citations": [_target_citation("src is fine", "verdict")],
                "findings": [],
                "read_only_claim": True,
            }
        ],
        "judge": {"best_reviewer": "Brandon", "hybrid_summary": "Safe."},
        "files_inspected": ["src"],
        "execution": {"unexpected_file_changes": []},
    }

    result = parallel_review_module.verify_parallel_review_bundle(verdict)

    assert result["status"] == "FAIL"
    assert any("directory target" in failure for failure in result["failures"])


def test_verifier_rejects_safe_verdict_for_truncated_target_bundle():
    verdict = {
        "schema_version": parallel_review_module.PARALLEL_REVIEW_SCHEMA_VERSION,
        "verdict": "SAFE",
        "target_reviewed": "target.py",
        "read_only": True,
        "target_bundle": {
            "entries": [{"target": "target.py", "path": "target.py", "kind": "file"}],
            "truncated": True,
        },
        "reviewers": [
            {
                "reviewer": "Brandon",
                "verdict": "SAFE",
                "summary": "Looks fine.",
                "files_inspected": ["target.py"],
                "evidence": ["target.py is fine"],
                "evidence_citations": [_target_citation("target.py is fine", "verdict")],
                "findings": [],
                "read_only_claim": True,
            }
        ],
        "judge": {"best_reviewer": "Brandon", "hybrid_summary": "Safe."},
        "files_inspected": ["target.py"],
        "execution": {"unexpected_file_changes": []},
    }

    result = parallel_review_module.verify_parallel_review_bundle(verdict)

    assert result["status"] == "FAIL"
    assert "safe verdict requires untruncated target_bundle" in result["failures"]


def test_verifier_rejects_files_inspected_outside_target_bundle():
    verdict = {
        "schema_version": parallel_review_module.PARALLEL_REVIEW_SCHEMA_VERSION,
        "verdict": "SAFE",
        "target_reviewed": "target.py",
        "read_only": True,
        "target_bundle": {
            "entries": [{"target": "target.py", "path": "target.py", "kind": "file"}],
            "truncated": False,
        },
        "reviewers": [
            {
                "reviewer": "Brandon",
                "verdict": "SAFE",
                "summary": "Looks fine.",
                "files_inspected": ["other.py"],
                "evidence": ["other.py is fine"],
                "evidence_citations": [_target_citation("other.py is fine", "verdict")],
                "findings": [],
                "read_only_claim": True,
            }
        ],
        "judge": {"best_reviewer": "Brandon", "hybrid_summary": "Safe."},
        "files_inspected": ["other.py"],
        "execution": {"unexpected_file_changes": []},
    }

    result = parallel_review_module.verify_parallel_review_bundle(verdict)

    assert result["status"] == "FAIL"
    assert any("outside target bundle" in failure for failure in result["failures"])


def test_judge_best_and_hybrid_produce_distinct_judge_prompts():
    kwargs = {
        "question": "review target",
        "target": "target.py",
        "reviewers": 3,
        "personas": "Brandon,Margaret,Jennifer",
        "focus": None,
        "runner": "scillm",
        "read_only": True,
        "model": "text",
    }
    outputs = [{"reviewer": "Brandon", "verdict": "SAFE", "summary": "ok", "evidence": ["target.py"]}]
    plan_best = parallel_review_module.build_parallel_review_plan(**kwargs, dag_mode="judge-best")
    plan_hybrid = parallel_review_module.build_parallel_review_plan(**kwargs, dag_mode="hybrid")

    assert parallel_review_module.build_judge_prompt(plan_best, outputs) != parallel_review_module.build_judge_prompt(plan_hybrid, outputs)


def test_parse_reviewer_output_normalizes_list_fields():
    payload = {
        "reviewer": {
            "name": "Brandon",
            "role": "correctness",
        }
    }
    parsed = parallel_review_module.parse_reviewer_output(
        json.dumps(
            {
                "verdict": "safe",
                "summary": "Inspected the target.",
                "files_inspected": "target.py",
                "evidence": "target.py returns 42",
                "findings": "not a finding object",
                "test_gaps": {"title": "missing regression test"},
            }
        ),
        payload,
    )

    assert parsed["verdict"] == "SAFE"
    assert parsed["files_inspected"] == ["target.py"]
    assert parsed["evidence"] == ["target.py returns 42"]
    assert parsed["findings"] == []
    assert parsed["test_gaps"] == ["{'title': 'missing regression test'}"]


def test_cli_parallel_review_verifier_failure_exits_needs_attention(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    target = tmp_path / "target.py"
    target.write_text("def answer():\n    return 42\n")

    class FakeScillmReviewerAdapter:
        def __init__(self, **kwargs):
            pass

        async def review(self, payload):
            reviewer = payload["reviewer"]["name"]
            if reviewer == "review-judge":
                return {
                    "reviewer": "review-judge",
                    "judge": "review-judge",
                    "verdict": "SAFE",
                    "summary": "Judge response omitted required synthesis fields.",
                    "files_inspected": [str(target)],
                    "evidence": ["target.py returns 42"],
                    "evidence_citations": [_target_citation("target.py returns 42", "verdict")],
                    "findings": [],
                    "test_gaps": [],
                    "read_only_claim": True,
                    "confidence": "medium",
                }
            return {
                "reviewer": reviewer,
                "verdict": "SAFE",
                "summary": f"{reviewer} inspected the target.",
                "files_inspected": [str(target)],
                "evidence": ["target.py returns 42"],
                "evidence_citations": [_target_citation("target.py returns 42", "verdict")],
                "findings": [],
                "test_gaps": [],
                "read_only_claim": True,
                "confidence": "medium",
            }

    monkeypatch.setattr(parallel_review_module, "ScillmReviewerAdapter", FakeScillmReviewerAdapter)
    monkeypatch.setattr(ask_module.SessionWriter, "write", lambda self: None)
    monkeypatch.setattr(ask_module, "_record_ask_telemetry", lambda **kwargs: None)

    result = CliRunner().invoke(
        ask_module.app,
        [
            "review",
            "target",
            "--parallel-review",
            "--review-target",
            str(target),
            "--parallel-review-personas",
            "Brandon,Margaret,Jennifer",
            "--ask-id",
            "parallel-verifier-fail",
            "--run-output-root",
            str(tmp_path),
            "--json",
        ],
    )

    assert result.exit_code == 2
    payload = json.loads(result.stdout)
    status = read_status("parallel-verifier-fail", tail_events=20, output_root=tmp_path)
    verdict = json.loads((tmp_path / "parallel-verifier-fail" / "parallel_review" / "verdict.json").read_text())
    assert payload["needs_attention"]["reason"] == "parallel_review_verifier_failed"
    assert payload["needs_attention"]["safe_default"] == "do_not_trust_review"
    assert "judge missing best_reviewer" in payload["needs_attention"]["verifier_failures"]
    assert status["state"] == "needs_attention"
    assert status["needs_attention"]["reason"] == "parallel_review_verifier_failed"
    assert verdict["verifier"]["status"] == "FAIL"


def test_parallel_review_events_include_each_reviewer(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    target = tmp_path / "target.py"
    target.write_text("def answer():\n    return 42\n")

    class FakeScillmReviewerAdapter:
        def __init__(self, **kwargs):
            pass

        async def review(self, payload):
            reviewer = payload["reviewer"]["name"]
            if reviewer == "review-judge":
                return {
                    "reviewer": "review-judge",
                    "judge": "review-judge",
                    "best_reviewer": "Brandon",
                    "best_review_reason": "Best evidence.",
                    "hybrid_summary": "All reviewers inspected target.py.",
                    "verdict": "SAFE",
                    "summary": "Judge synthesis.",
                    "files_inspected": [str(target)],
                    "evidence": ["target.py returns 42"],
                    "evidence_citations": [_target_citation("target.py returns 42", "verdict")],
                    "findings": [],
                    "test_gaps": [],
                    "read_only_claim": True,
                }
            return {
                "reviewer": reviewer,
                "verdict": "SAFE",
                "summary": f"{reviewer} inspected target.py.",
                "files_inspected": [str(target)],
                "evidence": ["target.py returns 42"],
                "evidence_citations": [_target_citation("target.py returns 42", "verdict")],
                "findings": [],
                "test_gaps": [],
                "read_only_claim": True,
            }

    monkeypatch.setattr(parallel_review_module, "ScillmReviewerAdapter", FakeScillmReviewerAdapter)
    monkeypatch.setattr(ask_module.SessionWriter, "write", lambda self: None)
    monkeypatch.setattr(ask_module, "_record_ask_telemetry", lambda **kwargs: None)

    result = CliRunner().invoke(
        ask_module.app,
        [
            "review",
            "target",
            "--parallel-review",
            "--review-target",
            str(target),
            "--parallel-review-personas",
            "Brandon,Margaret,Jennifer",
            "--ask-id",
            "parallel-events",
            "--run-output-root",
            str(tmp_path),
        ],
    )

    assert result.exit_code == 0
    status = read_status("parallel-events", tail_events=80, output_root=tmp_path)
    events = [event["event"] for event in status["event_tail"]]
    assert events.count("reviewer_started") == 3
    assert events.count("reviewer_finished") == 3
    assert "judge_started" in events
    assert "judge_finished" in events
    assert "verifier_started" in events
    assert "verifier_finished" in events


def test_parallel_review_reviewer_calls_overlap(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    target = tmp_path / "target.py"
    target.write_text("def answer():\n    return 42\n")
    started = {}
    finished = {}

    class FakeScillmReviewerAdapter:
        def __init__(self, **kwargs):
            pass

        async def review(self, payload):
            reviewer = payload["reviewer"]["name"]
            if reviewer == "review-judge":
                return {
                    "reviewer": "review-judge",
                    "judge": "review-judge",
                    "best_reviewer": "Brandon",
                    "best_review_reason": "Best evidence.",
                    "hybrid_summary": "All reviewers inspected target.py.",
                    "verdict": "SAFE",
                    "summary": "Judge synthesis.",
                    "files_inspected": [str(target)],
                    "evidence": ["target.py returns 42"],
                    "evidence_citations": [_target_citation("target.py returns 42", "verdict")],
                    "findings": [],
                    "test_gaps": [],
                    "read_only_claim": True,
                }
            started[reviewer] = time.monotonic()
            await asyncio.sleep(0.05)
            finished[reviewer] = time.monotonic()
            return {
                "reviewer": reviewer,
                "verdict": "SAFE",
                "summary": f"{reviewer} inspected target.py.",
                "files_inspected": [str(target)],
                "evidence": ["target.py returns 42"],
                "evidence_citations": [_target_citation("target.py returns 42", "verdict")],
                "findings": [],
                "test_gaps": [],
                "read_only_claim": True,
            }

    monkeypatch.setattr(parallel_review_module, "ScillmReviewerAdapter", FakeScillmReviewerAdapter)
    monkeypatch.setattr(ask_module.SessionWriter, "write", lambda self: None)
    monkeypatch.setattr(ask_module, "_record_ask_telemetry", lambda **kwargs: None)

    result = CliRunner().invoke(
        ask_module.app,
        [
            "review",
            "target",
            "--parallel-review",
            "--review-target",
            str(target),
            "--parallel-review-personas",
            "Brandon,Margaret,Jennifer",
            "--ask-id",
            "parallel-overlap",
            "--run-output-root",
            str(tmp_path),
        ],
    )

    assert result.exit_code == 0
    assert len(started) == 3
    assert max(started.values()) < min(finished.values())


def test_parallel_review_single_reviewer_failure_preserves_artifacts(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    target = tmp_path / "target.py"
    target.write_text("def answer():\n    return 42\n")

    class FakeScillmReviewerAdapter:
        def __init__(self, **kwargs):
            pass

        async def review(self, payload):
            reviewer = payload["reviewer"]["name"]
            if reviewer == "Margaret":
                raise RuntimeError("model unavailable")
            if reviewer == "review-judge":
                return {
                    "reviewer": "review-judge",
                    "judge": "review-judge",
                    "best_reviewer": "Brandon",
                    "best_review_reason": "Best evidence.",
                    "hybrid_summary": "One reviewer failed; outputs are incomplete.",
                    "verdict": "INSUFFICIENT_EVIDENCE",
                    "summary": "Judge synthesis.",
                    "files_inspected": [str(target)],
                    "evidence": ["target.py returns 42"],
                    "evidence_citations": [_target_citation("target.py returns 42", "verdict")],
                    "findings": [],
                    "test_gaps": [],
                    "read_only_claim": True,
                }
            return {
                "reviewer": reviewer,
                "verdict": "SAFE",
                "summary": f"{reviewer} inspected target.py.",
                "files_inspected": [str(target)],
                "evidence": ["target.py returns 42"],
                "evidence_citations": [_target_citation("target.py returns 42", "verdict")],
                "findings": [],
                "test_gaps": [],
                "read_only_claim": True,
            }

    monkeypatch.setattr(parallel_review_module, "ScillmReviewerAdapter", FakeScillmReviewerAdapter)
    monkeypatch.setattr(ask_module.SessionWriter, "write", lambda self: None)
    monkeypatch.setattr(ask_module, "_record_ask_telemetry", lambda **kwargs: None)

    result = CliRunner().invoke(
        ask_module.app,
        [
            "review",
            "target",
            "--parallel-review",
            "--review-target",
            str(target),
            "--parallel-review-personas",
            "Brandon,Margaret,Jennifer",
            "--ask-id",
            "parallel-reviewer-failure",
            "--run-output-root",
            str(tmp_path),
            "--json",
        ],
    )

    assert result.exit_code == 2
    review_dir = tmp_path / "parallel-reviewer-failure" / "parallel_review"
    verdict = json.loads((review_dir / "verdict.json").read_text())
    verifier_log = (review_dir / "verifier.log").read_text()
    status = read_status("parallel-reviewer-failure", tail_events=80, output_root=tmp_path)
    events = [event["event"] for event in status["event_tail"]]
    assert (review_dir / "reviewer_outputs").exists()
    assert verdict["verifier"]["status"] == "FAIL"
    assert "Margaret: reviewer failed" in verifier_log
    assert status["state"] == "needs_attention"
    assert "reviewer_failed" in events


def test_cli_parallel_review_rejects_unbounded_fanout(tmp_path):
    result = CliRunner().invoke(
        ask_module.app,
        [
            "review",
            "target",
            "--parallel-review",
            "--review-target",
            "git:diff",
            "--parallel-reviewers",
            "50",
            "--run-output-root",
            str(tmp_path),
        ],
    )

    assert result.exit_code != 0
    assert "Parallel reviewers must be <= 7" in result.output


def test_cli_parallel_review_rejects_unknown_runner(tmp_path):
    result = CliRunner().invoke(
        ask_module.app,
        [
            "review",
            "target",
            "--parallel-review",
            "--review-target",
            "git:diff",
            "--parallel-review-runner",
            "codex",
            "--run-output-root",
            str(tmp_path),
        ],
    )

    assert result.exit_code != 0
    assert "Only the scillm parallel-review" in result.output
    assert "runner is implemented" in result.output


def test_cli_parallel_review_rejects_unknown_dag_mode(tmp_path):
    result = CliRunner().invoke(
        ask_module.app,
        [
            "review",
            "target",
            "--parallel-review",
            "--review-target",
            "git:diff",
            "--review-dag",
            "shell",
            "--run-output-root",
            str(tmp_path),
        ],
    )

    assert result.exit_code != 0
    assert "Review DAG must be judge-best or hybrid" in result.output


def test_doctor_reports_runtime_sections():
    result = run_doctor()

    assert result["status"] in {"pass", "fail"}
    assert result["run_root"]
    assert any(check["name"] == "artifact_root_writable" for check in result["checks"])
    assert any(check["name"] == "runtime_artifact_schema" for check in result["checks"])
    assert any(check["name"] == "skill:memory" for check in result["checks"])
    lane_health = {item["lane"]: item for item in result["oracle_lane_health"]}
    assert {"auto", "scillm", "subagent-runner", "cursor-browser"} <= set(lane_health)
    assert "webgpt" not in lane_health
    assert all(item["state"] in {"available", "needs_attention", "blocked"} for item in lane_health.values())


def test_doctor_lane_health_marks_failed_live_scillm_needs_attention(monkeypatch):
    import ask.doctor as doctor_module

    monkeypatch.setattr(doctor_module, "_skill_path", lambda name: Path("/tmp/fake-run.sh"))
    result = doctor_module.build_oracle_lane_health([
        {
            "name": "live:scillm",
            "ok": False,
            "detail": "Could not determine current text model from proxy config",
        }
    ])
    lane_health = {item["lane"]: item for item in result}

    assert lane_health["scillm"]["state"] == "needs_attention"
    assert lane_health["scillm"]["safe_default"] == "do_not_claim_lane_ready"


def test_doctor_lane_health_marks_missing_cursor_bridge_needs_attention(monkeypatch):
    import ask.doctor as doctor_module

    monkeypatch.setattr(doctor_module, "_skill_path", lambda name: Path("/tmp/fake-run.sh"))
    result = doctor_module.build_oracle_lane_health([])
    lane_health = {item["lane"]: item for item in result}

    if not Path("/tmp/cursor-browser-bridge-port").exists():
        assert lane_health["cursor-browser"]["state"] == "needs_attention"
        assert "cursor-browser-bridge" in lane_health["cursor-browser"]["detail"]


def test_list_runs_returns_recent_statuses(tmp_path):
    older = AskRunState("older", output_root=tmp_path)
    older.write_request({"question": "older"})
    older.finish({"question": "older", "items": []})
    newer = AskRunState("newer", output_root=tmp_path)
    newer.write_request({"question": "newer"})
    newer.finish({"question": "newer", "items": [{"solution": "ok"}]})

    runs = list_runs(output_root=tmp_path, limit=2)

    assert {run["ask_id"] for run in runs} == {"older", "newer"}
    assert all("_status_path" in run for run in runs)


def test_runtime_index_is_append_only_and_powers_runs_listing(tmp_path):
    run = AskRunState("indexed", output_root=tmp_path)
    run.write_request({"command": "ask", "question": "indexed"})
    run.finish({"question": "indexed", "items": [{"solution": "ok"}]})

    index_path = tmp_path / "index.jsonl"
    runs = list_runs(output_root=tmp_path, limit=1)

    assert index_path.exists()
    assert len(index_path.read_text().splitlines()) >= 2
    assert runs[0]["ask_id"] == "indexed"


def test_prune_runs_removes_old_run_dirs(tmp_path):
    old = AskRunState("old-run", output_root=tmp_path)
    old.write_request({"question": "old"})
    old.finish({"question": "old", "items": []})
    new = AskRunState("new-run", output_root=tmp_path)
    new.write_request({"question": "new"})
    new.finish({"question": "new", "items": []})
    age_run_status(old)

    preview = prune_runs(output_root=tmp_path, older_than_days=14, dry_run=True)
    result = prune_runs(output_root=tmp_path, older_than_days=14)

    assert str(old.run_dir) in preview["removed"]
    assert str(old.run_dir) in result["removed"]
    assert not old.run_dir.exists()
    assert new.run_dir.exists()


def test_prune_runs_keeps_old_running_run(tmp_path):
    run = AskRunState("old-running", output_root=tmp_path)
    run.write_request({"question": "still running"})
    run.update("running", current_step="oracle")
    old_time = time.time() - 30 * 24 * 60 * 60
    os.utime(run.run_dir, (old_time, old_time))

    result = prune_runs(output_root=tmp_path, older_than_days=14)

    assert run.run_dir.exists()
    assert str(run.run_dir) in result["kept"]
    assert str(run.run_dir) not in result["removed"]


def test_prune_runs_uses_status_updated_at_not_directory_mtime(tmp_path):
    run = AskRunState("recent-status-old-dir", output_root=tmp_path)
    run.write_request({"question": "recent status"})
    run.finish({"question": "recent status", "items": []})
    old_time = time.time() - 30 * 24 * 60 * 60
    os.utime(run.run_dir, (old_time, old_time))

    result = prune_runs(output_root=tmp_path, older_than_days=14)

    assert run.run_dir.exists()
    assert str(run.run_dir) in result["kept"]
    assert str(run.run_dir) not in result["removed"]


def test_prune_runs_falls_back_to_status_file_mtime_for_malformed_updated_at(tmp_path):
    run = AskRunState("malformed-updated-at", output_root=tmp_path)
    run.write_request({"question": "old status file"})
    run.finish({"question": "old status file", "items": []})
    old_time = time.time() - 30 * 24 * 60 * 60
    payload = json.loads(run.status_path.read_text())
    payload["updated_at"] = "not-a-timestamp"
    run.status_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    os.utime(run.status_path, (old_time, old_time))

    result = prune_runs(output_root=tmp_path, older_than_days=14)

    assert str(run.run_dir) in result["removed"]
    assert not run.run_dir.exists()


def test_prune_runs_keeps_unrecognized_old_dirs(tmp_path):
    unrelated = tmp_path / "unrelated-old-dir"
    unrelated.mkdir()
    old_time = time.time() - 30 * 24 * 60 * 60
    os.utime(unrelated, (old_time, old_time))

    result = prune_runs(output_root=tmp_path, older_than_days=14)

    assert unrelated.exists()
    assert str(unrelated) not in result["removed"]
    assert str(unrelated) in result["kept"]


def test_prune_runs_keeps_malformed_and_mismatched_status_dirs(tmp_path):
    malformed = tmp_path / "malformed"
    malformed.mkdir()
    (malformed / "malformed.status.json").write_text("{not-json")
    mismatch = tmp_path / "mismatch"
    mismatch.mkdir()
    (mismatch / "mismatch.status.json").write_text(json.dumps({
        "runtime_protocol_version": "ask.runtime.v1",
        "ask_id": "other",
        "artifacts": {"run_dir": str(mismatch)},
    }))
    old_time = time.time() - 30 * 24 * 60 * 60
    os.utime(malformed, (old_time, old_time))
    os.utime(mismatch, (old_time, old_time))

    result = prune_runs(output_root=tmp_path, older_than_days=14)

    assert malformed.exists()
    assert mismatch.exists()
    assert str(malformed) in result["kept"]
    assert str(mismatch) in result["kept"]


def test_prune_runs_keeps_symlinked_dirs(tmp_path):
    target = tmp_path / "target"
    target.mkdir()
    symlink = tmp_path / "linked"
    symlink.symlink_to(target, target_is_directory=True)
    old_time = time.time() - 30 * 24 * 60 * 60
    os.utime(symlink, (old_time, old_time), follow_symlinks=False)

    result = prune_runs(output_root=tmp_path, older_than_days=14)

    assert symlink.exists()
    assert target.exists()
    assert str(symlink) not in result["removed"]


def test_cli_status_prune_dry_run_lists_old_run_dirs(tmp_path):
    old = AskRunState("old-cli-run", output_root=tmp_path)
    old.write_request({"question": "old"})
    old.finish({"question": "old", "items": []})
    age_run_status(old)

    result = CliRunner().invoke(
        status_module.app,
        ["--prune", "--older-than-days", "14", "--dry-run", "--run-output-root", str(tmp_path), "--json"],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert str(old.run_dir) in payload["removed"]
    assert old.run_dir.exists()


def test_reused_ask_id_is_rejected_by_default(tmp_path):
    first = AskRunState("same-id", output_root=tmp_path)
    first.write_request({"question": "one"})
    first.finish({"question": "one", "items": [{"solution": "ok"}]})

    with pytest.raises(FileExistsError):
        AskRunState("same-id", output_root=tmp_path)


def test_overwrite_replaces_existing_run_dir(tmp_path):
    first = AskRunState("same-id", output_root=tmp_path)
    first.write_request({"question": "one"})
    first.finish({"question": "one", "items": [{"solution": "ok"}]})

    second = AskRunState("same-id", output_root=tmp_path, overwrite=True)
    second.write_request({"question": "two"})

    request = json.loads(second.request_path.read_text())
    assert request["question"] == "two"


def test_resume_rejects_terminal_state(tmp_path):
    first = AskRunState("done-id", output_root=tmp_path)
    first.write_request({"question": "done"})
    first.finish({"question": "done", "items": [{"solution": "ok"}]})

    with pytest.raises(FileExistsError):
        AskRunState("done-id", output_root=tmp_path, resume=True)


def test_resume_accepts_running_state(tmp_path):
    first = AskRunState("running-id", output_root=tmp_path)
    first.write_request({"question": "running"})
    first.update("running", current_step="memory_recall")

    resumed = AskRunState("running-id", output_root=tmp_path, resume=True)

    assert resumed.ask_id == "running-id"


def test_resume_does_not_overwrite_original_request(tmp_path):
    first = AskRunState("resume-id", output_root=tmp_path)
    first.write_request({"command": "ask", "question": "original", "scope": "ask"})
    first.update("running", current_step="memory_recall")

    resumed = AskRunState("resume-id", output_root=tmp_path, resume=True)
    resumed.write_request({"command": "ask", "question": "original", "scope": "ask"})

    request = json.loads(first.request_path.read_text())
    events = [json.loads(line)["event"] for line in first.events_path.read_text().splitlines()]
    assert request["question"] == "original"
    assert "resumed" in events


def test_resume_rejects_conflicting_request(tmp_path):
    first = AskRunState("resume-conflict", output_root=tmp_path)
    first.write_request({"command": "ask", "question": "original", "scope": "ask"})
    first.update("running", current_step="memory_recall")

    resumed = AskRunState("resume-conflict", output_root=tmp_path, resume=True)
    with pytest.raises(ValueError):
        resumed.write_request({"command": "ask", "question": "changed", "scope": "ask"})


def test_resume_rejects_missing_original_request(tmp_path):
    first = AskRunState("missing-request", output_root=tmp_path)
    first.write_request({"command": "ask", "question": "original", "scope": "ask"})
    first.update("running", current_step="memory_recall")
    first.request_path.unlink()

    resumed = AskRunState("missing-request", output_root=tmp_path, resume=True)

    with pytest.raises(FileNotFoundError):
        resumed.write_request({"command": "ask", "question": "original", "scope": "ask"})


def test_resume_rejects_malformed_original_request(tmp_path):
    first = AskRunState("malformed-request", output_root=tmp_path)
    first.write_request({"command": "ask", "question": "original", "scope": "ask"})
    first.update("running", current_step="memory_recall")
    first.request_path.write_text("{not-json")

    resumed = AskRunState("malformed-request", output_root=tmp_path, resume=True)

    with pytest.raises(ValueError):
        resumed.write_request({"command": "ask", "question": "original", "scope": "ask"})


def test_make_run_id_same_question_does_not_collide():
    assert make_run_id("same question") != make_run_id("same question")


def test_watch_status_times_out_for_nonterminal_run(tmp_path):
    run = AskRunState("stuck", output_root=tmp_path)
    run.write_request({"question": "stuck"})
    run.update("running", current_step="memory_recall")

    with pytest.raises(TimeoutError):
        watch_status("stuck", output_root=tmp_path, interval=0.01, timeout_seconds=0.05)


def test_watch_status_streams_new_events_until_terminal(tmp_path, capsys):
    run = AskRunState("event-stream", output_root=tmp_path)
    run.write_request({"question": "stream"})
    run.event("subagent_session_heartbeat", subagent={"status": "running"})
    run.finish({"question": "stream", "items": []})

    watch_status("event-stream", output_root=tmp_path, interval=0.01, timeout_seconds=1)

    captured = capsys.readouterr().out
    assert '"state": "no_results"' in captured
    assert "event-stream" in captured


def test_cli_status_watch_timeout_exits_nonzero(tmp_path):
    run = AskRunState("stuck-cli", output_root=tmp_path)
    run.write_request({"question": "stuck"})
    run.update("running", current_step="memory_recall")

    result = CliRunner().invoke(
        status_module.app,
        [
            "--run",
            "stuck-cli",
            "--watch",
            "--watch-timeout-seconds",
            "0.05",
            "--poll-interval-seconds",
            "0.01",
            "--run-output-root",
            str(tmp_path),
        ],
    )

    assert result.exit_code == 2
    assert "Timed out watching" in result.stderr


def test_artifact_write_failure_degrades_plain_ask(monkeypatch):
    def broken_run_state(*args, **kwargs):
        raise OSError("read-only artifact root")

    def fake_ask(**kwargs):
        return {"question": kwargs["question"], "scope": kwargs["scope"], "items": [{"solution": "ok"}]}

    monkeypatch.setattr(ask_module, "AskRunState", broken_run_state)
    monkeypatch.setattr(ask_module, "ask", fake_ask)

    result = CliRunner().invoke(ask_module.app, ["what", "changed?"])

    assert result.exit_code == 0
    assert "Runtime artifacts disabled" in result.stderr


def test_artifact_write_failure_fails_closed_for_deep_review(monkeypatch):
    def broken_run_state(*args, **kwargs):
        raise OSError("read-only artifact root")

    monkeypatch.setattr(ask_module, "AskRunState", broken_run_state)

    result = CliRunner().invoke(ask_module.app, ["safe", "to", "proceed?", "--deep-review"])

    assert result.exit_code != 0
    assert "Runtime artifacts disabled" not in result.stderr


def test_cli_ask_dry_run_emits_spec_without_artifacts(tmp_path):
    result = CliRunner().invoke(
        ask_module.app,
        [
            "safe",
            "to",
            "proceed?",
            "--deep-review",
            "--dry-run",
            "--ask-id",
            "dry-ask",
            "--run-output-root",
            str(tmp_path),
            "--json",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["spec_protocol_version"] == "ask.dry_run.v1"
    assert payload["options"]["deep_review"] is True
    assert not (tmp_path / "dry-ask").exists()


def test_cli_ask_chain_and_reviewer_specs_feed_dry_run_options(tmp_path):
    result = CliRunner().invoke(
        ask_module.app,
        [
            "review",
            "runtime",
            "--chain",
            "deep-review-safety",
            "--reviewer-spec",
            "security",
            "--dry-run",
            "--run-output-root",
            str(tmp_path),
            "--json",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    options = payload["options"]
    assert options["deep_review"] is True
    assert options["parallel_review"] is True
    assert "secret-persistence" in options["deep_review_focus"]


def test_cli_ask_dry_run_includes_context_policy(tmp_path):
    result = CliRunner().invoke(
        ask_module.app,
        [
            "review",
            "runtime",
            "--dry-run",
            "--review-context",
            "inherited",
            "--inherit-memory",
            "full",
            "--inherit-skills",
            "all",
            "--inherit-project-context",
            "summary",
            "--run-output-root",
            str(tmp_path),
            "--json",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    policy = payload["options"]["context_policy"]
    assert policy["review_context"] == "inherited"
    assert policy["inherit_memory"] == "full"
    assert policy["inherit_skills"] == "all"
    assert policy["inherit_project_context"] == "summary"
    assert policy["memory_as_evidence"] is True


def test_cli_ask_dry_run_includes_parallel_review_dag_options(tmp_path):
    result = CliRunner().invoke(
        ask_module.app,
        [
            "review",
            "runtime",
            "--parallel-review",
            "--review-target",
            "git:diff",
            "--parallel-review-personas",
            "Brandon,Margaret,Jennifer",
            "--review-dag",
            "judge-best",
            "--dry-run",
            "--run-output-root",
            str(tmp_path),
            "--json",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    options = payload["options"]
    assert options["review_target"] == "git:diff"
    assert options["parallel_review_runner"] == "scillm"
    assert options["review_dag"] == "judge-best"
    assert "parallel_review/judge.json" in payload["risk_analysis"]["filesystem_writes"]


def test_deep_review_context_policy_never_treats_memory_as_evidence(tmp_path):
    result = CliRunner().invoke(
        ask_module.app,
        [
            "review",
            "runtime",
            "--deep-review",
            "--deep-review-target",
            "skills/ask/src/ask/run_state.py",
            "--dry-run",
            "--inherit-memory",
            "full",
            "--run-output-root",
            str(tmp_path),
            "--json",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    policy = payload["options"]["context_policy"]
    assert policy["mode"] == "deep-review"
    assert policy["inherit_memory"] == "full"
    assert policy["memory_as_evidence"] is False


def test_cli_real_non_oracle_ask_smoke_writes_granular_events(monkeypatch, tmp_path):
    def fake_recall(question, scope, k):
        return {
            "returncode": 0,
            "stdout": json.dumps({"items": [{"problem": question, "solution": "Runtime protocol exists."}]}),
            "stderr": "",
        }

    monkeypatch.setattr(ask_module, "run_memory_recall", fake_recall)
    monkeypatch.setattr(ask_module, "_has_relevant_domain_items", lambda items, question: True)
    monkeypatch.setattr(ask_module.SessionWriter, "write", lambda self: None)
    monkeypatch.setattr(ask_module, "_record_ask_telemetry", lambda **kwargs: None)

    result = CliRunner().invoke(
        ask_module.app,
        [
            "what",
            "changed?",
            "--raw",
            "--ask-id",
            "real-smoke",
            "--run-output-root",
            str(tmp_path),
        ],
    )

    assert result.exit_code == 0
    status = read_status("real-smoke", tail_events=20, output_root=tmp_path)
    events = [event["event"] for event in status["event_tail"]]
    assert "memory_recall_started" in events
    assert "memory_recall_finished" in events
    assert "synthesis_started" in events
    assert "synthesis_finished" in events
    assert status["state"] == "answered"


def test_cli_learn_writes_runtime_artifacts(monkeypatch, tmp_path):
    captured = {}

    def fake_learn(**kwargs):
        captured.update(kwargs)
        return {"topic": kwargs["topic"], "stored": 0, "memory_existing": 1, "items": []}

    monkeypatch.setattr(pipeline_module, "learn", fake_learn)
    result = CliRunner().invoke(
        pipeline_module.app,
        ["topic", "--ask-id", "learn-smoke", "--run-output-root", str(tmp_path)],
    )

    assert result.exit_code == 0
    assert captured["run_state"].ask_id == "learn-smoke"
    assert read_status("learn-smoke", output_root=tmp_path)["state"] == "completed"


def test_cli_learn_dry_run_emits_spec_without_artifacts(tmp_path):
    result = CliRunner().invoke(
        pipeline_module.app,
        ["topic", "--dry-run", "--ask-id", "learn-dry", "--run-output-root", str(tmp_path)],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["command"] == "learn"
    assert not (tmp_path / "learn-dry").exists()


def test_cli_nightly_writes_runtime_artifacts(monkeypatch, tmp_path):
    def fake_nightly_update(**kwargs):
        return {
            "scope": kwargs["scope"],
            "personas_checked": 0,
            "personas_updated": 1,
            "items_stored": 1,
            "errors": [],
        }

    monkeypatch.setattr(nightly_module, "nightly_update", fake_nightly_update)
    result = CliRunner().invoke(
        nightly_module.app,
        ["--ask-id", "nightly-smoke", "--run-output-root", str(tmp_path)],
    )

    assert result.exit_code == 0
    assert read_status("nightly-smoke", output_root=tmp_path)["state"] == "completed"


def test_cli_nightly_dry_run_emits_spec_without_artifacts(tmp_path):
    result = CliRunner().invoke(
        nightly_module.app,
        ["--dry-run", "--ask-id", "nightly-dry", "--run-output-root", str(tmp_path), "--json"],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["command"] == "nightly"
    assert not (tmp_path / "nightly-dry").exists()


def test_cli_os_learn_writes_runtime_artifacts(monkeypatch, tmp_path):
    monkeypatch.setattr(
        os_learn_module,
        "learn_os",
        lambda **kwargs: {"stored": 1, "dry_run": False, "items": [], "errors": 0},
    )
    result = CliRunner().invoke(
        os_learn_module.app,
        ["--ask-id", "os-learn-smoke", "--run-output-root", str(tmp_path)],
    )

    assert result.exit_code == 0
    assert read_status("os-learn-smoke", output_root=tmp_path)["state"] == "completed"


def test_cli_os_learn_dry_run_emits_spec_without_artifacts(tmp_path):
    result = CliRunner().invoke(
        os_learn_module.app,
        ["--dry-run", "--ask-id", "os-learn-dry", "--run-output-root", str(tmp_path), "--json"],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["command"] == "os learn"
    assert not (tmp_path / "os-learn-dry").exists()


def test_cli_os_ask_writes_runtime_artifacts(monkeypatch, tmp_path):
    monkeypatch.setattr(
        os_query_module,
        "recall_os",
        lambda question, k=5, tags=None, timeout=15: [{"problem": question, "solution": "memory skill"}],
    )
    result = CliRunner().invoke(
        os_query_module.app,
        ["ask", "which skills provide memory?", "--ask-id", "os-ask-smoke", "--run-output-root", str(tmp_path)],
    )

    assert result.exit_code == 0
    assert read_status("os-ask-smoke", output_root=tmp_path)["state"] == "answered"


def test_cli_os_health_writes_runtime_artifacts(monkeypatch, tmp_path):
    monkeypatch.setattr(os_query_module, "get_health_data", lambda subsystem: {"status": "ok"})
    monkeypatch.setattr(os_query_module, "recall_os", lambda *args, **kwargs: [])
    result = CliRunner().invoke(
        os_query_module.app,
        [
            "health",
            "is memory healthy?",
            "--subsystem",
            "memory",
            "--ask-id",
            "os-health-smoke",
            "--run-output-root",
            str(tmp_path),
        ],
    )

    assert result.exit_code == 0
    assert read_status("os-health-smoke", output_root=tmp_path)["state"] == "completed"


def test_cli_os_health_json_is_machine_readable(monkeypatch, tmp_path):
    monkeypatch.setattr(os_query_module, "get_health_data", lambda subsystem: {"status": "ok"})
    monkeypatch.setattr(
        os_query_module,
        "recall_os",
        lambda *args, **kwargs: [
            {"description": "Memory health monitor verifies recall, storage, and retrieval pipeline status."}
        ],
    )
    result = CliRunner().invoke(
        os_query_module.app,
        [
            "health",
            "is memory healthy?",
            "--subsystem",
            "memory",
            "--ask-id",
            "os-health-json",
            "--run-output-root",
            str(tmp_path),
            "--json",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["subsystem"] == "memory"
    assert payload["health_data"]["status"] == "ok"
    assert "retrieval pipeline status" in payload["answer"]
    assert read_status("os-health-json", output_root=tmp_path)["state"] == "completed"
