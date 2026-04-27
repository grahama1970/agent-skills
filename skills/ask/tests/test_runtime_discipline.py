from pathlib import Path

from typer.testing import CliRunner

from ask.chain_specs import get_chain_spec, load_chain_specs, validate_chain_spec
from ask.doctor import app as doctor_app, run_doctor
from ask.reviewer_specs import get_reviewer_spec, select_reviewer_angles
from ask.run_state import (
    build_context_policy,
    complete_run,
    create_run,
    get_run,
    list_runs,
    review_and_fix_policy,
)
from ask.status import app as status_app


def test_run_state_creates_standard_artifacts(tmp_path: Path):
    run = create_run("parallel-review", question="review this", run_id="test-run", root=tmp_path)

    assert run["run_id"] == "test-run"
    run_dir = tmp_path / "parallel-review" / "test-run"
    assert (run_dir / "request.json").exists()
    assert (run_dir / "status.json").exists()
    assert (run_dir / "events.jsonl").exists()

    complete_run("test-run", "parallel-review", artifact_paths=["synthesis.md"], root=tmp_path)
    loaded = get_run("test-run", root=tmp_path)
    assert loaded is not None
    assert loaded["status"]["state"] == "completed"
    assert list_runs(root=tmp_path)[0]["run_id"] == "test-run"


def test_context_policy_and_review_and_fix_worktree_guard():
    policy = build_context_policy(
        "deep-review",
        review_context="fresh",
        inherit_memory="summary",
        inherit_skills="selected",
        inherit_project_context="no",
    )

    assert policy["mode"] == "deep-review"
    assert policy["memory_as_evidence"] is False

    blocked = review_and_fix_policy("src/ask/ask.py")
    assert blocked["allowed"] is False
    assert blocked["needs_attention"] == "needs_repo_access"

    allowed = review_and_fix_policy("src/ask/ask.py", worktree="/tmp/ask-fix")
    assert allowed["allowed"] is True
    assert allowed["write_policy"] == "isolated_worktree_only"


def test_reviewer_frontmatter_specs_load_and_drive_dynamic_angles():
    evidence = get_reviewer_spec("evidence")
    assert evidence["name"] == "evidence-auditor"
    assert evidence["write_policy"] == "artifacts_only"

    selected = select_reviewer_angles(
        "Run E2E tests and review timeout failure modes for memory-backed security answers",
        count=5,
    )
    names = [spec["name"] for spec in selected]
    assert "evidence-auditor" in names
    assert "failure-mode" in names
    assert "test-proof" in names
    assert "security-data-risk" in names


def test_saved_review_chains_validate():
    chains = load_chain_specs()
    assert "deep-review" in chains
    assert "parallel-review" in chains
    assert validate_chain_spec(chains["deep-review"]) == []
    assert get_chain_spec("parallel-review")["stages"][0]["name"] == "select-reviewers"


def test_doctor_reports_runtime_objects():
    report = run_doctor()
    check_names = {check["name"] for check in report["checks"]}

    assert "artifact-root" in check_names
    assert "reviewer-specs" in check_names
    assert "chain-specs" in check_names
    assert report["status"] in {"pass", "warn", "fail"}


def test_doctor_cli_json():
    runner = CliRunner()
    result = runner.invoke(doctor_app, ["--json"])

    assert result.exit_code in {0, 1}
    assert '"reviewer-specs"' in result.output
    assert '"chain-specs"' in result.output


def test_status_cli_lists_runtime_runs(tmp_path: Path, monkeypatch):
    from ask import run_state

    monkeypatch.setattr(run_state, "DEFAULT_ARTIFACT_ROOT", tmp_path)
    create_run("ask", question="status smoke", run_id="status-run", root=tmp_path)

    runner = CliRunner()
    result = runner.invoke(status_app, ["--runs", "--json"])

    assert result.exit_code == 0
    assert "status-run" in result.output
