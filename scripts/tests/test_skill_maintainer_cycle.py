from __future__ import annotations

import importlib.util
import json
import subprocess
from pathlib import Path


def load_cycle_module():
    module_path = Path(__file__).resolve().parents[1] / "skill_maintainer_cycle.py"
    spec = importlib.util.spec_from_file_location("skill_maintainer_cycle", module_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def issue_fixture() -> dict:
    return {
        "number": 3,
        "title": "Feature: resilient $ask WebGPT recovery for stale tab id / URL mismatch",
        "labels": [
            {"name": "skill-maintenance"},
            {"name": "skill-optimization"},
            {"name": "type:feature"},
            {"name": "maintainer-active"},
        ],
        "body": "\n".join(
            [
                "## Ticket type",
                "feature",
                "",
                "## Target paths",
                "- skills/ask/SKILL.md",
                "- skills/surf/SKILL.md",
                "- skills/browser-oracle project binding files, if ask routes through browser-oracle",
                "",
                "## Maintainer route",
                "backend_python_or_skill_runtime",
                "",
                "## Requested repair agent",
                "coder",
                "",
                "## Current state",
                "This mentions visual design, UI, screenshot, and interaction words.",
            ]
        ),
    }


def mock_successful_github_terminal_disposition(monkeypatch, cycle):
    monkeypatch.setattr(
        cycle,
        "gh_issue_comment",
        lambda issue_number, body_path, dry_run=False: {
            "cmd": ["gh", "issue", "comment", str(issue_number), "--body-file", str(body_path)],
            "dry_run": dry_run,
            "returncode": 0,
            "stdout": "commented",
            "stderr": "",
        },
    )
    monkeypatch.setattr(
        cycle,
        "gh_issue_close",
        lambda issue_number, dry_run=False: {
            "cmd": ["gh", "issue", "close", str(issue_number)],
            "dry_run": dry_run,
            "returncode": 0,
            "stdout": "closed",
            "stderr": "",
        },
    )
    monkeypatch.setattr(
        cycle,
        "gh_issue_edit",
        lambda issue_number, *args, dry_run=False: {
            "cmd": ["gh", "issue", "edit", str(issue_number), *args],
            "dry_run": dry_run,
            "returncode": 0,
            "stdout": "edited",
            "stderr": "",
        },
    )


def test_issue_body_route_metadata_wins_over_misleading_text():
    cycle = load_cycle_module()
    route = cycle.classify(issue_fixture())
    assert route["route"] == "backend_python_or_skill_runtime"
    assert route["repair_agent"] == "coder"
    assert route["verifier_agent"] == "project-or-harness-verifier"
    assert route["selection_source"] == "issue_body"
    assert route["selection_reason"] == "route:backend_python_or_skill_runtime"


def test_ticket_skill_maintenance_body_routes_and_targets():
    cycle = load_cycle_module()
    body = "\n".join(
        [
            "## Type",
            "",
            "maintenance",
            "",
            "## Target",
            "",
            "skills/monitor-skill-health",
            "",
            "## Target paths",
            "",
            "- skills/monitor-skill-health",
            "",
            "## Current state",
            "",
            "low needs_fix finding at monitor.py",
            "",
            "## Requested outcome",
            "",
            "Preserve invariant: focused monitor re-audit passes",
            "",
            "## Required proof",
            "",
            "skills/monitor-skill-health/run.sh audit --skill monitor-skill-health --no-memory --no-deep-review --json",
            "",
            "## Route",
            "",
            "backend_python_or_skill_runtime",
            "",
            "## Maintainer route",
            "",
            "backend_python_or_skill_runtime",
            "",
            "## Requested repair agent",
            "",
            "agent-skill-maintainer",
        ]
    )
    issue = {
        "number": 91,
        "title": "[monitor-skill-health] monitor-skill-health: style-module-docstring",
        "labels": [
            {"name": "type:maintenance"},
            {"name": "skill-maintenance"},
            {"name": "monitor-skill-health"},
            {"name": "route:backend_python_or_skill_runtime"},
            {"name": "agent:agent-skill-maintainer"},
        ],
        "body": body,
    }

    route = cycle.classify(issue)

    assert route["route"] == "backend_python_or_skill_runtime"
    assert route["selection_source"] == "issue_label"
    assert cycle.target_paths(issue) == ["skills/monitor-skill-health"]
    assert cycle.target_skills(issue) == ["monitor-skill-health"]


def test_ask_webgpt_command_uses_dedicated_review_code_project(tmp_path):
    cycle = load_cycle_module()
    cmd = cycle.ask_webgpt_command(tmp_path / "bundle.md")
    assert "--project" in cmd
    assert cmd[cmd.index("--project") + 1] == "agent-skills-review-code"


def test_target_skills_are_extracted_from_target_paths_section_only():
    cycle = load_cycle_module()
    assert cycle.target_skills(issue_fixture()) == ["ask", "surf", "browser-oracle"]


def test_target_skills_are_preserved_when_skill_path_is_missing():
    cycle = load_cycle_module()
    issue = issue_fixture()
    issue["body"] = "\n".join(
        [
            "## Target paths",
            "- skills/fact-extractor/fact_extractor/cli.py",
            "- agents/audiobook-extractor/AGENTS.md",
        ]
    )

    assert cycle.target_skills(issue) == ["fact-extractor"]
    assert cycle.target_paths(issue) == [
        "skills/fact-extractor/fact_extractor/cli.py",
        "agents/audiobook-extractor/AGENTS.md",
    ]


def test_target_skills_do_not_fall_back_to_prose_paths_without_target_section():
    cycle = load_cycle_module()
    issue = issue_fixture()
    issue["body"] = "\n".join(
        [
            "## Current state",
            "The prose mentions skills/best-practices-skills/SKILL.md as an example only.",
            "",
            "## Maintainer route",
            "backend_python_or_skill_runtime",
        ]
    )
    assert cycle.target_skills(issue) == []


def test_missing_target_paths_are_detected_against_repo_root(tmp_path, monkeypatch):
    cycle = load_cycle_module()
    (tmp_path / "skills" / "present").mkdir(parents=True)
    (tmp_path / "skills" / "present" / "SKILL.md").write_text("---\nname: present\n")
    monkeypatch.setattr(cycle, "REPO_ROOT", tmp_path)

    assert cycle.missing_target_paths([
        "skills/present/SKILL.md",
        "skills/missing/SKILL.md",
        "agents/missing/AGENTS.md",
    ]) == [
        "skills/missing/SKILL.md",
        "agents/missing/AGENTS.md",
    ]


def test_active_lease_does_not_prevent_explicit_issue_classification():
    cycle = load_cycle_module()
    issue = issue_fixture()
    assert "maintainer-active" in {label["name"] for label in issue["labels"]}
    assert cycle.classify(issue)["repair_agent"] == "coder"


def test_issue_list_filters_active_blocked_and_external_owner(monkeypatch):
    cycle = load_cycle_module()
    issues = [
        {"number": 1, "labels": [{"name": "skill-bug"}]},
        {"number": 2, "labels": [{"name": "skill-bug"}, {"name": "maintainer-active"}]},
        {"number": 3, "labels": [{"name": "skill-bug"}, {"name": "maintainer-blocked"}]},
        {"number": 4, "labels": [{"name": "skill-bug"}, {"name": "needs-human"}]},
        {"number": 5, "labels": [{"name": "skill-bug"}, {"name": "external-owner"}]},
    ]

    class _Completed:
        stdout = json.dumps(issues)

    monkeypatch.setattr(cycle, "shutil_which", lambda name: "/usr/bin/gh")
    monkeypatch.setattr(cycle, "run", lambda cmd, check=True: _Completed())

    selected = cycle.issue_list(["skill-bug"])

    assert [issue["number"] for issue in selected] == [1]


def test_default_labels_include_skill_agent_and_monitor_tickets():
    cycle = load_cycle_module()

    assert "skill-maintenance" in cycle.DEFAULT_LABELS
    assert "agent-maintenance" in cycle.DEFAULT_LABELS
    assert "monitor-skill-health" in cycle.DEFAULT_LABELS


def test_dry_run_main_writes_prepared_only_blocked_result(tmp_path, monkeypatch, capsys):
    cycle = load_cycle_module()
    issue = issue_fixture()
    issue["labels"] = [{"name": "skill-bug"}, {"name": "skill-maintenance"}]
    issue["number"] = 44
    issue["body"] = issue["body"].replace("backend_python_or_skill_runtime", "backend_python_or_skill_runtime")

    monkeypatch.setattr(cycle, "ARTIFACT_ROOT", tmp_path)
    monkeypatch.setattr(cycle, "issue_view", lambda number: issue)
    monkeypatch.setattr(cycle, "git_repo_slug", lambda: "owner/repo")
    monkeypatch.setattr(cycle, "ensure_ask_runtime", lambda: None)
    monkeypatch.setattr(
        "sys.argv",
        [
            "skill_maintainer_cycle.py",
            "--issue",
            "44",
            "--require-webgpt",
            "--dry-run",
        ],
    )

    assert cycle.main() == 0
    output = json.loads(capsys.readouterr().out)

    assert output["status"] == "prepared_only_blocked"
    assert output["issue"] == 44
    assert output["closure_decision"] == "blocked_missing_repair_executor"
    assert [action["action"] for action in output["github_actions"]] == [
        "lease_label",
        "lease_comment",
        "blocked_comment",
        "blocked_labels_release_lease",
    ]
    result_path = Path(output["artifact_dir"]) / "cycle-result.json"
    assert json.loads(result_path.read_text())["status"] == "prepared_only_blocked"
    repair = json.loads((Path(output["artifact_dir"]) / "repair-response.json").read_text())
    verifier = json.loads((Path(output["artifact_dir"]) / "verifier-response.json").read_text())
    review = json.loads((Path(output["artifact_dir"]) / "review-response.json").read_text())
    webgpt = json.loads((Path(output["artifact_dir"]) / "ask-webgpt-result.json").read_text())
    assert repair["status"] == "blocked_missing_executor"
    assert verifier["status"] == "blocked_waiting_for_repair_receipt"
    assert review["status"] == "blocked_waiting_for_repair_and_verifier_receipts"
    assert webgpt["status"] == "blocked_waiting_for_deterministic_verification"
    assert output["repair_receipts"] == [str(Path(output["artifact_dir"]) / "repair-response.json")]
    assert output["verifier_receipts"] == [str(Path(output["artifact_dir"]) / "verifier-response.json")]
    assert output["review_receipts"] == [str(Path(output["artifact_dir"]) / "review-response.json")]
    assert output["ask_webgpt_artifacts"] == [str(Path(output["artifact_dir"]) / "ask-webgpt-result.json")]
    for key in ("repair_spec", "verifier_spec", "review_spec"):
        spec_path = Path(output["subagent_specs"][key])
        spec = json.loads(spec_path.read_text())
        assert spec["backend"] == "codex"
        assert spec["cwd"]
        assert spec["output_dir"].endswith("subagent-sessions")
        assert str(output["issue"]) in spec["task_id"]
        assert spec["command"][:2] == ["codex", "exec"]
        assert "--dangerously-bypass-approvals-and-sandbox" in spec["command"]
        assert "--ask-for-approval" not in spec["command"]


def test_dry_run_dispatch_records_repair_subagent_start(tmp_path, monkeypatch, capsys):
    cycle = load_cycle_module()
    issue = issue_fixture()
    issue["labels"] = [{"name": "skill-bug"}, {"name": "skill-maintenance"}]
    issue["number"] = 45

    monkeypatch.setattr(cycle, "ARTIFACT_ROOT", tmp_path)
    monkeypatch.setattr(cycle, "issue_view", lambda number: issue)
    monkeypatch.setattr(cycle, "git_repo_slug", lambda: "owner/repo")
    monkeypatch.setattr(cycle, "ensure_ask_runtime", lambda: None)
    monkeypatch.setattr(
        cycle,
        "maybe_dispatch_subagent",
        lambda spec_path, dry_run=False: {
            "cmd": ["bash", "skills/subagent-runner/run.sh", "start", spec_path],
            "dry_run": dry_run,
            "returncode": 0,
            "stdout": json.dumps({
                "session_id": "skill-maintainer-issue-45-repair-abc123",
                "status": "starting",
                "artifact_dir": "/tmp/subagent-sessions/session",
                "watcher_pid": 12345,
            }),
            "stderr": "",
        },
    )
    monkeypatch.setattr(
        "sys.argv",
        [
            "skill_maintainer_cycle.py",
            "--issue",
            "45",
            "--require-webgpt",
            "--dry-run",
            "--dispatch-subagents",
        ],
    )

    assert cycle.main() == 0
    output = json.loads(capsys.readouterr().out)

    assert output["status"] == "repair_subagent_started"
    assert output["subagent_dispatch"][0]["phase"] == "repair"
    assert output["subagent_dispatch"][0]["cmd"][:3] == ["bash", "skills/subagent-runner/run.sh", "start"]
    assert output["closure_decision"] == "waiting_for_repair_subagent_receipt"
    assert output["repair_session"]["session_id"] == "skill-maintainer-issue-45-repair-abc123"
    assert [action["action"] for action in output["github_actions"]] == [
        "lease_label",
        "lease_comment",
    ]
    repair = json.loads((Path(output["artifact_dir"]) / "repair-response.json").read_text())
    assert repair["status"] == "running"
    assert repair["subagent_dispatch"]["stdout_json"]["artifact_dir"] == "/tmp/subagent-sessions/session"


def test_missing_target_paths_block_before_subagent_dispatch(tmp_path, monkeypatch, capsys):
    cycle = load_cycle_module()
    issue = issue_fixture()
    issue["labels"] = [{"name": "skill-maintenance"}]
    issue["number"] = 46
    issue["body"] = "\n".join(
        [
            "## Target paths",
            "- skills/missing-skill/SKILL.md",
            "- agents/missing-agent/AGENTS.md",
            "",
            "## Maintainer route",
            "backend_python_or_skill_runtime",
        ]
    )

    monkeypatch.setattr(cycle, "ARTIFACT_ROOT", tmp_path)
    monkeypatch.setattr(cycle, "issue_view", lambda number: issue)
    monkeypatch.setattr(cycle, "git_repo_slug", lambda: "owner/repo")
    monkeypatch.setattr(cycle, "ensure_ask_runtime", lambda: None)
    dispatch_calls = []
    monkeypatch.setattr(cycle, "maybe_dispatch_subagent", lambda *args, **kwargs: dispatch_calls.append((args, kwargs)))
    monkeypatch.setattr(
        "sys.argv",
        [
            "skill_maintainer_cycle.py",
            "--issue",
            "46",
            "--require-webgpt",
            "--dry-run",
            "--dispatch-subagents",
        ],
    )

    assert cycle.main() == 0
    output = json.loads(capsys.readouterr().out)

    assert output["status"] == "blocked_missing_target_paths"
    assert output["missing_target_paths"] == [
        "skills/missing-skill/SKILL.md",
        "agents/missing-agent/AGENTS.md",
    ]
    assert dispatch_calls == []
    assert [action["action"] for action in output["github_actions"]] == [
        "lease_label",
        "lease_comment",
        "missing_target_comment",
        "missing_target_labels_release_lease",
    ]
    assert (Path(output["artifact_dir"]) / "missing-targets.json").exists()


def test_command_fixture_specs_write_completed_receipts(tmp_path):
    cycle = load_cycle_module()
    issue = issue_fixture()
    issue_dir = tmp_path / "issue-48"
    issue_dir.mkdir()
    route = cycle.ROUTES_BY_NAME["backend_python_or_skill_runtime"]

    specs = cycle.build_subagent_specs(issue_dir, issue, route, ["ask"], command_fixture=True)

    for key in ("repair_spec", "verifier_spec", "review_spec"):
        spec = json.loads(Path(specs[key]).read_text())
        assert spec["command"][:2] == ["python3", "-c"]
        assert "CONTROLLED_WORKER_DONE" in spec["command"][2]
        assert spec["tau_handoff"]["schema"] == "tau.agent_handoff.v1"
        assert spec["tau_handoff"]["issue"] == issue["number"]
        assert spec["tau_handoff"]["route"] == "backend_python_or_skill_runtime"
        assert spec["tau_handoff"]["lease_policy"] == "one_ticket_at_a_time"
        assert spec["tau_handoff"]["expected_receipt"].endswith("-response.json")

    repair_spec = json.loads(Path(specs["repair_spec"]).read_text())
    verifier_spec = json.loads(Path(specs["verifier_spec"]).read_text())
    review_spec = json.loads(Path(specs["review_spec"]).read_text())
    assert repair_spec["tau_handoff"]["phase"] == "repair"
    assert verifier_spec["tau_handoff"]["phase"] == "deterministic_verification"
    assert review_spec["tau_handoff"]["phase"] == "independent_review"


def test_real_subagent_specs_include_gateable_receipt_contracts(tmp_path):
    cycle = load_cycle_module()
    issue = issue_fixture()
    issue_dir = tmp_path / "issue-50"
    issue_dir.mkdir()
    route = cycle.ROUTES_BY_NAME["backend_python_or_skill_runtime"]

    specs = cycle.build_subagent_specs(issue_dir, issue, route, ["ask"], command_fixture=False)

    repair_spec = json.loads(Path(specs["repair_spec"]).read_text())
    verifier_spec = json.loads(Path(specs["verifier_spec"]).read_text())
    review_spec = json.loads(Path(specs["review_spec"]).read_text())

    assert "Phase: repair" in repair_spec["prompt"]
    assert '"status": "repaired"' in repair_spec["prompt"]
    assert '"files_changed": ["relative/path"]' in repair_spec["prompt"]
    assert "State mocked/live boundaries" in repair_spec["prompt"]
    assert repair_spec["tau_handoff"]["receipt_contract"]["accepted_status"] == ["repaired", "completed"]
    assert "changed_files" in repair_spec["tau_handoff"]["receipt_contract"]["required_fields"]

    assert "Phase: deterministic_verification" in verifier_spec["prompt"]
    assert '"decision": "pass"' in verifier_spec["prompt"]
    assert verifier_spec["tau_handoff"]["receipt_contract"]["accepted_decisions"] == ["pass", "passed", "no_findings"]

    assert "Phase: independent_review" in review_spec["prompt"]
    assert "Read the issue, repair receipt, and verifier receipt." in review_spec["prompt"]
    assert review_spec["tau_handoff"]["receipt_contract"]["blocking_findings_field"] == "blocking_findings"


def test_github_dry_run_allows_live_local_dispatch(tmp_path, monkeypatch, capsys):
    cycle = load_cycle_module()
    issue = issue_fixture()
    issue["labels"] = [{"name": "skill-bug"}, {"name": "skill-maintenance"}]
    issue["number"] = 49

    monkeypatch.setattr(cycle, "ARTIFACT_ROOT", tmp_path)
    monkeypatch.setattr(cycle, "issue_view", lambda number: issue)
    monkeypatch.setattr(cycle, "git_repo_slug", lambda: "owner/repo")
    monkeypatch.setattr(cycle, "ensure_ask_runtime", lambda: None)
    dispatch_calls = []

    def fake_dispatch(spec_path, dry_run=False):
        dispatch_calls.append({"spec_path": spec_path, "dry_run": dry_run})
        return {
            "cmd": ["bash", "skills/subagent-runner/run.sh", "start", spec_path],
            "dry_run": dry_run,
            "returncode": 0,
            "stdout": json.dumps({"session_id": "local-dispatch", "artifact_dir": "/tmp/local-dispatch"}),
            "stderr": "",
        }

    monkeypatch.setattr(cycle, "maybe_dispatch_subagent", fake_dispatch)
    monkeypatch.setattr(
        "sys.argv",
        [
            "skill_maintainer_cycle.py",
            "--issue",
            "49",
            "--require-webgpt",
            "--github-dry-run",
            "--dispatch-subagents",
        ],
    )

    assert cycle.main() == 0
    output = json.loads(capsys.readouterr().out)

    assert dispatch_calls == [{"spec_path": output["subagent_specs"]["repair_spec"], "dry_run": False}]
    assert output["github_dry_run"] is True
    assert output["github_actions"][0]["dry_run"] is True
    assert output["subagent_dispatch"][0]["dry_run"] is False


def test_controlled_live_mutation_fixture_posts_only_lease_comment_and_local_receipts(
    tmp_path,
    monkeypatch,
    capsys,
):
    cycle = load_cycle_module()
    issue = issue_fixture()
    issue["labels"] = [{"name": "skill-maintenance"}]
    issue["number"] = 5
    issue["url"] = "https://github.com/owner/repo/issues/5"

    monkeypatch.setattr(cycle, "ARTIFACT_ROOT", tmp_path)
    monkeypatch.setattr(cycle, "issue_view", lambda number: issue)
    monkeypatch.setattr(cycle, "git_repo_slug", lambda: "owner/repo")
    monkeypatch.setattr(cycle, "ensure_ask_runtime", lambda: None)
    monkeypatch.setattr(
        cycle,
        "gh_issue_edit",
        lambda issue_number, *args, dry_run=False: {
            "cmd": ["gh", "issue", "edit", str(issue_number), *args],
            "dry_run": dry_run,
            "returncode": 0,
            "stdout": "https://github.com/owner/repo/issues/5\n",
            "stderr": "",
        },
    )
    monkeypatch.setattr(
        cycle,
        "gh_issue_comment",
        lambda issue_number, body_path, dry_run=False: {
            "cmd": ["gh", "issue", "comment", str(issue_number), "--body-file", str(body_path)],
            "dry_run": dry_run,
            "returncode": 0,
            "stdout": "https://github.com/owner/repo/issues/5#issuecomment-1\n",
            "stderr": "",
        },
    )
    dispatch_calls = []
    monkeypatch.setattr(cycle, "maybe_dispatch_subagent", lambda *args, **kwargs: dispatch_calls.append(args))
    monkeypatch.setattr(
        "sys.argv",
        [
            "skill_maintainer_cycle.py",
            "--issue",
            "5",
            "--require-webgpt",
            "--controlled-live-mutation-fixture",
        ],
    )

    assert cycle.main() == 0
    output = json.loads(capsys.readouterr().out)
    issue_dir = Path(output["artifact_dir"])

    assert output["status"] == "controlled_live_mutation_fixture_completed"
    assert output["scheduler_enabled"] is False
    assert output["closure_attempted"] is False
    assert output["closure_decision"] == "blocked_waiting_for_human_fixture_disposition"
    assert dispatch_calls == []
    assert [action["action"] for action in output["github_actions"]] == [
        "lease_label",
        "lease_comment",
    ]
    assert "blocked_comment" not in {action["action"] for action in output["github_actions"]}
    assert "blocked_labels_release_lease" not in {action["action"] for action in output["github_actions"]}

    proof = output["controlled_live_mutation_proof"]
    assert proof["schema"] == "skill_maintainer.controlled_live_mutation_proof.v1"
    assert proof["lease_label_present_before_run"] is False
    assert proof["lease_label_mutation_observed"] is True
    assert proof["lease_label_proven"] is True
    assert proof["lease_comment_observed"] is True
    assert proof["repair_verifier_reviewer_scope"] == "local_receipt_artifacts_only"
    assert proof["webgpt_treated_as_deterministic_proof"] is False

    for receipt_name in ("repair-response.json", "verifier-response.json", "review-response.json"):
        receipt = json.loads((issue_dir / receipt_name).read_text())
        assert receipt["status"] == "completed"
        assert receipt["decision"] == "pass"
        assert receipt["changed_files"] == []
        assert receipt["controlled_live_mutation_proof"]["schema"] == proof["schema"]
    webgpt = json.loads((issue_dir / "ask-webgpt-result.json").read_text())
    assert webgpt["status"] == "not_run"
    assert webgpt["reason"] == "controlled_live_mutation_fixture_stops_before_webgpt"


def test_controlled_live_mutation_fixture_comments_when_issue_already_leased(
    tmp_path,
    monkeypatch,
    capsys,
):
    cycle = load_cycle_module()
    issue = issue_fixture()
    issue["labels"] = [{"name": "skill-maintenance"}, {"name": "maintainer-active"}]
    issue["number"] = 6

    monkeypatch.setattr(cycle, "ARTIFACT_ROOT", tmp_path)
    monkeypatch.setattr(cycle, "issue_view", lambda number: issue)
    monkeypatch.setattr(cycle, "git_repo_slug", lambda: "owner/repo")
    monkeypatch.setattr(cycle, "ensure_ask_runtime", lambda: None)
    edit_calls = []
    monkeypatch.setattr(cycle, "gh_issue_edit", lambda *args, **kwargs: edit_calls.append(args))
    monkeypatch.setattr(
        cycle,
        "gh_issue_comment",
        lambda issue_number, body_path, dry_run=False: {
            "cmd": ["gh", "issue", "comment", str(issue_number), "--body-file", str(body_path)],
            "dry_run": dry_run,
            "returncode": 0,
            "stdout": "https://github.com/owner/repo/issues/6#issuecomment-2\n",
            "stderr": "",
        },
    )
    monkeypatch.setattr(
        "sys.argv",
        [
            "skill_maintainer_cycle.py",
            "--issue",
            "6",
            "--require-webgpt",
            "--controlled-live-mutation-fixture",
        ],
    )

    assert cycle.main() == 0
    output = json.loads(capsys.readouterr().out)

    assert edit_calls == []
    assert [action["action"] for action in output["github_actions"]] == ["lease_comment"]
    assert output["controlled_live_mutation_proof"]["lease_label_present_before_run"] is True
    assert output["controlled_live_mutation_proof"]["lease_label_proven"] is True
    assert output["controlled_live_mutation_proof"]["lease_comment_observed"] is True


def test_controlled_live_mutation_fixture_rejects_fixture_source_before_github_mutation(
    tmp_path,
    monkeypatch,
):
    cycle = load_cycle_module()
    issue = issue_fixture()
    issue["labels"] = [{"name": "skill-maintenance"}]
    fixture = tmp_path / "issue.json"
    fixture.write_text(json.dumps(issue))

    monkeypatch.setattr(cycle, "ARTIFACT_ROOT", tmp_path / "artifacts")
    monkeypatch.setattr(cycle, "git_repo_slug", lambda: "owner/repo")
    monkeypatch.setattr(cycle, "ensure_ask_runtime", lambda: None)
    edit_calls = []
    comment_calls = []
    monkeypatch.setattr(cycle, "gh_issue_edit", lambda *args, **kwargs: edit_calls.append((args, kwargs)))
    monkeypatch.setattr(cycle, "gh_issue_comment", lambda *args, **kwargs: comment_calls.append((args, kwargs)))
    monkeypatch.setattr(
        "sys.argv",
        [
            "skill_maintainer_cycle.py",
            "--fixture-issue-json",
            str(fixture),
            "--require-webgpt",
            "--controlled-live-mutation-fixture",
        ],
    )

    try:
        cycle.main()
    except SystemExit as exc:
        assert str(exc) == "--controlled-live-mutation-fixture requires a real GitHub issue"
    else:
        raise AssertionError("expected SystemExit")

    assert edit_calls == []
    assert comment_calls == []


def test_controlled_live_mutation_fixture_rejects_dispatch_before_github_mutation(
    tmp_path,
    monkeypatch,
):
    cycle = load_cycle_module()
    issue = issue_fixture()
    issue["labels"] = [{"name": "skill-maintenance"}]
    issue["number"] = 7

    monkeypatch.setattr(cycle, "ARTIFACT_ROOT", tmp_path)
    monkeypatch.setattr(cycle, "issue_view", lambda number: issue)
    monkeypatch.setattr(cycle, "git_repo_slug", lambda: "owner/repo")
    monkeypatch.setattr(cycle, "ensure_ask_runtime", lambda: None)
    edit_calls = []
    comment_calls = []
    dispatch_calls = []
    monkeypatch.setattr(cycle, "gh_issue_edit", lambda *args, **kwargs: edit_calls.append((args, kwargs)))
    monkeypatch.setattr(cycle, "gh_issue_comment", lambda *args, **kwargs: comment_calls.append((args, kwargs)))
    monkeypatch.setattr(cycle, "maybe_dispatch_subagent", lambda *args, **kwargs: dispatch_calls.append((args, kwargs)))
    monkeypatch.setattr(
        "sys.argv",
        [
            "skill_maintainer_cycle.py",
            "--issue",
            "7",
            "--require-webgpt",
            "--controlled-live-mutation-fixture",
            "--dispatch-subagents",
        ],
    )

    try:
        cycle.main()
    except SystemExit as exc:
        assert str(exc) == "--controlled-live-mutation-fixture cannot be combined with --dispatch-subagents"
    else:
        raise AssertionError("expected SystemExit")

    assert edit_calls == []
    assert comment_calls == []
    assert dispatch_calls == []


def test_fixture_loop_repair_executor_records_safety_contract(tmp_path, monkeypatch, capsys):
    cycle = load_cycle_module()
    issue = issue_fixture()
    issue["labels"] = [{"name": "skill-bug"}, {"name": "skill-maintenance"}]
    issue["number"] = 71
    fixture = tmp_path / "issue.json"
    fixture.write_text(json.dumps(issue))
    repo = tmp_path / "repo"
    repo.mkdir()

    monkeypatch.setattr(cycle, "ARTIFACT_ROOT", tmp_path / "artifacts")
    monkeypatch.setattr(cycle, "git_repo_slug", lambda: "owner/repo")
    monkeypatch.setattr(cycle, "ensure_ask_runtime", lambda: None)

    loop_calls = []

    def fake_loop_executor(**kwargs):
        loop_calls.append(kwargs)
        issue_dir = kwargs["issue_dir"]
        cycle.write_json(issue_dir / "repair-response.json", {"status": "completed"})
        cycle.write_json(issue_dir / "verifier-response.json", {"status": "completed", "decision": "pass"})
        cycle.write_json(issue_dir / "review-response.json", {"status": "completed", "decision": "pass"})
        return {
            "ok": True,
            "launch": {"cmd": ["loop"]},
            "loop_node_result": {"ok": True},
            "project_agent_fixture_proof": {
                "schema": "skill_maintainer.loop_fixture_proof.v1",
                "package_or_git_sha": "candidate-sha",
                "baseline_sha": "abc123",
                "fresh_loop_id_created": True,
                "verifier_consumed_receipt": True,
                "rollback_command": "git -C /tmp/repo reset --hard abc123",
                "proof_errors": [],
            },
            "proof_out": str(issue_dir / "loop-node-result.json"),
            "final_receipt": str(repo / ".loop" / "runs" / "run" / "final-receipt.json"),
            "changed_files": ["duration_tool/parser.py"],
        }

    monkeypatch.setattr(cycle, "run_loop_repair_executor", fake_loop_executor)
    monkeypatch.setattr(
        "sys.argv",
        [
            "skill_maintainer_cycle.py",
            "--fixture-issue-json",
            str(fixture),
            "--github-dry-run",
            "--require-webgpt",
            "--loop-repair-repo",
            str(repo),
            "--loop-repair-launch-command",
            "python run_loop.py",
            "--loop-scope-include",
            "duration_tool/**",
            "--loop-check-command",
            "python -m unittest discover -s tests",
            "--baseline-git-sha",
            "abc123",
            "--rollback-command",
            "git -C /tmp/repo reset --hard abc123",
        ],
    )

    assert cycle.main() == 0
    output = json.loads(capsys.readouterr().out)

    assert output["status"] == "loop_repair_executor_completed"
    assert output["issue_source"] == "fixture"
    assert output["scheduler_enabled"] is False
    assert output["closure_attempted"] is False
    assert output["destructive_writes"] == []
    assert output["no_lease_needed"] is True
    assert output["lease_released"] is True
    assert output["github_actions"] == []
    assert output["baseline_git_sha"] == "abc123"
    assert output["rollback_command"] == "git -C /tmp/repo reset --hard abc123"
    assert output["project_agent_fixture_proof"]["schema"] == "skill_maintainer.loop_fixture_proof.v1"
    assert output["project_agent_fixture_proof"]["fresh_loop_id_created"] is True
    assert output["project_agent_fixture_proof"]["verifier_consumed_receipt"] is True
    assert output["project_agent_fixture_proof"]["proof_errors"] == []
    assert loop_calls[0]["repo"] == repo.resolve()
    assert loop_calls[0]["scope_include"] == ["duration_tool/**"]
    assert loop_calls[0]["check_commands"] == ["python -m unittest discover -s tests"]


def test_git_worktree_or_branch_uses_actual_branch_name(tmp_path):
    cycle = load_cycle_module()
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    (repo / "README.md").write_text("fixture\n")
    subprocess.run(["git", "add", "README.md"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "initial"], cwd=repo, check=True)
    subprocess.run(["git", "checkout", "-q", "-b", "fixture-proof"], cwd=repo, check=True)

    assert cycle.git_worktree_or_branch(repo) == "fixture-proof"


def test_live_dispatch_aborts_when_lease_fails(tmp_path, monkeypatch):
    cycle = load_cycle_module()
    issue = issue_fixture()
    issue["labels"] = [{"name": "skill-bug"}, {"name": "skill-maintenance"}]
    issue["number"] = 53
    dispatch_calls = []

    monkeypatch.setattr(cycle, "ARTIFACT_ROOT", tmp_path)
    monkeypatch.setattr(cycle, "issue_view", lambda number: issue)
    monkeypatch.setattr(cycle, "git_repo_slug", lambda: "owner/repo")
    monkeypatch.setattr(cycle, "ensure_ask_runtime", lambda: None)
    monkeypatch.setattr(
        cycle,
        "gh_issue_edit",
        lambda *args, **kwargs: {
            "cmd": ["gh", "issue", "edit"],
            "dry_run": False,
            "returncode": 1,
            "stdout": "",
            "stderr": "lease failed",
        },
    )
    monkeypatch.setattr(cycle, "maybe_dispatch_subagent", lambda *args, **kwargs: dispatch_calls.append(args))
    monkeypatch.setattr(
        "sys.argv",
        [
            "skill_maintainer_cycle.py",
            "--issue",
            "53",
            "--require-webgpt",
            "--dispatch-subagents",
        ],
    )

    try:
        cycle.main()
    except SystemExit as exc:
        assert "lease label failed" in str(exc)
    else:
        raise AssertionError("expected SystemExit from failed lease")

    assert dispatch_calls == []


def test_continue_pending_run_waits_for_running_repair(tmp_path):
    cycle = load_cycle_module()
    issue_dir = tmp_path / "20260612T000000Z" / "issue-46"
    issue_dir.mkdir(parents=True)
    (issue_dir / "cycle-result.json").write_text(json.dumps({
        "status": "repair_subagent_started",
        "target_skills": ["scheduler"],
        "subagent_dispatch": [],
        "subagent_specs": {
            "repair_spec": str(issue_dir / "repair_spec.json"),
            "verifier_spec": str(issue_dir / "verifier_spec.json"),
            "review_spec": str(issue_dir / "review_spec.json"),
        },
    }))
    (issue_dir / "issue-snapshot.json").write_text(json.dumps({"number": 46, "url": "https://example.invalid/46"}))
    (issue_dir / "route-decision.json").write_text(json.dumps({
        "route": "ops_or_scheduler",
        "repair_agent": "devops",
        "verifier_agent": "project-or-harness-verifier",
        "review_agent": "code-reviewer",
    }))
    (issue_dir / "repair-response.json").write_text(json.dumps({"status": "running"}))

    result = cycle.continue_pending_run(issue_dir, dry_run=True)

    assert result["continuation_status"] == "waiting_for_repair_receipt"
    assert result["observed_repair_status"] == "running"


def test_continue_pending_run_blocks_invalid_completed_verifier_receipt(tmp_path):
    cycle = load_cycle_module()
    issue_dir = tmp_path / "20260612T000000Z" / "issue-54"
    issue_dir.mkdir(parents=True)
    (issue_dir / "cycle-result.json").write_text(json.dumps({
        "status": "verifier_subagent_started",
        "target_skills": ["scheduler"],
        "closure_decision": "waiting_for_verifier_subagent_receipt",
        "subagent_dispatch": [],
        "subagent_specs": {
            "repair_spec": str(issue_dir / "repair_spec.json"),
            "verifier_spec": str(issue_dir / "verifier_spec.json"),
            "review_spec": str(issue_dir / "review_spec.json"),
        },
    }))
    (issue_dir / "issue-snapshot.json").write_text(json.dumps({"number": 54, "url": "https://example.invalid/54"}))
    (issue_dir / "route-decision.json").write_text(json.dumps({
        "route": "ops_or_scheduler",
        "repair_agent": "devops",
        "verifier_agent": "project-or-harness-verifier",
        "review_agent": "code-reviewer",
    }))
    (issue_dir / "verifier-response.json").write_text(json.dumps({
        "status": "completed",
        "decision": "fail",
        "commands_run": ["pytest failed"],
        "evidence_summary": "tests failed",
    }))

    result = cycle.continue_pending_run(issue_dir, dry_run=True)

    assert result["continuation_status"] == "blocked_invalid_verifier_receipt:nonpassing_decision:fail"
    assert result["closure_decision"] == "blocked_invalid_verifier_receipt:nonpassing_decision:fail"
    assert result["status"] == "blocked_invalid_verifier_receipt:nonpassing_decision:fail"
    assert result["receipt_gate_reason"] == "nonpassing_decision:fail"


def test_continue_pending_run_disposes_failed_repair_receipt_with_github_actions(tmp_path, monkeypatch):
    cycle = load_cycle_module()
    issue_dir = tmp_path / "20260612T000000Z" / "issue-65"
    issue_dir.mkdir(parents=True)
    (issue_dir / "cycle-result.json").write_text(json.dumps({
        "status": "repair_subagent_started",
        "target_skills": ["scheduler"],
        "github_actions": [],
        "subagent_dispatch": [],
        "subagent_specs": {
            "repair_spec": str(issue_dir / "repair_spec.json"),
            "verifier_spec": str(issue_dir / "verifier_spec.json"),
            "review_spec": str(issue_dir / "review_spec.json"),
        },
    }))
    (issue_dir / "issue-snapshot.json").write_text(json.dumps({"number": 65, "url": "https://example.invalid/65"}))
    (issue_dir / "route-decision.json").write_text(json.dumps({
        "route": "ops_or_scheduler",
        "repair_agent": "devops",
        "verifier_agent": "project-or-harness-verifier",
        "review_agent": "code-reviewer",
    }))
    (issue_dir / "repair-response.json").write_text(json.dumps({
        "status": "failed",
        "commands_run": ["repair command"],
        "evidence_summary": "repair failed",
    }))
    monkeypatch.setattr(
        cycle,
        "gh_issue_comment",
        lambda issue_number, body_path, dry_run=False: {
            "cmd": ["gh", "issue", "comment", str(issue_number)],
            "dry_run": dry_run,
            "returncode": 0,
            "stdout": "",
            "stderr": "",
        },
    )
    monkeypatch.setattr(
        cycle,
        "gh_issue_edit",
        lambda issue_number, *args, dry_run=False: {
            "cmd": ["gh", "issue", "edit", str(issue_number), *args],
            "dry_run": dry_run,
            "returncode": 0,
            "stdout": "",
            "stderr": "",
        },
    )

    result = cycle.continue_pending_run(issue_dir, dry_run=False, github_dry_run=True)

    assert result["status"].startswith("blocked_invalid_repair_receipt")
    assert [action["action"] for action in result["github_actions"]] == [
        "terminal_blocked_comment",
        "terminal_blocked_labels_release_lease",
    ]
    assert all(action["dry_run"] for action in result["github_actions"])


def test_non_webgpt_terminal_disposition_failure_retries_next_cycle(tmp_path, monkeypatch):
    cycle = load_cycle_module()
    issue_dir = tmp_path / "20260612T000000Z" / "issue-71"
    issue_dir.mkdir(parents=True)
    (issue_dir / "cycle-result.json").write_text(json.dumps({
        "status": "repair_subagent_started",
        "target_skills": ["scheduler"],
        "github_actions": [],
        "subagent_dispatch": [],
        "subagent_specs": {},
    }))
    (issue_dir / "issue-snapshot.json").write_text(json.dumps({"number": 71, "url": "https://example.invalid/71"}))
    (issue_dir / "route-decision.json").write_text(json.dumps({
        "route": "ops_or_scheduler",
        "repair_agent": "devops",
        "verifier_agent": "project-or-harness-verifier",
        "review_agent": "code-reviewer",
    }))
    (issue_dir / "repair-response.json").write_text(json.dumps({
        "status": "failed",
        "commands_run": ["repair command"],
        "evidence_summary": "repair failed",
    }))
    monkeypatch.setattr(
        cycle,
        "gh_issue_comment",
        lambda issue_number, body_path, dry_run=False: {
            "cmd": ["gh", "issue", "comment", str(issue_number)],
            "dry_run": dry_run,
            "returncode": 1,
            "stdout": "",
            "stderr": "api unavailable",
        },
    )

    first = cycle.continue_pending_run(issue_dir, dry_run=False, github_dry_run=False)
    monkeypatch.setattr(cycle, "ARTIFACT_ROOT", tmp_path)

    assert first["terminal_disposition_status"] == "failed"
    assert cycle.latest_pending_issue_dir() == issue_dir

    mock_successful_github_terminal_disposition(monkeypatch, cycle)
    retry = cycle.continue_pending_run(issue_dir, dry_run=False, github_dry_run=False)

    assert retry["terminal_disposition_retry"] is True
    assert retry["terminal_disposition_status"] == "completed"
    assert retry["status"].startswith("blocked_invalid_repair_receipt")


def test_continue_pending_run_terminalizes_verifier_dispatch_failure(tmp_path, monkeypatch):
    cycle = load_cycle_module()
    issue_dir = tmp_path / "20260612T000000Z" / "issue-66"
    issue_dir.mkdir(parents=True)
    (issue_dir / "cycle-result.json").write_text(json.dumps({
        "status": "repair_subagent_started",
        "target_skills": ["scheduler"],
        "github_actions": [],
        "subagent_dispatch": [],
        "subagent_specs": {
            "repair_spec": str(issue_dir / "repair_spec.json"),
            "verifier_spec": str(issue_dir / "verifier_spec.json"),
            "review_spec": str(issue_dir / "review_spec.json"),
        },
    }))
    (issue_dir / "issue-snapshot.json").write_text(json.dumps({"number": 66, "url": "https://example.invalid/66"}))
    (issue_dir / "route-decision.json").write_text(json.dumps({
        "route": "ops_or_scheduler",
        "repair_agent": "devops",
        "verifier_agent": "project-or-harness-verifier",
        "review_agent": "code-reviewer",
    }))
    (issue_dir / "repair-response.json").write_text(json.dumps({
        "status": "completed",
        "commands_run": ["repair command"],
        "evidence_summary": "repair evidence",
    }))
    monkeypatch.setattr(
        cycle,
        "maybe_dispatch_subagent",
        lambda spec_path, dry_run=False: {
            "cmd": ["bash", "skills/subagent-runner/run.sh", "start", spec_path],
            "dry_run": dry_run,
            "returncode": 2,
            "stdout": "",
            "stderr": "start failed",
        },
    )
    monkeypatch.setattr(cycle, "gh_issue_comment", lambda issue_number, body_path, dry_run=False: {"cmd": [], "dry_run": dry_run, "returncode": 0, "stdout": "", "stderr": ""})
    monkeypatch.setattr(cycle, "gh_issue_edit", lambda issue_number, *args, dry_run=False: {"cmd": [], "dry_run": dry_run, "returncode": 0, "stdout": "", "stderr": ""})

    result = cycle.continue_pending_run(issue_dir, dry_run=False, github_dry_run=True)

    assert result["status"] == "blocked_verifier_subagent_start_failed"
    assert result["closure_decision"] == "blocked_verifier_subagent_start_failed"
    assert result["github_actions"][0]["action"] == "terminal_blocked_comment"


def test_continue_pending_run_dispatches_verifier_after_completed_repair(tmp_path, monkeypatch):
    cycle = load_cycle_module()
    issue_dir = tmp_path / "20260612T000000Z" / "issue-47"
    issue_dir.mkdir(parents=True)
    verifier_spec = issue_dir / "verifier_spec.json"
    (issue_dir / "cycle-result.json").write_text(json.dumps({
        "status": "repair_subagent_started",
        "target_skills": ["scheduler"],
        "subagent_dispatch": [],
        "subagent_specs": {
            "repair_spec": str(issue_dir / "repair_spec.json"),
            "verifier_spec": str(verifier_spec),
            "review_spec": str(issue_dir / "review_spec.json"),
        },
    }))
    (issue_dir / "issue-snapshot.json").write_text(json.dumps({"number": 47, "url": "https://example.invalid/47"}))
    (issue_dir / "route-decision.json").write_text(json.dumps({
        "route": "ops_or_scheduler",
        "repair_agent": "devops",
        "verifier_agent": "project-or-harness-verifier",
        "review_agent": "code-reviewer",
    }))
    (issue_dir / "repair-response.json").write_text(json.dumps({
        "status": "completed",
        "commands_run": ["repair command"],
        "evidence_summary": "repair evidence",
    }))
    monkeypatch.setattr(
        cycle,
        "maybe_dispatch_subagent",
        lambda spec_path, dry_run=False: {
            "cmd": ["bash", "skills/subagent-runner/run.sh", "start", spec_path],
            "dry_run": dry_run,
            "returncode": 0,
            "stdout": json.dumps({
                "session_id": "skill-maintainer-issue-47-verify-def456",
                "status": "starting",
                "artifact_dir": "/tmp/subagent-sessions/verifier",
                "watcher_pid": 22222,
            }),
            "stderr": "",
        },
    )

    result = cycle.continue_pending_run(issue_dir, dry_run=False)

    assert result["status"] == "verifier_subagent_started"
    assert result["closure_decision"] == "waiting_for_verifier_subagent_receipt"
    assert result["verifier_session"]["session_id"] == "skill-maintainer-issue-47-verify-def456"
    verifier = json.loads((issue_dir / "verifier-response.json").read_text())
    assert verifier["status"] == "running"
    assert verifier["subagent_dispatch"]["stdout_json"]["artifact_dir"] == "/tmp/subagent-sessions/verifier"


def test_receipt_gate_accepts_well_formed_repaired_repair_receipt():
    cycle = load_cycle_module()

    ok, reason = cycle.receipt_gate(
        {
            "status": "repaired",
            "summary": "Patched the targeted runtime behavior.",
            "files_changed": ["skills/surf/scripts/webgpt-submit.sh"],
            "proof": [
                {
                    "command": "pytest skills/surf/tests -q",
                    "result": "15 passed",
                }
            ],
        },
        phase="repair",
    )

    assert ok is True
    assert reason == "pass"


def test_receipt_gate_rejects_repaired_repair_receipt_without_proof():
    cycle = load_cycle_module()

    ok, reason = cycle.receipt_gate(
        {
            "status": "repaired",
            "summary": "Patched the targeted runtime behavior.",
            "files_changed": ["skills/surf/scripts/webgpt-submit.sh"],
        },
        phase="repair",
    )

    assert ok is False
    assert reason == "missing_repair_proof"


def test_receipt_gate_accepts_completed_repair_receipt_with_summary():
    cycle = load_cycle_module()

    ok, reason = cycle.receipt_gate(
        {
            "status": "completed",
            "summary": "Implemented and tested the feature.",
            "changed_files": ["skills/fact-extractor/fact_extractor/cli.py"],
            "commands_run": [{"command": "pytest", "exit_code": 0}],
        },
        phase="repair",
    )

    assert ok is True
    assert reason == "pass"


def test_scoped_publication_paths_exclude_artifacts_and_abs_paths(tmp_path, monkeypatch):
    cycle = load_cycle_module()
    (tmp_path / "skills" / "fact-extractor").mkdir(parents=True)
    (tmp_path / "skills" / "fact-extractor" / "SKILL.md").write_text("skill")
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "tool.py").write_text("tool")
    monkeypatch.setattr(cycle, "REPO_ROOT", tmp_path)

    paths = cycle.scoped_publication_paths(
        {
            "target_paths": [
                "skills/fact-extractor/SKILL.md",
                ".artifacts/run/output.json",
                "/tmp/outside.py",
            ]
        },
        {
            "changed_files": [
                ".artifacts/run/repair-response.json",
                "scripts/tool.py",
                "../outside.py",
            ],
            "implementation_files_verified": [
                {"path": "skills/fact-extractor/SKILL.md"},
            ],
        },
    )

    assert paths == ["skills/fact-extractor/SKILL.md", "scripts/tool.py"]


def test_scoped_publication_paths_accepts_tracked_deleted_file(tmp_path, monkeypatch):
    cycle = load_cycle_module()
    deleted = tmp_path / "skills" / "agent-status" / "README.md"
    deleted.parent.mkdir(parents=True)
    deleted.write_text("duplicate docs\n")
    monkeypatch.setattr(cycle, "REPO_ROOT", tmp_path)
    calls = []

    class _CP:
        def __init__(self, returncode=0):
            self.returncode = returncode
            self.stdout = ""
            self.stderr = ""

    def fake_git_run(args, check=False):
        calls.append(args)
        if args == ["ls-files", "--error-unmatch", "--", "skills/agent-status/README.md"]:
            return _CP(0)
        return _CP(1)

    monkeypatch.setattr(cycle, "git_run", fake_git_run)
    deleted.unlink()

    paths = cycle.scoped_publication_paths(
        {"target_paths": ["skills/agent-status"]},
        {"files_changed": ["skills/agent-status/README.md"]},
    )

    assert paths == ["skills/agent-status/README.md"]
    assert ["ls-files", "--error-unmatch", "--", "skills/agent-status/README.md"] in calls


def test_publish_scoped_changes_commits_only_allowlisted_paths(tmp_path, monkeypatch):
    cycle = load_cycle_module()
    issue_dir = tmp_path / "issue"
    issue_dir.mkdir()
    (tmp_path / "skills" / "fact-extractor").mkdir(parents=True)
    (tmp_path / "skills" / "fact-extractor" / "SKILL.md").write_text("skill")
    (tmp_path / "unrelated.py").write_text("do not stage")
    monkeypatch.setattr(cycle, "REPO_ROOT", tmp_path)
    calls = []

    class _CP:
        def __init__(self, returncode=0, stdout="", stderr=""):
            self.returncode = returncode
            self.stdout = stdout
            self.stderr = stderr

    def fake_git_run(args, check=False):
        calls.append(args)
        if args[:4] == ["diff", "--cached", "--name-only", "--"]:
            return _CP(stdout="skills/fact-extractor/SKILL.md\n")
        if args == ["rev-parse", "HEAD"]:
            return _CP(stdout="abc123\n")
        return _CP()

    monkeypatch.setattr(cycle, "git_run", fake_git_run)

    publication = cycle.publish_scoped_changes(
        issue_dir,
        {"issue": 8, "target_paths": ["skills/fact-extractor/SKILL.md"]},
        {"changed_files": [".artifacts/output.json"]},
        dry_run=False,
        github_dry_run=False,
    )

    assert publication["status"] == "committed"
    assert publication["commit"] == "abc123"
    assert ["add", "--", "skills/fact-extractor/SKILL.md"] in calls
    assert ["commit", "-m", "Fix skill-maintainer issue #8", "--", "skills/fact-extractor/SKILL.md"] in calls
    assert ["reset", "--quiet"] not in calls
    assert all("unrelated.py" not in call for call in calls)
    assert all("add" not in call or "." not in call for call in calls)


def test_receipt_gate_does_not_accept_repaired_for_verifier_or_review():
    cycle = load_cycle_module()
    receipt = {
        "status": "repaired",
        "summary": "This is not a verifier status.",
        "files_changed": ["skills/surf/scripts/webgpt-submit.sh"],
        "proof": [{"command": "pytest", "result": "passed"}],
    }

    assert cycle.receipt_gate(receipt, phase="deterministic_verification") == (False, "repaired")
    assert cycle.receipt_gate(receipt, phase="independent_review") == (False, "repaired")


def test_receipt_gate_accepts_result_pass_for_verifier_receipt():
    cycle = load_cycle_module()

    ok, reason = cycle.receipt_gate(
        {
            "status": "completed",
            "result": "pass",
            "commands_run": [{"cmd": "pytest", "returncode": 0}],
            "evidence_summary": ["deterministic tests passed"],
            "findings": [],
        },
        phase="deterministic_verification",
    )

    assert ok is True
    assert reason == "pass"


def test_receipt_gate_blocks_result_pass_with_findings():
    cycle = load_cycle_module()

    ok, reason = cycle.receipt_gate(
        {
            "status": "completed",
            "result": "pass",
            "commands_run": [{"cmd": "pytest", "returncode": 0}],
            "evidence_summary": ["deterministic tests passed"],
            "findings": ["unresolved issue"],
        },
        phase="deterministic_verification",
    )

    assert ok is False
    assert reason == "blocking_findings_present"


def test_continue_pending_run_dispatches_verifier_after_repaired_repair(tmp_path, monkeypatch):
    cycle = load_cycle_module()
    issue_dir = tmp_path / "20260612T000000Z" / "issue-76"
    issue_dir.mkdir(parents=True)
    verifier_spec = issue_dir / "verifier_spec.json"
    (issue_dir / "cycle-result.json").write_text(json.dumps({
        "status": "repair_subagent_started",
        "target_skills": ["surf"],
        "subagent_dispatch": [],
        "subagent_specs": {
            "repair_spec": str(issue_dir / "repair_spec.json"),
            "verifier_spec": str(verifier_spec),
            "review_spec": str(issue_dir / "review_spec.json"),
        },
    }))
    (issue_dir / "issue-snapshot.json").write_text(json.dumps({"number": 76, "url": "https://example.invalid/76"}))
    (issue_dir / "route-decision.json").write_text(json.dumps({
        "route": "backend_python_or_skill_runtime",
        "repair_agent": "coder",
        "verifier_agent": "project-or-harness-verifier",
        "review_agent": "code-reviewer",
    }))
    (issue_dir / "repair-response.json").write_text(json.dumps({
        "status": "repaired",
        "summary": "Patched WebGPT tab recovery.",
        "files_changed": ["skills/surf/scripts/webgpt-submit.sh"],
        "proof": [{"command": "pytest skills/surf/tests -q", "result": "15 passed"}],
    }))
    monkeypatch.setattr(
        cycle,
        "maybe_dispatch_subagent",
        lambda spec_path, dry_run=False: {
            "cmd": ["bash", "skills/subagent-runner/run.sh", "start", spec_path],
            "dry_run": dry_run,
            "returncode": 0,
            "stdout": json.dumps({
                "session_id": "skill-maintainer-issue-76-verify-def456",
                "status": "starting",
                "artifact_dir": "/tmp/subagent-sessions/verifier",
                "watcher_pid": 22222,
            }),
            "stderr": "",
        },
    )

    result = cycle.continue_pending_run(issue_dir, dry_run=False)

    assert result["status"] == "verifier_subagent_started"
    assert result["closure_decision"] == "waiting_for_verifier_subagent_receipt"
    assert result["verifier_session"]["session_id"] == "skill-maintainer-issue-76-verify-def456"


def test_continue_pending_run_resumes_terminalized_invalid_repair_after_gate_fix(tmp_path, monkeypatch):
    cycle = load_cycle_module()
    issue_dir = tmp_path / "20260612T000000Z" / "issue-78"
    issue_dir.mkdir(parents=True)
    verifier_spec = issue_dir / "verifier_spec.json"
    (issue_dir / "cycle-result.json").write_text(json.dumps({
        "status": "blocked_invalid_repair_receipt:missing_evidence_summary",
        "closure_decision": "blocked_invalid_repair_receipt:missing_evidence_summary",
        "terminal_disposition_status": "completed",
        "target_skills": ["fact-extractor"],
        "subagent_dispatch": [],
        "subagent_specs": {
            "repair_spec": str(issue_dir / "repair_spec.json"),
            "verifier_spec": str(verifier_spec),
            "review_spec": str(issue_dir / "review_spec.json"),
        },
    }))
    (issue_dir / "issue-snapshot.json").write_text(json.dumps({"number": 78, "url": "https://example.invalid/78"}))
    (issue_dir / "route-decision.json").write_text(json.dumps({
        "route": "backend_python_or_skill_runtime",
        "repair_agent": "coder",
        "verifier_agent": "project-or-harness-verifier",
        "review_agent": "code-reviewer",
    }))
    (issue_dir / "repair-response.json").write_text(json.dumps({
        "status": "completed",
        "summary": "Implemented book progress logging.",
        "changed_files": ["skills/fact-extractor/fact_extractor/cli.py"],
        "commands_run": [{"command": "pytest", "exit_code": 0}],
    }))
    monkeypatch.setattr(
        cycle,
        "maybe_dispatch_subagent",
        lambda spec_path, dry_run=False: {
            "cmd": ["bash", "skills/subagent-runner/run.sh", "start", spec_path],
            "dry_run": dry_run,
            "returncode": 0,
            "stdout": json.dumps({
                "session_id": "skill-maintainer-issue-78-verify-resumed",
                "status": "starting",
                "artifact_dir": "/tmp/subagent-sessions/verifier",
                "watcher_pid": 33333,
            }),
            "stderr": "",
        },
    )

    result = cycle.continue_pending_run(issue_dir, dry_run=False)

    assert result["status"] == "verifier_subagent_started"
    assert result["terminal_disposition_status"] == "superseded_by_valid_repair_receipt"
    assert result["verifier_session"]["session_id"] == "skill-maintainer-issue-78-verify-resumed"


def test_continue_pending_run_closes_after_completed_review_when_webgpt_not_required(tmp_path):
    cycle = load_cycle_module()
    issue_dir = tmp_path / "20260612T000000Z" / "issue-50"
    issue_dir.mkdir(parents=True)
    repo_root = tmp_path / "repo"
    (repo_root / "skills" / "scheduler").mkdir(parents=True)
    (repo_root / "skills" / "scheduler" / "SKILL.md").write_text("scheduler")
    cycle.REPO_ROOT = repo_root
    (issue_dir / "cycle-result.json").write_text(json.dumps({
        "status": "review_subagent_started",
        "closure_decision": "waiting_for_review_subagent_receipt",
        "target_skills": ["scheduler"],
        "target_paths": ["skills/scheduler/SKILL.md"],
        "required_next_evidence": ["review-response.json"],
        "subagent_dispatch": [],
        "subagent_specs": {
            "repair_spec": str(issue_dir / "repair_spec.json"),
            "verifier_spec": str(issue_dir / "verifier_spec.json"),
            "review_spec": str(issue_dir / "review_spec.json"),
        },
    }))
    (issue_dir / "issue-snapshot.json").write_text(json.dumps({"number": 50, "url": "https://example.invalid/50"}))
    (issue_dir / "route-decision.json").write_text(json.dumps({
        "route": "ops_or_scheduler",
        "repair_agent": "devops",
        "verifier_agent": "project-or-harness-verifier",
        "review_agent": "code-reviewer",
    }))
    (issue_dir / "repair-response.json").write_text(json.dumps({
        "status": "completed",
        "commands_run": ["repair command"],
        "evidence_summary": "repair evidence",
    }))
    (issue_dir / "verifier-response.json").write_text(json.dumps({
        "status": "completed",
        "decision": "pass",
        "commands_run": ["verify command"],
        "evidence_summary": "verifier evidence",
        "blocking_findings": [],
    }))
    (issue_dir / "review-response.json").write_text(json.dumps({
        "status": "completed",
        "decision": "pass",
        "commands_run": ["review command"],
        "evidence_summary": "review evidence",
        "blocking_findings": [],
    }))

    result = cycle.continue_pending_run(issue_dir, dry_run=True)

    assert result["dry_run_simulation"]["action"] == "terminal_success_dispose"
    assert result["continuation_status"] == "fixed_with_deterministic_proof"
    assert result["closure_decision"] == "close_from_deterministic_proof"
    assert result["required_next_evidence"] == []


def test_continue_pending_run_blocks_after_completed_review_when_webgpt_required(tmp_path):
    cycle = load_cycle_module()
    issue_dir = tmp_path / "20260612T000000Z" / "issue-50"
    issue_dir.mkdir(parents=True)
    (issue_dir / "cycle-result.json").write_text(json.dumps({
        "status": "review_subagent_started",
        "closure_decision": "waiting_for_review_subagent_receipt",
        "target_skills": ["scheduler"],
        "required_next_evidence": ["review-response.json"],
        "subagent_dispatch": [],
        "subagent_specs": {
            "repair_spec": str(issue_dir / "repair_spec.json"),
            "verifier_spec": str(issue_dir / "verifier_spec.json"),
            "review_spec": str(issue_dir / "review_spec.json"),
        },
    }))
    (issue_dir / "issue-snapshot.json").write_text(json.dumps({"number": 50, "url": "https://example.invalid/50"}))
    (issue_dir / "route-decision.json").write_text(json.dumps({
        "route": "ops_or_scheduler",
        "repair_agent": "devops",
        "verifier_agent": "project-or-harness-verifier",
        "review_agent": "code-reviewer",
    }))
    (issue_dir / "repair-response.json").write_text(json.dumps({
        "status": "completed",
        "commands_run": ["repair command"],
        "evidence_summary": "repair evidence",
    }))
    (issue_dir / "verifier-response.json").write_text(json.dumps({
        "status": "completed",
        "decision": "pass",
        "commands_run": ["verify command"],
        "evidence_summary": "verifier evidence",
        "blocking_findings": [],
    }))
    (issue_dir / "review-response.json").write_text(json.dumps({
        "status": "completed",
        "decision": "pass",
        "commands_run": ["review command"],
        "evidence_summary": "review evidence",
        "blocking_findings": [],
    }))

    result = cycle.continue_pending_run(issue_dir, dry_run=True, require_webgpt=True)

    assert result["continuation_status"] == "blocked_waiting_for_webgpt_and_closure_wiring"
    assert result["closure_decision"] == "blocked_waiting_for_webgpt_and_closure_wiring"
    assert result["observed_review_status"] == "completed"
    assert result["required_next_evidence"][0].startswith("ask-webgpt-result.json")


def test_continue_pending_run_can_run_webgpt_after_completed_review(tmp_path, monkeypatch):
    cycle = load_cycle_module()
    issue_dir = tmp_path / "20260612T000000Z" / "issue-51"
    issue_dir.mkdir(parents=True)
    (issue_dir / "cycle-result.json").write_text(json.dumps({
        "status": "review_subagent_started",
        "closure_decision": "waiting_for_review_subagent_receipt",
        "target_skills": ["scheduler"],
        "required_next_evidence": ["review-response.json"],
        "subagent_dispatch": [],
        "subagent_specs": {
            "repair_spec": str(issue_dir / "repair_spec.json"),
            "verifier_spec": str(issue_dir / "verifier_spec.json"),
            "review_spec": str(issue_dir / "review_spec.json"),
        },
    }))
    (issue_dir / "issue-snapshot.json").write_text(json.dumps({"number": 51, "url": "https://example.invalid/51"}))
    (issue_dir / "route-decision.json").write_text(json.dumps({
        "route": "ops_or_scheduler",
        "repair_agent": "devops",
        "verifier_agent": "project-or-harness-verifier",
        "review_agent": "code-reviewer",
    }))
    (issue_dir / "repair-response.json").write_text(json.dumps({
        "status": "completed",
        "commands_run": ["repair command"],
        "evidence_summary": "repair evidence",
    }))
    (issue_dir / "verifier-response.json").write_text(json.dumps({
        "status": "completed",
        "decision": "pass",
        "commands_run": ["verify command"],
        "evidence_summary": "verifier evidence",
        "blocking_findings": [],
    }))
    (issue_dir / "review-response.json").write_text(json.dumps({
        "status": "completed",
        "decision": "pass",
        "commands_run": ["review command"],
        "evidence_summary": "review evidence",
        "blocking_findings": [],
    }))
    (issue_dir / "review-bundle.md").write_text("# Review bundle\n")
    monkeypatch.setattr(
        cycle,
        "maybe_run_webgpt",
        lambda bundle, dry_run=False: {
            "cmd": ["bash", "skills/ask/run.sh", "webgpt-review", "--bundle", str(bundle)],
            "dry_run": dry_run,
            "returncode": 0,
            "stdout": '{"review":"ok"}',
            "stderr": "",
        },
    )
    mock_successful_github_terminal_disposition(monkeypatch, cycle)

    result = cycle.continue_pending_run(
        issue_dir,
        dry_run=False,
        github_dry_run=False,
        run_webgpt=True,
        require_webgpt=True,
    )

    assert result["continuation_status"] == "blocked_waiting_for_finding_disposition_and_closure_wiring"
    assert result["closure_decision"] == "blocked_waiting_for_finding_disposition_and_closure_wiring"
    assert result["status"] == "webgpt_review_attempted"
    assert result["terminal_disposition_status"] == "completed"
    assert [action["action"] for action in result["github_actions"]] == [
        "terminal_blocked_comment",
        "terminal_blocked_labels_release_lease",
    ]
    webgpt = json.loads((issue_dir / "ask-webgpt-result.json").read_text())
    assert webgpt["status"] == "completed"
    assert webgpt["returncode"] == 0


def test_continue_pending_run_runs_webgpt_but_skips_disposition_under_github_dry_run(tmp_path, monkeypatch):
    cycle = load_cycle_module()
    issue_dir = tmp_path / "20260612T000000Z" / "issue-77"
    issue_dir.mkdir(parents=True)
    (issue_dir / "cycle-result.json").write_text(json.dumps({
        "status": "review_subagent_started",
        "closure_decision": "waiting_for_review_subagent_receipt",
        "target_skills": ["surf"],
        "github_actions": [],
        "subagent_dispatch": [],
        "subagent_specs": {},
    }))
    (issue_dir / "issue-snapshot.json").write_text(json.dumps({"number": 77, "url": "https://example.invalid/77"}))
    (issue_dir / "route-decision.json").write_text(json.dumps({
        "route": "backend_python_or_skill_runtime",
        "repair_agent": "coder",
        "verifier_agent": "project-or-harness-verifier",
        "review_agent": "code-reviewer",
    }))
    (issue_dir / "repair-response.json").write_text(json.dumps({
        "status": "repaired",
        "summary": "Patched WebGPT tab recovery.",
        "files_changed": ["skills/surf/scripts/webgpt-submit.sh"],
        "proof": [{"command": "pytest skills/surf/tests -q", "result": "15 passed"}],
    }))
    (issue_dir / "verifier-response.json").write_text(json.dumps({
        "status": "completed",
        "result": "pass",
        "commands_run": [{"cmd": "pytest", "returncode": 0}],
        "evidence_summary": ["verifier evidence"],
        "findings": [],
    }))
    (issue_dir / "review-response.json").write_text(json.dumps({
        "status": "completed",
        "result": "pass",
        "commands_run": [{"cmd": "pytest", "returncode": 0}],
        "evidence_summary": ["review evidence"],
        "findings": [],
    }))
    (issue_dir / "review-bundle.md").write_text("# Review bundle\n")
    monkeypatch.setattr(
        cycle,
        "maybe_run_webgpt",
        lambda bundle, dry_run=False: {
            "cmd": ["bash", "skills/ask/run.sh", "webgpt-review", "--bundle", str(bundle)],
            "dry_run": dry_run,
            "returncode": 0,
            "stdout": '{"review":"ok"}',
            "stderr": "",
        },
    )
    monkeypatch.setattr(cycle, "gh_issue_comment", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("no GitHub comment")))
    monkeypatch.setattr(cycle, "gh_issue_edit", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("no GitHub edit")))

    result = cycle.continue_pending_run(issue_dir, dry_run=False, github_dry_run=True, run_webgpt=True)

    assert result["status"] == "webgpt_review_attempted"
    assert result["github_disposition_skipped"] == "github_dry_run"
    assert "terminal_disposition_status" not in result
    webgpt = json.loads((issue_dir / "ask-webgpt-result.json").read_text())
    assert webgpt["status"] == "completed"
    assert webgpt["returncode"] == 0


def test_continue_pending_run_records_webgpt_dry_run_status(tmp_path, monkeypatch):
    cycle = load_cycle_module()
    issue_dir = tmp_path / "20260612T000000Z" / "issue-52"
    issue_dir.mkdir(parents=True)
    (issue_dir / "cycle-result.json").write_text(json.dumps({
        "status": "review_subagent_started",
        "target_skills": ["scheduler"],
        "subagent_dispatch": [],
        "subagent_specs": {},
    }))
    (issue_dir / "issue-snapshot.json").write_text(json.dumps({"number": 52, "url": "https://example.invalid/52"}))
    (issue_dir / "route-decision.json").write_text(json.dumps({
        "route": "ops_or_scheduler",
        "repair_agent": "devops",
        "verifier_agent": "project-or-harness-verifier",
        "review_agent": "code-reviewer",
    }))
    (issue_dir / "repair-response.json").write_text(json.dumps({
        "status": "completed",
        "commands_run": ["repair command"],
        "evidence_summary": "repair evidence",
    }))
    (issue_dir / "verifier-response.json").write_text(json.dumps({
        "status": "completed",
        "decision": "pass",
        "commands_run": ["verify command"],
        "evidence_summary": "verifier evidence",
        "blocking_findings": [],
    }))
    (issue_dir / "review-response.json").write_text(json.dumps({
        "status": "completed",
        "decision": "pass",
        "commands_run": ["review command"],
        "evidence_summary": "review evidence",
        "blocking_findings": [],
    }))
    (issue_dir / "review-bundle.md").write_text("# Review bundle\n")
    monkeypatch.setattr(
        cycle,
        "maybe_run_webgpt",
        lambda bundle, dry_run=False: {
            "cmd": ["bash", "skills/ask/run.sh", "webgpt-review"],
            "dry_run": dry_run,
            "returncode": 0,
            "stdout": "",
            "stderr": "",
        },
    )

    result = cycle.continue_pending_run(issue_dir, dry_run=True, run_webgpt=True)

    assert result["last_invocation_dry_run"] is True
    assert result["run_webgpt"] is True
    assert result["dry_run_simulation"]["action"] == "run_webgpt"
    assert not (issue_dir / "ask-webgpt-result.json").exists()


def test_continue_pending_run_does_not_resubmit_existing_webgpt_result(tmp_path, monkeypatch):
    cycle = load_cycle_module()
    issue_dir = tmp_path / "20260612T000000Z" / "issue-55"
    issue_dir.mkdir(parents=True)
    (issue_dir / "cycle-result.json").write_text(json.dumps({
        "status": "review_subagent_started",
        "target_skills": ["scheduler"],
        "subagent_dispatch": [],
        "subagent_specs": {},
    }))
    (issue_dir / "issue-snapshot.json").write_text(json.dumps({"number": 55, "url": "https://example.invalid/55"}))
    (issue_dir / "route-decision.json").write_text(json.dumps({
        "route": "ops_or_scheduler",
        "repair_agent": "devops",
        "verifier_agent": "project-or-harness-verifier",
        "review_agent": "code-reviewer",
    }))
    (issue_dir / "repair-response.json").write_text(json.dumps({
        "status": "completed",
        "commands_run": ["repair command"],
        "evidence_summary": "repair evidence",
    }))
    (issue_dir / "verifier-response.json").write_text(json.dumps({
        "status": "completed",
        "decision": "pass",
        "commands_run": ["verify command"],
        "evidence_summary": "verifier evidence",
        "blocking_findings": [],
    }))
    (issue_dir / "review-response.json").write_text(json.dumps({
        "status": "completed",
        "decision": "pass",
        "commands_run": ["review command"],
        "evidence_summary": "review evidence",
        "blocking_findings": [],
    }))
    (issue_dir / "ask-webgpt-result.json").write_text(json.dumps({"status": "completed"}))
    calls = []
    monkeypatch.setattr(cycle, "maybe_run_webgpt", lambda *args, **kwargs: calls.append(args))
    mock_successful_github_terminal_disposition(monkeypatch, cycle)

    result = cycle.continue_pending_run(
        issue_dir,
        dry_run=False,
        github_dry_run=False,
        run_webgpt=True,
        require_webgpt=True,
    )

    assert calls == []
    assert result["observed_webgpt_status"] == "completed"
    assert result["closure_decision"] == "blocked_waiting_for_finding_disposition_and_closure_wiring"
    assert result["terminal_disposition_status"] == "completed"
    assert [action["action"] for action in result["github_actions"]] == [
        "terminal_blocked_comment",
        "terminal_blocked_labels_release_lease",
    ]


def test_latest_pending_issue_dir_skips_terminal_webgpt_receipts(tmp_path, monkeypatch):
    cycle = load_cycle_module()
    old_issue_dir = tmp_path / "20260612T000000Z" / "issue-57"
    old_issue_dir.mkdir(parents=True)
    (old_issue_dir / "cycle-result.json").write_text(json.dumps({
        "status": "webgpt_review_attempted",
        "terminal_disposition_status": "completed",
    }))
    (old_issue_dir / "ask-webgpt-result.json").write_text(json.dumps({"status": "completed"}))
    pending_issue_dir = tmp_path / "20260612T000001Z" / "issue-58"
    pending_issue_dir.mkdir(parents=True)
    (pending_issue_dir / "cycle-result.json").write_text(json.dumps({"status": "repair_subagent_started"}))
    monkeypatch.setattr(cycle, "ARTIFACT_ROOT", tmp_path)

    assert cycle.latest_pending_issue_dir() == pending_issue_dir


def test_latest_pending_issue_dir_retries_terminal_webgpt_without_completed_disposition(tmp_path, monkeypatch):
    cycle = load_cycle_module()
    retry_issue_dir = tmp_path / "20260612T000000Z" / "issue-69"
    retry_issue_dir.mkdir(parents=True)
    (retry_issue_dir / "cycle-result.json").write_text(json.dumps({
        "status": "webgpt_review_attempted",
        "terminal_disposition_status": "failed",
    }))
    (retry_issue_dir / "ask-webgpt-result.json").write_text(json.dumps({"status": "completed"}))
    monkeypatch.setattr(cycle, "ARTIFACT_ROOT", tmp_path)

    assert cycle.latest_pending_issue_dir() == retry_issue_dir


def test_github_dry_run_runs_webgpt_but_does_not_write_terminal_disposition(tmp_path, monkeypatch):
    cycle = load_cycle_module()
    issue_dir = tmp_path / "20260612T000000Z" / "issue-70"
    issue_dir.mkdir(parents=True)
    (issue_dir / "cycle-result.json").write_text(json.dumps({
        "status": "review_subagent_started",
        "target_skills": ["scheduler"],
        "subagent_dispatch": [],
        "subagent_specs": {},
    }))
    (issue_dir / "issue-snapshot.json").write_text(json.dumps({"number": 70, "url": "https://example.invalid/70"}))
    (issue_dir / "route-decision.json").write_text(json.dumps({
        "route": "ops_or_scheduler",
        "repair_agent": "devops",
        "verifier_agent": "project-or-harness-verifier",
        "review_agent": "code-reviewer",
    }))
    (issue_dir / "repair-response.json").write_text(json.dumps({
        "status": "completed",
        "commands_run": ["repair command"],
        "evidence_summary": "repair evidence",
    }))
    (issue_dir / "verifier-response.json").write_text(json.dumps({
        "status": "completed",
        "decision": "pass",
        "commands_run": ["verify command"],
        "evidence_summary": "verifier evidence",
        "blocking_findings": [],
    }))
    (issue_dir / "review-response.json").write_text(json.dumps({
        "status": "completed",
        "decision": "pass",
        "commands_run": ["review command"],
        "evidence_summary": "review evidence",
        "blocking_findings": [],
    }))
    (issue_dir / "review-bundle.md").write_text("# Review bundle\n")
    monkeypatch.setattr(
        cycle,
        "maybe_run_webgpt",
        lambda bundle, dry_run=False: {
            "cmd": ["bash", "skills/ask/run.sh", "webgpt-review", "--bundle", str(bundle)],
            "dry_run": dry_run,
            "returncode": 0,
            "stdout": '{"review":"ok"}',
            "stderr": "",
        },
    )

    result = cycle.continue_pending_run(issue_dir, dry_run=False, github_dry_run=True, run_webgpt=True)

    assert result["status"] == "webgpt_review_attempted"
    assert result["github_disposition_skipped"] == "github_dry_run"
    assert "terminal_disposition_status" not in result
    webgpt = json.loads((issue_dir / "ask-webgpt-result.json").read_text())
    assert webgpt["status"] == "completed"
    assert webgpt["returncode"] == 0


def test_latest_pending_issue_dir_skips_dry_run_artifacts(tmp_path, monkeypatch):
    cycle = load_cycle_module()
    dry_run_issue_dir = tmp_path / "20260612T000000Z" / "issue-59"
    dry_run_issue_dir.mkdir(parents=True)
    (dry_run_issue_dir / "cycle-result.json").write_text(json.dumps({
        "status": "repair_subagent_started",
        "dry_run": True,
    }))
    pending_issue_dir = tmp_path / "20260612T000001Z" / "issue-60"
    pending_issue_dir.mkdir(parents=True)
    (pending_issue_dir / "cycle-result.json").write_text(json.dumps({
        "status": "repair_subagent_started",
        "dry_run": False,
    }))
    monkeypatch.setattr(cycle, "ARTIFACT_ROOT", tmp_path)

    assert cycle.latest_pending_issue_dir() == pending_issue_dir


def test_latest_pending_issue_dir_skips_github_dry_run_artifacts(tmp_path, monkeypatch):
    cycle = load_cycle_module()
    gh_dry_run_issue_dir = tmp_path / "20260612T000000Z" / "issue-61"
    gh_dry_run_issue_dir.mkdir(parents=True)
    (gh_dry_run_issue_dir / "cycle-result.json").write_text(json.dumps({
        "status": "repair_subagent_started",
        "created_github_dry_run": True,
    }))
    pending_issue_dir = tmp_path / "20260612T000001Z" / "issue-62"
    pending_issue_dir.mkdir(parents=True)
    (pending_issue_dir / "cycle-result.json").write_text(json.dumps({
        "status": "repair_subagent_started",
        "created_github_dry_run": False,
    }))
    monkeypatch.setattr(cycle, "ARTIFACT_ROOT", tmp_path)

    assert cycle.latest_pending_issue_dir() == pending_issue_dir


def test_main_can_continue_explicit_github_dry_run_artifact(tmp_path, monkeypatch, capsys):
    cycle = load_cycle_module()
    issue_dir = tmp_path / "20260612T000000Z" / "issue-64"
    issue_dir.mkdir(parents=True)
    (issue_dir / "cycle-result.json").write_text(json.dumps({
        "status": "repair_subagent_started",
        "created_github_dry_run": True,
        "target_skills": ["scheduler"],
        "subagent_dispatch": [],
        "subagent_specs": {},
    }))
    (issue_dir / "issue-snapshot.json").write_text(json.dumps({"number": 64, "url": "https://example.invalid/64"}))
    (issue_dir / "route-decision.json").write_text(json.dumps({
        "route": "ops_or_scheduler",
        "repair_agent": "devops",
        "verifier_agent": "project-or-harness-verifier",
        "review_agent": "code-reviewer",
    }))
    (issue_dir / "repair-response.json").write_text(json.dumps({"status": "running"}))
    monkeypatch.setattr(cycle.sys, "argv", [
        "skill_maintainer_cycle.py",
        "--continue-issue-dir",
        str(issue_dir),
        "--github-dry-run",
    ])

    assert cycle.main() == 0
    output = json.loads(capsys.readouterr().out)

    assert output["status"] == "repair_subagent_started"
    assert output["continuation_status"] == "waiting_for_repair_receipt"
    assert output["last_invocation_dry_run"] is False


def test_dry_run_continuation_does_not_poison_live_artifact(tmp_path):
    cycle = load_cycle_module()
    issue_dir = tmp_path / "20260612T000000Z" / "issue-63"
    issue_dir.mkdir(parents=True)
    (issue_dir / "cycle-result.json").write_text(json.dumps({
        "status": "repair_subagent_started",
        "dry_run": False,
        "created_dry_run": False,
        "target_skills": ["scheduler"],
        "subagent_dispatch": [],
        "subagent_specs": {},
    }))
    (issue_dir / "issue-snapshot.json").write_text(json.dumps({"number": 63, "url": "https://example.invalid/63"}))
    (issue_dir / "route-decision.json").write_text(json.dumps({
        "route": "ops_or_scheduler",
        "repair_agent": "devops",
        "verifier_agent": "project-or-harness-verifier",
        "review_agent": "code-reviewer",
    }))
    (issue_dir / "repair-response.json").write_text(json.dumps({"status": "running"}))

    result = cycle.continue_pending_run(issue_dir, dry_run=True)
    stored = json.loads((issue_dir / "cycle-result.json").read_text())

    assert result["last_invocation_dry_run"] is True
    assert stored["dry_run"] is False
    assert stored["created_dry_run"] is False


def test_continue_pending_run_revalidates_verifier_before_webgpt(tmp_path, monkeypatch):
    cycle = load_cycle_module()
    issue_dir = tmp_path / "20260612T000000Z" / "issue-56"
    issue_dir.mkdir(parents=True)
    (issue_dir / "cycle-result.json").write_text(json.dumps({
        "status": "review_subagent_started",
        "target_skills": ["scheduler"],
        "subagent_dispatch": [],
        "subagent_specs": {},
    }))
    (issue_dir / "issue-snapshot.json").write_text(json.dumps({"number": 56, "url": "https://example.invalid/56"}))
    (issue_dir / "route-decision.json").write_text(json.dumps({
        "route": "ops_or_scheduler",
        "repair_agent": "devops",
        "verifier_agent": "project-or-harness-verifier",
        "review_agent": "code-reviewer",
    }))
    (issue_dir / "repair-response.json").write_text(json.dumps({
        "status": "completed",
        "commands_run": ["repair command"],
        "evidence_summary": "repair evidence",
    }))
    (issue_dir / "review-response.json").write_text(json.dumps({
        "status": "completed",
        "decision": "pass",
        "commands_run": ["review command"],
        "evidence_summary": "review evidence",
        "blocking_findings": [],
    }))
    calls = []
    monkeypatch.setattr(cycle, "maybe_run_webgpt", lambda *args, **kwargs: calls.append(args))

    result = cycle.continue_pending_run(issue_dir, dry_run=False, github_dry_run=True, run_webgpt=True)

    assert calls == []
    assert result["continuation_status"] == "blocked_invalid_verifier_receipt:missing"
    assert result["receipt_gate_reason"] == "missing"


def test_existing_webgpt_result_does_not_bypass_missing_verifier(tmp_path, monkeypatch):
    cycle = load_cycle_module()
    issue_dir = tmp_path / "20260612T000000Z" / "issue-64"
    issue_dir.mkdir(parents=True)
    (issue_dir / "cycle-result.json").write_text(json.dumps({
        "status": "review_subagent_started",
        "target_skills": ["scheduler"],
        "subagent_dispatch": [],
        "subagent_specs": {},
    }))
    (issue_dir / "issue-snapshot.json").write_text(json.dumps({"number": 64, "url": "https://example.invalid/64"}))
    (issue_dir / "route-decision.json").write_text(json.dumps({
        "route": "ops_or_scheduler",
        "repair_agent": "devops",
        "verifier_agent": "project-or-harness-verifier",
        "review_agent": "code-reviewer",
    }))
    (issue_dir / "repair-response.json").write_text(json.dumps({
        "status": "completed",
        "commands_run": ["repair command"],
        "evidence_summary": "repair evidence",
    }))
    (issue_dir / "review-response.json").write_text(json.dumps({
        "status": "completed",
        "decision": "pass",
        "commands_run": ["review command"],
        "evidence_summary": "review evidence",
        "blocking_findings": [],
    }))
    (issue_dir / "ask-webgpt-result.json").write_text(json.dumps({"status": "completed"}))
    calls = []
    monkeypatch.setattr(cycle, "maybe_run_webgpt", lambda *args, **kwargs: calls.append(args))

    result = cycle.continue_pending_run(issue_dir, dry_run=False, github_dry_run=True, run_webgpt=True)

    assert calls == []
    assert result["continuation_status"] == "blocked_invalid_verifier_receipt:missing"
    assert result["closure_decision"] == "blocked_invalid_verifier_receipt:missing"
    assert result["receipt_gate_reason"] == "missing"


def test_existing_failed_webgpt_result_preserves_external_review_failure(tmp_path, monkeypatch):
    cycle = load_cycle_module()
    issue_dir = tmp_path / "20260612T000000Z" / "issue-67"
    issue_dir.mkdir(parents=True)
    (issue_dir / "cycle-result.json").write_text(json.dumps({
        "status": "review_subagent_started",
        "target_skills": ["scheduler"],
        "subagent_dispatch": [],
        "subagent_specs": {},
    }))
    (issue_dir / "issue-snapshot.json").write_text(json.dumps({"number": 67, "url": "https://example.invalid/67"}))
    (issue_dir / "route-decision.json").write_text(json.dumps({
        "route": "ops_or_scheduler",
        "repair_agent": "devops",
        "verifier_agent": "project-or-harness-verifier",
        "review_agent": "code-reviewer",
    }))
    (issue_dir / "repair-response.json").write_text(json.dumps({
        "status": "completed",
        "commands_run": ["repair command"],
        "evidence_summary": "repair evidence",
    }))
    (issue_dir / "verifier-response.json").write_text(json.dumps({
        "status": "completed",
        "decision": "pass",
        "commands_run": ["verify command"],
        "evidence_summary": "verifier evidence",
        "blocking_findings": [],
    }))
    (issue_dir / "review-response.json").write_text(json.dumps({
        "status": "completed",
        "decision": "pass",
        "commands_run": ["review command"],
        "evidence_summary": "review evidence",
        "blocking_findings": [],
    }))
    (issue_dir / "ask-webgpt-result.json").write_text(json.dumps({"status": "failed"}))
    calls = []
    monkeypatch.setattr(cycle, "maybe_run_webgpt", lambda *args, **kwargs: calls.append(args))
    mock_successful_github_terminal_disposition(monkeypatch, cycle)

    result = cycle.continue_pending_run(issue_dir, dry_run=False, github_dry_run=False, run_webgpt=True)

    assert calls == []
    assert result["status"] == "webgpt_review_failed"
    assert result["closure_decision"] == "blocked_webgpt_review_failed"
    assert result["observed_webgpt_status"] == "failed"
    assert result["terminal_disposition_status"] == "completed"
    assert [action["action"] for action in result["github_actions"]] == [
        "terminal_blocked_comment",
        "terminal_blocked_labels_release_lease",
    ]


def test_immediate_failed_webgpt_run_releases_lease_with_blocker(tmp_path, monkeypatch):
    cycle = load_cycle_module()
    issue_dir = tmp_path / "20260612T000000Z" / "issue-68"
    issue_dir.mkdir(parents=True)
    (issue_dir / "cycle-result.json").write_text(json.dumps({
        "status": "review_subagent_started",
        "target_skills": ["scheduler"],
        "subagent_dispatch": [],
        "subagent_specs": {},
    }))
    (issue_dir / "issue-snapshot.json").write_text(json.dumps({"number": 68, "url": "https://example.invalid/68"}))
    (issue_dir / "route-decision.json").write_text(json.dumps({
        "route": "ops_or_scheduler",
        "repair_agent": "devops",
        "verifier_agent": "project-or-harness-verifier",
        "review_agent": "code-reviewer",
    }))
    (issue_dir / "repair-response.json").write_text(json.dumps({
        "status": "completed",
        "commands_run": ["repair command"],
        "evidence_summary": "repair evidence",
    }))
    (issue_dir / "verifier-response.json").write_text(json.dumps({
        "status": "completed",
        "decision": "pass",
        "commands_run": ["verify command"],
        "evidence_summary": "verifier evidence",
        "blocking_findings": [],
    }))
    (issue_dir / "review-response.json").write_text(json.dumps({
        "status": "completed",
        "decision": "pass",
        "commands_run": ["review command"],
        "evidence_summary": "review evidence",
        "blocking_findings": [],
    }))
    (issue_dir / "review-bundle.md").write_text("# Review bundle\n")
    monkeypatch.setattr(
        cycle,
        "maybe_run_webgpt",
        lambda bundle, dry_run=False: {
            "cmd": ["bash", "skills/ask/run.sh", "webgpt-review", "--bundle", str(bundle)],
            "dry_run": dry_run,
            "returncode": 4,
            "stdout": "",
            "stderr": "missing sentinel",
        },
    )
    mock_successful_github_terminal_disposition(monkeypatch, cycle)

    result = cycle.continue_pending_run(issue_dir, dry_run=False, github_dry_run=False, run_webgpt=True)

    assert result["status"] == "webgpt_review_failed"
    assert result["closure_decision"] == "blocked_webgpt_review_failed"
    assert result["terminal_disposition_status"] == "completed"
    assert result["required_next_evidence"] == [
        "ask-webgpt-result.json from a successful real $ask runtime or explicit human retry decision"
    ]
    assert [action["action"] for action in result["github_actions"]] == [
        "terminal_blocked_comment",
        "terminal_blocked_labels_release_lease",
    ]
    webgpt = json.loads((issue_dir / "ask-webgpt-result.json").read_text())
    assert webgpt["status"] == "failed"
    assert webgpt["returncode"] == 4


def test_webgpt_terminal_disposition_failure_remains_retryable(tmp_path, monkeypatch):
    cycle = load_cycle_module()
    issue_dir = tmp_path / "20260612T000000Z" / "issue-69"
    issue_dir.mkdir(parents=True)
    (issue_dir / "cycle-result.json").write_text(json.dumps({
        "status": "review_subagent_started",
        "target_skills": ["scheduler"],
        "subagent_dispatch": [],
        "subagent_specs": {},
    }))
    (issue_dir / "issue-snapshot.json").write_text(json.dumps({"number": 69, "url": "https://example.invalid/69"}))
    (issue_dir / "route-decision.json").write_text(json.dumps({
        "route": "ops_or_scheduler",
        "repair_agent": "devops",
        "verifier_agent": "project-or-harness-verifier",
        "review_agent": "code-reviewer",
    }))
    (issue_dir / "repair-response.json").write_text(json.dumps({
        "status": "completed",
        "commands_run": ["repair command"],
        "evidence_summary": "repair evidence",
    }))
    (issue_dir / "verifier-response.json").write_text(json.dumps({
        "status": "completed",
        "decision": "pass",
        "commands_run": ["verify command"],
        "evidence_summary": "verifier evidence",
        "blocking_findings": [],
    }))
    (issue_dir / "review-response.json").write_text(json.dumps({
        "status": "completed",
        "decision": "pass",
        "commands_run": ["review command"],
        "evidence_summary": "review evidence",
        "blocking_findings": [],
    }))
    (issue_dir / "ask-webgpt-result.json").write_text(json.dumps({"status": "completed"}))
    monkeypatch.setattr(
        cycle,
        "gh_issue_comment",
        lambda issue_number, body_path, dry_run=False: {
            "cmd": ["gh", "issue", "comment", str(issue_number)],
            "dry_run": dry_run,
            "returncode": 1,
            "stdout": "",
            "stderr": "api unavailable",
        },
    )

    result = cycle.continue_pending_run(issue_dir, dry_run=False, github_dry_run=False, run_webgpt=True)
    stored = json.loads((issue_dir / "cycle-result.json").read_text())
    monkeypatch.setattr(cycle, "ARTIFACT_ROOT", tmp_path)

    assert result["terminal_disposition_status"] == "failed"
    assert result["terminal_disposition_failed_action"] == "terminal_blocked_comment"
    assert result["terminal_disposition_gate_validated"] is True
    assert stored["terminal_disposition_status"] == "failed"
    assert cycle.latest_pending_issue_dir() == issue_dir

    mock_successful_github_terminal_disposition(monkeypatch, cycle)
    retry_result = cycle.continue_pending_run(
        issue_dir,
        dry_run=False,
        github_dry_run=False,
        run_webgpt=True,
        require_webgpt=True,
    )

    assert retry_result["terminal_disposition_retry"] is True
    assert retry_result["terminal_disposition_gate_validated"] is True
    assert retry_result["terminal_disposition_status"] == "completed"
    assert [action["action"] for action in retry_result["github_actions"][-2:]] == [
        "terminal_blocked_comment",
        "terminal_blocked_labels_release_lease",
    ]


def test_webgpt_terminal_retry_revalidates_missing_gate_marker(tmp_path, monkeypatch):
    cycle = load_cycle_module()
    issue_dir = tmp_path / "20260612T000000Z" / "issue-72"
    issue_dir.mkdir(parents=True)
    (issue_dir / "cycle-result.json").write_text(json.dumps({
        "status": "webgpt_review_attempted",
        "target_skills": ["scheduler"],
        "terminal_disposition_status": "failed",
        "subagent_dispatch": [],
        "subagent_specs": {},
    }))
    (issue_dir / "issue-snapshot.json").write_text(json.dumps({"number": 72, "url": "https://example.invalid/72"}))
    (issue_dir / "route-decision.json").write_text(json.dumps({
        "route": "ops_or_scheduler",
        "repair_agent": "devops",
        "verifier_agent": "project-or-harness-verifier",
        "review_agent": "code-reviewer",
    }))
    (issue_dir / "repair-response.json").write_text(json.dumps({
        "status": "completed",
        "commands_run": ["repair command"],
        "evidence_summary": "repair evidence",
    }))
    (issue_dir / "review-response.json").write_text(json.dumps({
        "status": "completed",
        "decision": "pass",
        "commands_run": ["review command"],
        "evidence_summary": "review evidence",
        "blocking_findings": [],
    }))
    (issue_dir / "ask-webgpt-result.json").write_text(json.dumps({"status": "completed"}))
    mock_successful_github_terminal_disposition(monkeypatch, cycle)

    result = cycle.continue_pending_run(
        issue_dir,
        dry_run=False,
        github_dry_run=False,
        run_webgpt=True,
        require_webgpt=True,
    )

    assert result["terminal_disposition_retry"] is True
    assert result["terminal_disposition_gate_validated"] is False
    assert result["receipt_gate_reason"] == "verifier:missing"
    assert result["status"] == "blocked_invalid_webgpt_retry_gate_receipt:verifier:missing"
    assert result["terminal_disposition_status"] == "completed"


def test_webgpt_terminal_retry_handles_missing_disposition_status(tmp_path, monkeypatch):
    cycle = load_cycle_module()
    issue_dir = tmp_path / "20260612T000000Z" / "issue-73"
    issue_dir.mkdir(parents=True)
    (issue_dir / "cycle-result.json").write_text(json.dumps({
        "status": "webgpt_review_attempted",
        "target_skills": ["scheduler"],
        "terminal_disposition_gate_validated": True,
        "subagent_dispatch": [],
        "subagent_specs": {},
    }))
    (issue_dir / "issue-snapshot.json").write_text(json.dumps({"number": 73, "url": "https://example.invalid/73"}))
    (issue_dir / "route-decision.json").write_text(json.dumps({
        "route": "ops_or_scheduler",
        "repair_agent": "devops",
        "verifier_agent": "project-or-harness-verifier",
        "review_agent": "code-reviewer",
    }))
    (issue_dir / "ask-webgpt-result.json").write_text(json.dumps({"status": "completed"}))
    mock_successful_github_terminal_disposition(monkeypatch, cycle)

    result = cycle.continue_pending_run(
        issue_dir,
        dry_run=False,
        github_dry_run=False,
        run_webgpt=True,
        require_webgpt=True,
    )

    assert result["terminal_disposition_retry"] is True
    assert result["observed_webgpt_status"] == "completed"
    assert result["closure_decision"] == "blocked_waiting_for_finding_disposition_and_closure_wiring"
    assert result["terminal_disposition_status"] == "completed"
