import json
import time

import pytest
from typer.testing import CliRunner

import ask.ask as ask_module
import ask.ask_dag as ask_dag
from ask.run_state import AskRunState, read_status


def test_validate_ask_dag_accepts_parallel_persona_oracle_nodes():
    dag = ask_dag.validate_ask_dag(
        {
            "schema_version": "ask.dag.v1",
            "nodes": [
                {
                    "id": "brandon",
                    "type": "ask.oracle",
                    "input": {
                        "persona": "Brandon",
                        "prompt": "Read the report and comment against the criteria.",
                        "model": "gpt-5.5",
                        "reasoning_effort": "high",
                    },
                },
                {
                    "id": "margaret",
                    "type": "ask.oracle",
                    "input": {
                        "persona": "Margaret",
                        "prompt": "Read the report and comment against the criteria.",
                        "model": "gpt-5.5",
                        "reasoning_effort": "high",
                    },
                },
                {
                    "id": "final_report",
                    "type": "ask.report",
                    "depends_on": ["brandon", "margaret"],
                    "input": {"title": "Persona Review Report"},
                },
            ],
        }
    )

    summary = ask_dag.dag_dry_run_summary(dag)

    assert summary["schema_version"] == "ask.dag.v1"
    assert [node["id"] for node in summary["nodes"]] == ["brandon", "margaret", "final_report"]


def test_validate_ask_dag_rejects_unknown_dependency():
    with pytest.raises(ask_dag.AskDagError, match="unknown dependencies"):
        ask_dag.validate_ask_dag(
            {
                "schema_version": "ask.dag.v1",
                "nodes": [
                    {
                        "id": "review",
                        "type": "ask.oracle",
                        "depends_on": ["missing"],
                        "input": {"prompt": "review"},
                    }
                ],
            }
        )


def test_validate_ask_dag_accepts_scillm_exec_graph_shape(tmp_path):
    prompt_payload = tmp_path / "brandon-prompt.md"
    prompt_payload.write_text("Brandon: read the report and comment.", encoding="utf-8")

    dag = ask_dag.validate_ask_dag(
        {
            "exec_graph_version": "scillm.exec.graph.v1",
            "graph_id": "report-review",
            "graph_goal": "Review a report with concurrent personas.",
            "max_concurrency": 2,
            "nodes": [
                {
                    "id": "brandon",
                    "title": "Brandon review",
                    "execution": {"model": "gpt 5.5 high", "call_type": "one-shot"},
                    "prompt_payload": str(prompt_payload),
                },
                {
                    "id": "margaret",
                    "title": "Margaret review",
                    "execution": {"model": "gpt-5.5 high", "call_type": "one-shot"},
                    "prompt_payload": {"prompt": "Margaret: read the report and comment."},
                },
                {
                    "id": "final_report",
                    "title": "Final report",
                    "depends_on": ["brandon", "margaret"],
                    "execution": {"call_type": "ask.report", "title": "Final report"},
                },
            ],
        },
        base_dir=tmp_path,
    )

    assert dag["source_graph_version"] == "scillm.exec.graph.v1"
    assert dag["graph_id"] == "report-review"
    assert dag["max_concurrency"] == 2
    assert dag["nodes"][0]["type"] == "ask.oracle"
    assert dag["nodes"][0]["input"]["model"] == "gpt-5.5"
    assert dag["nodes"][0]["input"]["reasoning_effort"] == "high"
    assert dag["nodes"][0]["input"]["prompt"] == "Brandon: read the report and comment."
    assert dag["nodes"][2]["type"] == "ask.report"


def test_validate_ask_dag_rejects_non_runnable_skill_run():
    with pytest.raises(ask_dag.AskDagError, match="runnable sibling skill contract"):
        ask_dag.validate_ask_dag(
            {
                "schema_version": "ask.dag.v1",
                "nodes": [
                    {
                        "id": "final_report",
                        "type": "skill.run",
                        "input": {"skill": "create-report", "args": ["--help"]},
                    }
                ],
            }
        )


def test_validate_ask_dag_accepts_any_runnable_sibling_skill():
    dag = ask_dag.validate_ask_dag(
        {
            "schema_version": "ask.dag.v1",
            "nodes": [
                {
                    "id": "image",
                    "type": "skill.run",
                    "input": {"skill": "create-image", "args": ["--help"]},
                }
            ],
        }
    )

    assert dag["nodes"][0]["input"]["skill"] == "create-image"


def test_draft_ask_dag_from_question_hides_scillm_pooling_details():
    dag = ask_dag.draft_ask_dag_from_question(
        "Use $memory and $scillm to analyze this, then $create-report a short report",
        mentioned_skills=["memory", "scillm", "create-report"],
    )

    assert dag["schema_version"] == "ask.dag.v1"
    assert [node["id"] for node in dag["nodes"]] == ["memory_first", "analysis", "final_report"]
    analysis = dag["nodes"][1]
    assert analysis["type"] == "ask.oracle"
    assert "model_pool" not in analysis["input"]
    assert "queue" not in analysis["input"]
    assert "transport" not in analysis["input"]
    final_report = dag["nodes"][2]
    assert final_report["type"] == "ask.report"


def test_draft_ask_dag_from_question_fails_closed_for_ambiguity():
    with pytest.raises(ask_dag.AskDagError, match="ambiguous"):
        ask_dag.draft_ask_dag_from_question("make it better")


def test_execute_ask_dag_runs_independent_oracle_nodes_concurrently(monkeypatch, tmp_path):
    def fake_oracle_node(node, **_kwargs):
        time.sleep(0.2)
        return {
            "id": node["id"],
            "type": node["type"],
            "ok": True,
            "content": f"{node['id']} comment",
            "context_items": [
                {
                    "problem": node["id"],
                    "solution": f"{node['id']} comment",
                    "via": "ask_dag",
                }
            ],
        }

    monkeypatch.setattr(ask_dag, "_execute_oracle_node", fake_oracle_node)
    run = AskRunState("parallel-dag", output_root=tmp_path)
    run.write_request({"command": "ask", "question": "review report", "scope": "ask"})
    dag = ask_dag.validate_ask_dag(
        {
            "schema_version": "ask.dag.v1",
            "nodes": [
                {"id": "brandon", "type": "ask.oracle", "input": {"prompt": "comment"}},
                {"id": "margaret", "type": "ask.oracle", "input": {"prompt": "comment"}},
            ],
        }
    )

    started = time.perf_counter()
    result = ask_dag.execute_ask_dag(dag, question="review report", scope="ask", run_state=run)
    elapsed = time.perf_counter() - started

    assert elapsed < 0.35
    assert result["context_items"][0]["solution"] in {"brandon comment", "margaret comment"}
    status = read_status("parallel-dag", tail_events=20, output_root=tmp_path)
    assert status["artifacts"]["dag_manifest"].endswith("dag/manifest.json")
    assert any(event["event"] == "dag_layer_started" and event["concurrent"] for event in status["event_tail"])
    assert any(event["event"] == "dag_scillm_partition_started" for event in status["event_tail"])
    subgraph = json.loads((tmp_path / "parallel-dag" / "dag" / "layer-001-scillm.subgraph.json").read_text())
    assert subgraph["exec_graph_version"] == "scillm.exec.graph.v1"
    assert subgraph["owner"] == "ask"
    assert subgraph["lane_owner"] == "scillm"
    assert subgraph["node_ids"] == ["brandon", "margaret"]


def test_execute_ask_dag_passes_dependency_context_to_report_node(monkeypatch, tmp_path):
    def fake_memory_recall(_query, _scope, **_kwargs):
        return {
            "returncode": 0,
            "stdout": json.dumps({"items": [{"problem": "p", "solution": "s"}]}),
            "stderr": "",
        }

    monkeypatch.setattr(ask_dag, "run_memory_recall", fake_memory_recall)
    run = AskRunState("skill-context-dag", output_root=tmp_path)
    run.write_request({"command": "ask", "question": "review report", "scope": "ask"})
    dag = ask_dag.validate_ask_dag(
        {
            "schema_version": "ask.dag.v1",
            "nodes": [
                {"id": "memory_first", "type": "memory.recall", "input": {"query": "lessons"}},
                {
                    "id": "final_report",
                    "type": "ask.report",
                    "depends_on": ["memory_first"],
                    "input": {"title": "Generated Report"},
                },
            ],
        }
    )

    result = ask_dag.execute_ask_dag(dag, question="review report", scope="ask", run_state=run)
    report_node = next(node for node in result["nodes"] if node["id"] == "final_report")

    assert report_node["ok"] is True
    assert report_node["output_path"].endswith("final_report.out.md")
    assert result["context_items"][-1]["solution"].startswith("# Generated Report")
    context = json.loads((tmp_path / "skill-context-dag" / "dag" / "final_report.context.json").read_text())
    assert list(context["dependencies"]) == ["memory_first"]


def test_execute_ask_dag_auto_repairs_dogpile_timeout(monkeypatch, tmp_path):
    calls = []

    def fake_run_skill(skill, args, timeout):
        calls.append((skill, args, timeout))
        assert skill == "dogpile"
        if len(calls) == 1:
            return {"returncode": -2, "stdout": "", "stderr": "Skill dogpile timed out (90s)"}
        return {"returncode": 0, "stdout": "# Dogpile Report\n\nRecovered context", "stderr": ""}

    monkeypatch.setattr(ask_dag, "run_skill", fake_run_skill)
    run = AskRunState("dogpile-repair-dag", output_root=tmp_path)
    run.write_request({"command": "ask", "question": "research", "scope": "ask"})
    dag = ask_dag.validate_ask_dag(
        {
            "schema_version": "ask.dag.v1",
            "nodes": [
                {
                    "id": "fresh_context",
                    "type": "dogpile.search",
                    "input": {"query": "LLM DAG orchestration", "timeout": 90},
                }
            ],
        }
    )

    result = ask_dag.execute_ask_dag(dag, question="research", scope="ask", run_state=run)
    node = result["nodes"][0]

    assert [call[2] for call in calls] == [90, 360]
    assert node["ok"] is True
    assert node["auto_repaired"] is True
    assert node["repairs"][0]["reason"] == "dogpile_timeout_budget_too_low"
    status = read_status("dogpile-repair-dag", tail_events=20, output_root=tmp_path)
    assert any(event["event"] == "dag_node_auto_repair_started" for event in status["event_tail"])
    assert any(event["event"] == "dag_node_auto_repair_finished" and event["ok"] for event in status["event_tail"])


def test_execute_ask_dag_stops_after_failed_required_node(monkeypatch, tmp_path):
    def fake_run_skill(skill, args, timeout):
        assert skill == "dogpile"
        return {"returncode": 1, "stdout": "", "stderr": "provider failure"}

    monkeypatch.setattr(ask_dag, "run_skill", fake_run_skill)
    run = AskRunState("required-fail-dag", output_root=tmp_path)
    run.write_request({"command": "ask", "question": "research", "scope": "ask"})
    dag = ask_dag.validate_ask_dag(
        {
            "schema_version": "ask.dag.v1",
            "nodes": [
                {"id": "fresh_context", "type": "dogpile.search", "input": {"query": "LLM DAG orchestration"}},
                {
                    "id": "final_report",
                    "type": "ask.report",
                    "depends_on": ["fresh_context"],
                    "input": {"title": "Final Report"},
                },
            ],
        }
    )

    with pytest.raises(ask_dag.AskDagError, match="required node"):
        ask_dag.execute_ask_dag(dag, question="research", scope="ask", run_state=run)

    status = read_status("required-fail-dag", tail_events=20, output_root=tmp_path)
    assert any(event["event"] == "dag_layer_failed" for event in status["event_tail"])
    assert not (tmp_path / "required-fail-dag" / "dag" / "final_report.json").exists()


def test_validate_ask_dag_rejects_non_boolean_allow_failure():
    with pytest.raises(ask_dag.AskDagError, match="allow_failure must be a boolean"):
        ask_dag.validate_ask_dag(
            {
                "schema_version": "ask.dag.v1",
                "nodes": [
                    {
                        "id": "optional_probe",
                        "type": "memory.recall",
                        "allow_failure": "yes",
                        "input": {"query": "probe"},
                    }
                ],
            }
        )


def test_execute_ask_dag_continues_when_failed_node_allows_failure(monkeypatch, tmp_path):
    calls = {"dogpile": 0}

    def fake_run_skill(skill, args, timeout):
        if skill == "dogpile":
            calls["dogpile"] += 1
            return {"returncode": 1, "stdout": "", "stderr": "provider failure"}
        return {"returncode": 0, "stdout": "{}", "stderr": ""}

    monkeypatch.setattr(ask_dag, "run_skill", fake_run_skill)
    run = AskRunState("allow-failure-dag", output_root=tmp_path)
    run.write_request({"command": "ask", "question": "research", "scope": "ask"})
    dag = ask_dag.validate_ask_dag(
        {
            "schema_version": "ask.dag.v1",
            "nodes": [
                {
                    "id": "fresh_context",
                    "type": "dogpile.search",
                    "allow_failure": True,
                    "input": {"query": "LLM DAG orchestration"},
                },
                {
                    "id": "final_report",
                    "type": "ask.report",
                    "depends_on": ["fresh_context"],
                    "input": {"title": "Final Report"},
                },
            ],
        }
    )

    result = ask_dag.execute_ask_dag(dag, question="research", scope="ask", run_state=run)
    assert calls["dogpile"] == 1
    assert (tmp_path / "allow-failure-dag" / "dag" / "final_report.json").exists()
    assert result["manifest_path"]
    status = read_status("allow-failure-dag", tail_events=20, output_root=tmp_path)
    assert not any(event["event"] == "dag_layer_failed" for event in status["event_tail"])



def test_cli_dag_json_records_normalized_request_and_passes_dag(monkeypatch, tmp_path):
    captured = {}

    def fake_ask(**kwargs):
        captured.update(kwargs)
        return {
            "question": kwargs["question"],
            "scope": kwargs["scope"],
            "items": [{"solution": "ok"}],
            "answer": "ok",
        }

    monkeypatch.setattr(ask_module, "ask", fake_ask)
    dag = {
        "schema_version": "ask.dag.v1",
        "nodes": [
            {"id": "memory_first", "type": "memory.recall", "input": {"query": "prior report lessons"}},
            {
                "id": "brandon",
                "type": "ask.oracle",
                "depends_on": ["memory_first"],
                "input": {"prompt": "Brandon comment on the report"},
            },
        ],
    }

    result = CliRunner().invoke(
        ask_module.app,
        [
            "comment",
            "on",
            "the",
            "report",
            "--dag-json",
            json.dumps(dag),
            "--ask-id",
            "dag-cli",
            "--run-output-root",
            str(tmp_path),
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    assert captured["ask_dag"]["schema_version"] == "ask.dag.v1"
    request = json.loads((tmp_path / "dag-cli" / "dag-cli.request.json").read_text())
    assert request["ask_dag"]["node_count"] == 2
    assert request["ask_dag"]["nodes"][1]["id"] == "brandon"


def test_cli_orchestrate_records_drafted_dag(monkeypatch, tmp_path):
    captured = {}

    def fake_ask(**kwargs):
        captured.update(kwargs)
        return {
            "question": kwargs["question"],
            "scope": kwargs["scope"],
            "items": [{"solution": "ok"}],
            "answer": "ok",
        }

    monkeypatch.setattr(ask_module, "ask", fake_ask)

    result = CliRunner().invoke(
        ask_module.app,
        [
            "Use",
            "$memory",
            "and",
            "$scillm",
            "to",
            "analyze",
            "this",
            "then",
            "$create-report",
            "a",
            "report",
            "--orchestrate",
            "--ask-id",
            "dag-orchestrate-cli",
            "--run-output-root",
            str(tmp_path),
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    assert captured["ask_dag"]["graph_id"] == "ask-natural-language-orchestration"
    request = json.loads((tmp_path / "dag-orchestrate-cli" / "dag-orchestrate-cli.request.json").read_text())
    assert request["orchestrate"] is True
    assert request["ask_dag"]["node_count"] == 3
    assert request["ask_dag"]["nodes"][-1]["id"] == "final_report"


def test_dag_dry_run_summary_includes_layers_and_ascii_chart():
    dag = ask_dag.validate_ask_dag(
        {
            "schema_version": "ask.dag.v1",
            "graph_id": "fanout-join",
            "max_concurrency": 2,
            "nodes": [
                {
                    "id": "memory_a",
                    "type": "memory.recall",
                    "input": {"query": "a", "scope": "ask", "k": 1},
                },
                {
                    "id": "memory_b",
                    "type": "memory.recall",
                    "input": {"query": "b", "scope": "ask", "k": 1},
                },
                {
                    "id": "final_report",
                    "type": "ask.report",
                    "depends_on": ["memory_a", "memory_b"],
                    "input": {"title": "Final Report"},
                },
            ],
        }
    )
    summary = ask_dag.dag_dry_run_summary(dag)
    assert summary["layer_count"] == 2
    assert summary["layers"][0]["concurrent"] is True
    assert set(summary["layers"][0]["node_ids"]) == {"memory_a", "memory_b"}
    assert summary["layers"][1]["node_ids"] == ["final_report"]
    chart = summary["ascii_chart"]
    assert "DAG decision tree" in chart
    assert "┌" in chart or "[" in chart
    assert "memory_a" in chart and "memory_b" in chart
    assert "final_report" in chart
    assert summary["ascii_renderer"] in {"phart-git", "phart-pypi", "fallback"}
    assert "┌" in chart or "[" in chart


def test_validate_ask_dag_accepts_scillm_agent_turn_node():
    dag = ask_dag.validate_ask_dag(
        {
            "schema_version": "ask.dag.v1",
            "nodes": [
                {
                    "id": "implement",
                    "type": "scillm.agent_turn",
                    "input": {
                        "worker_id": "implementation",
                        "goal": "Fix the path bug in render_dag_chart.py",
                        "sandbox": "workspace-write",
                    },
                }
            ],
        }
    )
    assert dag["nodes"][0]["type"] == "scillm.agent_turn"


def test_draft_ask_dag_from_question_uses_agent_turn_for_coding_intent():
    dag = ask_dag.draft_ask_dag_from_question("Implement the fix for the DAG path bug")
    node_types = [node["type"] for node in dag["nodes"]]
    assert "scillm.agent_turn" in node_types
    implement = next(node for node in dag["nodes"] if node["id"] == "implement")
    assert implement["input"]["sandbox"] == "workspace-write"
    assert "fix" in implement["input"]["goal"].lower()


def test_should_orchestrate_from_text_detects_coding_intent():
    assert ask_dag.should_orchestrate_from_text("Please implement the retry logic")


def test_build_persona_review_implement_dag_validates():
    dag = ask_dag.build_persona_review_implement_dag(
        "Brandon: review-code then implement the sample_target fix",
        persona="Brandon",
        agent_worker_id="implementation",
    )
    node_ids = [node["id"] for node in dag["nodes"]]
    assert node_ids == [
        "memory_first",
        "persona_brief",
        "code_review",
        "memory_consult",
        "dogpile_consult",
        "implement",
    ]
    implement = next(node for node in dag["nodes"] if node["id"] == "implement")
    assert implement["type"] == "scillm.agent_turn"
    assert implement["input"]["sandbox"] == "workspace-write"
    review = next(node for node in dag["nodes"] if node["id"] == "code_review")
    assert review["input"]["skill"] == "review-code"
    assert "--file" in review["input"]["args"]


def test_draft_ask_dag_review_code_implement_loop():
    dag = ask_dag.draft_ask_dag_from_question(
        "Brandon $review-code the module then implement the fix; use $memory and $dogpile when blocked"
    )
    assert dag["graph_id"] == "ask-persona-review-implement"
    assert any(node["id"] == "code_review" for node in dag["nodes"])


def test_build_persona_review_implement_includes_debugger_guidance():
    dag = ask_dag.build_persona_review_implement_dag("fix sample", persona="Brandon")
    implement = next(node for node in dag["nodes"] if node["id"] == "implement")
    goal = implement["input"]["goal"]
    assert "/debugger" in goal
    assert "breakpoint" in goal.lower()
