"""CLI behavior tests for safe defaults and explicit live-effect gates."""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from captcha_skill.cli import app

SKILL_ROOT = Path(__file__).resolve().parents[1]
FIXTURES = SKILL_ROOT / "fixtures"
RUNNER = CliRunner()


def test_no_args_is_safe_json_status() -> None:
    result = RUNNER.invoke(app, [])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["schema_version"] == "captcha.status.v1"
    assert payload["status"] in {"PASS", "NOT_ESTABLISHED"}


def test_valid_authorization_preflight_passes() -> None:
    result = RUNNER.invoke(
        app,
        [
            "authorization-preflight",
            "--manifest",
            str(FIXTURES / "authorization-valid-local.json"),
            "--action",
            "plan",
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["status"] == "PASS"
    assert payload["schema_version"] == "captcha.authorization_receipt.v1"


def test_public_target_preflight_fails_closed() -> None:
    result = RUNNER.invoke(
        app,
        [
            "authorization-preflight",
            "--manifest",
            str(FIXTURES / "authorization-invalid-public.json"),
            "--action",
            "evaluate",
            "--json",
        ],
    )

    assert result.exit_code == 2
    payload = json.loads(result.stdout)
    assert payload["status"] == "BLOCKED"
    assert payload["failure_code"] == "target_not_loopback"


def test_evaluate_requires_explicit_execute() -> None:
    result = RUNNER.invoke(
        app,
        [
            "evaluate",
            "--manifest",
            str(FIXTURES / "authorization-valid-local.json"),
            "--json",
        ],
    )

    assert result.exit_code == 2
    payload = json.loads(result.stdout)
    assert payload["failure_code"] == "execution_not_confirmed"


def test_ask_dag_command_writes_typed_skill_run(tmp_path: Path) -> None:
    out = tmp_path / "captcha.ask-dag.json"
    result = RUNNER.invoke(
        app,
        [
            "ask-dag",
            "--manifest",
            str(FIXTURES / "authorization-valid-local.json"),
            "--out",
            str(out),
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    dag = json.loads(out.read_text())
    assert dag["schema_version"] == "ask.dag.v1"
    assert dag["nodes"][0]["type"] == "skill.run"
    assert dag["nodes"][0]["input"]["skill"] == "captcha"
    assert "--execute" in dag["nodes"][0]["input"]["args"]


def test_plan_missing_runtime_is_nonzero_and_truthful(tmp_path: Path) -> None:
    out = tmp_path / "plan.json"
    result = RUNNER.invoke(
        app,
        [
            "plan",
            "--manifest",
            str(FIXTURES / "authorization-valid-local.json"),
            "--recap-root",
            "/definitely/missing/ReCAP-Agent",
            "--recap-python",
            "/definitely/missing/ReCAP-Agent/.venv/bin/python",
            "--out",
            str(out),
            "--json",
        ],
    )

    assert result.exit_code == 2
    payload = json.loads(result.stdout)
    assert payload["readiness"] == "NEEDS_ATTENTION"
    assert payload["blockers"]
    assert payload["seam_validation"] is None
