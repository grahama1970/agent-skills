#!/usr/bin/env python3
"""Stress sanity for /ask Tau DAG routing without default provider spend."""

from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path
from typing import Any

import typer


ASK_DIR = Path(__file__).resolve().parents[1]
app = typer.Typer(add_completion=False, help="Run bounded /ask Tau DAG stress sanity checks.")


@app.command()
def main(
    output_root: Path | None = typer.Option(None, "--output-root", help="Artifact root; defaults to a temp dir."),
    keep: bool = typer.Option(False, "--keep", help="Keep temporary artifact root."),
    json_output: bool = typer.Option(False, "--json", help="Emit JSON summary."),
) -> None:
    temp_dir_ctx: tempfile.TemporaryDirectory[str] | None = None
    if output_root is None:
        temp_dir_ctx = tempfile.TemporaryDirectory(prefix="ask-tau-dag-stress-")
        root = Path(temp_dir_ctx.name)
    else:
        root = output_root.expanduser().resolve()
        root.mkdir(parents=True, exist_ok=True)

    summary = _run(root)
    if json_output:
        typer.echo(json.dumps(summary, indent=2, sort_keys=True))
    else:
        typer.echo(f"status: {summary['status']}")
        typer.echo(f"output_root: {summary['output_root']}")
        for case in summary["cases"]:
            typer.echo(f"{case['id']}: {'PASS' if case['ok'] else 'FAIL'}")

    if temp_dir_ctx is not None and not keep:
        temp_dir_ctx.cleanup()
    raise typer.Exit(0 if summary["ok"] else 1)


def _run(output_root: Path) -> dict[str, Any]:
    cases = [
        _case_compile_ready(output_root),
        _case_incomplete_interview(output_root),
        _case_local_fixture_execution(output_root),
        _case_provider_execution_requires_opt_in(output_root),
        _case_webgpt_routes_to_interview(output_root),
    ]
    ok = all(case["ok"] for case in cases)
    return {
        "schema": "ask.tau_dag_stress_sanity.v1",
        "status": "PASS" if ok else "FAIL",
        "ok": ok,
        "mocked": False,
        "live": True,
        "provider_live": False,
        "what_was_exercised": [
            "/ask run.sh tau-dag compile-ready path",
            "/ask run.sh tau-dag incomplete request interview path",
            "real Tau CLI local-fixture DAG execution path",
            "provider execution fail-closed opt-in path",
            "WebGPT native-skill-route fail-closed path",
        ],
        "what_remains_unverified": [
            "Provider/model calls because --allow-provider-calls is not used.",
            "Semantic quality of solver/reviewer output.",
            "Browser screenshot proof of the React Flow viewer.",
        ],
        "output_root": str(output_root),
        "cases": cases,
    }


def _case_compile_ready(output_root: Path) -> dict[str, Any]:
    return _run_case(
        "compile-ready",
        [
            "tau-dag",
            "ask 2 gpt 5.6 xhigh subagents to solve X concurrently, then claude fable reviews both solutions",
            "--repo",
            "local/tau",
            "--target",
            "stress-compile",
            "--criterion",
            "correctness",
            "--criterion",
            "maintainability",
            "--run-output-root",
            str(output_root / "compile-ready"),
            "--json",
        ],
        expect_returncode=0,
        checks=[
            ("status_ready", lambda payload: (payload.get("bundle") or {}).get("status") == "READY"),
            ("dag_exists", lambda payload: Path(str((payload.get("bundle") or {}).get("dag_path"))).is_file()),
            (
                "final_dag_before_execution",
                lambda payload: (payload.get("bundle") or {}).get("final_dag_emitted_before_execution")
                is True,
            ),
            (
                "gpt_56_xhigh_route_metadata",
                lambda payload: _has_model_policy(
                    payload,
                    requested_model="gpt-5.6-xhigh",
                    model="gpt-5.5",
                    reasoning_effort="high",
                    requested_reasoning_effort="xhigh",
                ),
            ),
            (
                "claude_fable_route_metadata",
                lambda payload: _has_model_policy(
                    payload,
                    requested_model="claude-fable",
                    model="claude-fable-5",
                    auth="scillm_claude_code_credentials",
                ),
            ),
        ],
    )


def _case_incomplete_interview(output_root: Path) -> dict[str, Any]:
    return _run_case(
        "incomplete-interview",
        [
            "tau-dag",
            "solve X",
            "--run-output-root",
            str(output_root / "incomplete-interview"),
            "--json",
        ],
        expect_returncode=2,
        checks=[
            ("needs_interview", lambda payload: (payload.get("bundle") or {}).get("status") == "NEEDS_INTERVIEW"),
            ("interview_packet_exists", lambda payload: Path(str((payload.get("bundle") or {}).get("run_dir")), "interview-required.json").is_file()),
        ],
    )


def _case_local_fixture_execution(output_root: Path) -> dict[str, Any]:
    return _run_case(
        "local-fixture-execution",
        [
            "tau-dag",
            "ask 2 gpt 5.6 xhigh subagents to solve X concurrently, then claude fable reviews both solutions",
            "--repo",
            "local/tau",
            "--target",
            "stress-local-fixture",
            "--criterion",
            "correctness",
            "--criterion",
            "maintainability",
            "--run-output-root",
            str(output_root / "local-fixture-execution"),
            "--execute",
            "--local-fixture",
            "--poll-timeout-seconds",
            "60",
            "--json",
        ],
        expect_returncode=0,
        checks=[
            ("execution_pass", lambda payload: (payload.get("execution") or {}).get("status") == "PASS"),
            ("tau_receipt_exists", lambda payload: Path(str((payload.get("execution") or {}).get("receipt_path"))).is_file()),
            (
                "parallel_solver_dispatches_observed",
                lambda payload: (((payload.get("execution") or {}).get("receipt") or {}).get("max_observed_concurrency") or 0) >= 2,
            ),
        ],
    )


def _case_provider_execution_requires_opt_in(output_root: Path) -> dict[str, Any]:
    return _run_case(
        "provider-execution-requires-opt-in",
        [
            "tau-dag",
            "solve X",
            "--repo",
            "local/tau",
            "--target",
            "stress-provider-block",
            "--solver-model",
            "gpt-5.6-xhigh",
            "--reviewer-model",
            "claude-fable",
            "--criterion",
            "correctness",
            "--run-output-root",
            str(output_root / "provider-execution-requires-opt-in"),
            "--execute",
            "--json",
        ],
        expect_returncode=3,
        checks=[
            (
                "blocked_for_provider_opt_in",
                lambda payload: (payload.get("execution") or {}).get("blocked_reason") == "provider_execution_requires_allow_provider_calls",
            ),
            ("provider_live_false", lambda payload: payload.get("provider_live") is False),
        ],
    )


def _case_webgpt_routes_to_interview(output_root: Path) -> dict[str, Any]:
    return _run_case(
        "webgpt-routes-to-interview",
        [
            "tau-dag",
            "ask webgpt to review X after a solver finishes",
            "--repo",
            "local/tau",
            "--target",
            "stress-webgpt",
            "--solver-model",
            "gpt-5.6-xhigh",
            "--reviewer-model",
            "webgpt",
            "--criterion",
            "correctness",
            "--run-output-root",
            str(output_root / "webgpt-routes-to-interview"),
            "--json",
        ],
        expect_returncode=2,
        checks=[
            ("needs_interview", lambda payload: (payload.get("bundle") or {}).get("status") == "NEEDS_INTERVIEW"),
            ("model_routes_missing_field", lambda payload: "model_routes" in ((payload.get("bundle") or {}).get("missing_fields") or [])),
        ],
    )


def _run_case(
    case_id: str,
    args: list[str],
    *,
    expect_returncode: int,
    checks: list[tuple[str, Any]],
) -> dict[str, Any]:
    command = [str(ASK_DIR / "run.sh"), *args]
    completed = subprocess.run(
        command,
        cwd=ASK_DIR,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        timeout=180,
    )
    payload = _json_or_error(completed.stdout)
    check_results = [
        {"name": "returncode", "ok": completed.returncode == expect_returncode, "evidence": {"actual": completed.returncode, "expected": expect_returncode}}
    ]
    for name, predicate in checks:
        try:
            ok = bool(predicate(payload))
        except Exception as exc:  # pragma: no cover - diagnostics only
            ok = False
            payload.setdefault("predicate_errors", {})[name] = str(exc)
        check_results.append({"name": name, "ok": ok, "evidence": {}})
    ok = all(item["ok"] for item in check_results)
    return {
        "id": case_id,
        "ok": ok,
        "mocked": False,
        "live": True,
        "provider_live": False,
        "command": command,
        "returncode": completed.returncode,
        "checks": check_results,
        "stdout_tail": completed.stdout[-4000:],
        "stderr_tail": completed.stderr[-4000:],
    }


def _json_or_error(text: str) -> dict[str, Any]:
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        return {"parse_error": str(exc), "raw_stdout": text[-4000:]}
    return payload if isinstance(payload, dict) else {"parse_error": "stdout JSON root was not an object"}


def _has_model_policy(payload: dict[str, Any], **expected: Any) -> bool:
    dag = (payload.get("bundle") or {}).get("dag")
    if not isinstance(dag, dict):
        return False
    nodes = dag.get("nodes")
    if not isinstance(nodes, list):
        return False
    for node in nodes:
        if not isinstance(node, dict):
            continue
        policy = node.get("model_policy")
        if isinstance(policy, dict) and all(
            policy.get(key) == value for key, value in expected.items()
        ):
            return True
    return False


if __name__ == "__main__":
    app()
