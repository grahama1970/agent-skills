"""Run the /ask live E2E feature matrix and write an evidence report."""

from __future__ import annotations

from dotenv import find_dotenv, load_dotenv

load_dotenv(find_dotenv(usecwd=True), override=False)

import json
import os
import signal
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import typer


ASK_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_ROOT = ASK_ROOT / ".ask_artifacts" / "phase2-e2e"
SUBAGENT_RUNNER = ASK_ROOT.parent / "subagent-runner" / "run.sh"
app = typer.Typer(add_completion=False, help="Run live /ask E2E checks.")


@dataclass(frozen=True)
class Case:
    name: str
    command: list[str]
    timeout: int
    required: bool = True
    expect_zero: bool = True


@app.command()
def main(
    output_root: str = typer.Option(str(DEFAULT_OUTPUT_ROOT), "--output-root"),
    fast: bool = typer.Option(False, "--fast", help="Skip expensive live oracle/deep-review cases."),
    only: list[str] | None = typer.Option(
        None,
        "--only",
        help="Run cases whose names contain this substring. May be repeated.",
    ),
) -> None:
    args = SimpleNamespace(output_root=output_root, fast=fast, only=only or [])

    output_root = Path(args.output_root)
    run_dir = output_root / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_dir.mkdir(parents=True, exist_ok=True)

    cases = build_cases(run_dir=run_dir, fast=args.fast)
    if args.only:
        filters = [item.lower() for item in args.only]
        cases = [case for case in cases if any(filter_item in case.name.lower() for filter_item in filters)]
    results = [run_case(case, run_dir) for case in cases]
    summary = {
        "started_at": run_dir.name,
        "run_dir": str(run_dir),
        "total": len(results),
        "passed": sum(1 for result in results if result["passed"]),
        "failed": sum(1 for result in results if not result["passed"] and result["required"]),
        "non_required_failed": sum(1 for result in results if not result["passed"] and not result["required"]),
        "results": results,
    }
    (run_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    (run_dir / "PHASE_2_E2E_REPORT.md").write_text(render_report(summary), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    raise typer.Exit(1 if summary["failed"] else 0)


def build_cases(*, run_dir: Path, fast: bool) -> list[Case]:
    phase_scope = "ask"
    warm_model = os.environ.get("ASK_E2E_SCILLM_MODEL", "deepseek-ai/DeepSeek-V3.2-TEE")
    cases = [
        Case("help exposes deep review", ["./run.sh", "ask", "--help"], 30),
        Case("memory direct recall", ["../memory/run.sh", "recall", "--q", "project knowledge overview for ask", "--scope", phase_scope, "--k", "1"], 45),
        Case("scillm warm check", ["../scillm/run.sh", "warm-check", "--json"], 45),
        Case("subagent-runner help", ["../subagent-runner/run.sh", "--help"], 30),
        Case("ask memory json", ["./run.sh", "ask", "project knowledge overview for ask", "--ask-id", "e2e-ask-memory", "--json"], 60),
        Case("ask raw", ["./run.sh", "ask", "project knowledge overview for ask", "--raw"], 60),
        Case("ask status json", ["./run.sh", "status", "--json"], 60),
        Case("ask os static json", ["./run.sh", "os", "ask", "what does the memory skill do?", "--json"], 60),
        Case("ask os health memory", ["./run.sh", "os", "health", "is memory healthy?", "--json"], 90),
        Case("ask learn dry run", ["./run.sh", "learn", "ask live e2e smoke topic", "--youtube-only", "--max-videos", "0", "--dry-run", "--ask-id", "e2e-learn-dry-run"], 90),
        Case("ask os learn dry run", ["./run.sh", "os", "learn", "--depth", "quick", "--dry-run", "--ask-id", "e2e-os-learn-dry-run"], 90),
        Case("ask nightly dry run", ["./run.sh", "nightly", "--scope", phase_scope, "--dry-run", "--json"], 120),
    ]
    if fast:
        return cases
    cases.extend(
        [
            Case(
                "cybersecurity oracle",
                [
                    "./run.sh",
                    "ask",
                    "What is the state of space-based cybersecurity in 2026?",
                    "--scope",
                    "sparta",
                    "--oracle",
                    "--oracle-backend",
                    "scillm",
                    "--oracle-model",
                    warm_model,
                    "--oracle-timeout",
                    "240",
                    "--json",
                ],
                300,
            ),
            Case(
                "cybersecurity persona",
                [
                    "./run.sh",
                    "ask",
                    "Brandon",
                    "what",
                    "is",
                    "the",
                    "state",
                    "of",
                    "space-based",
                    "cybersecurity",
                    "in",
                    "2016?",
                    "--scope",
                    "sparta",
                    "--oracle-timeout",
                    "360",
                    "--oracle-idle-timeout",
                    "240",
                    "--oracle-heartbeat-interval",
                    "10",
                    "--json",
                ],
                420,
            ),
            Case(
                "cybersecurity roundtable",
                [
                    "./run.sh",
                    "ask",
                    "What is the state of cybersecurity in 2026?",
                    "--scope",
                    "sparta",
                    "--roundtable",
                    "--roundtable-personas",
                    "Brandon:failure_mode,Margaret:evidence_auditor,Jennifer:complexity_minimizer",
                    "--roundtable-rounds",
                    "1",
                    "--oracle-backend",
                    "subagent-runner",
                    "--oracle-timeout",
                    "420",
                    "--oracle-idle-timeout",
                    "240",
                    "--oracle-heartbeat-interval",
                    "10",
                    "--json",
                ],
                540,
            ),
            Case(
                "oracle scillm",
                [
                    "./run.sh",
                    "ask",
                    "project knowledge overview for ask",
                    "--oracle",
                    "--oracle-backend",
                    "scillm",
                    "--oracle-model",
                    warm_model,
                    "--oracle-timeout",
                    "180",
                    "--json",
                ],
                240,
            ),
            Case(
                "oracle subagent-runner",
                [
                    "./run.sh",
                    "ask",
                    "project knowledge overview for ask",
                    "--oracle",
                    "--oracle-backend",
                    "subagent-runner",
                    "--oracle-model",
                    "gpt-5.5",
                    "--oracle-timeout",
                    "300",
                    "--oracle-idle-timeout",
                    "240",
                    "--oracle-heartbeat-interval",
                    "10",
                    "--json",
                ],
                360,
            ),
            Case(
                "persona peer",
                [
                    "./run.sh",
                    "ask",
                    "Brandon",
                    "ask",
                    "Margaret",
                    "summarize",
                    "one",
                    "risk",
                    "in",
                    "ask",
                    "deep",
                    "review",
                    "--oracle-timeout",
                    "300",
                    "--oracle-idle-timeout",
                    "240",
                    "--oracle-heartbeat-interval",
                    "10",
                    "--json",
                ],
                360,
            ),
            Case(
                "roundtable",
                [
                    "./run.sh",
                    "ask",
                    "Should ask prefer queues or retries for long oracle tasks?",
                    "--roundtable",
                    "--roundtable-personas",
                    "Brandon:failure_mode,Margaret:evidence_auditor",
                    "--roundtable-rounds",
                    "1",
                    "--oracle-backend",
                    "subagent-runner",
                    "--oracle-timeout",
                    "300",
                    "--oracle-idle-timeout",
                    "240",
                    "--oracle-heartbeat-interval",
                    "10",
                    "--json",
                ],
                420,
            ),
            Case(
                "parallel review",
                [
                    "./run.sh",
                    "ask",
                    "Assess ask artifact behavior",
                    "--parallel-review",
                    "--parallel-reviewers",
                    "2",
                    "--parallel-review-focus",
                    "correctness,tests",
                    "--oracle-backend",
                    "subagent-runner",
                    "--oracle-timeout",
                    "300",
                    "--oracle-idle-timeout",
                    "240",
                    "--oracle-heartbeat-interval",
                    "10",
                    "--json",
                ],
                420,
            ),
            Case(
                "deep review",
                [
                    "./run.sh",
                    "ask",
                    "deep review ask deep review implementation",
                    "--deep-review",
                    "--deep-review-target",
                    "src/ask/deep_review.py",
                    "--deep-reviewers",
                    "2",
                    "--deep-review-focus",
                    "target,fail-closed,artifacts",
                    "--deep-review-output-root",
                    str(run_dir / "deep-review"),
                    "--ask-id",
                    "e2e-deep-review",
                    "--oracle-backend",
                    "subagent-runner",
                    "--oracle-timeout",
                    "420",
                    "--oracle-idle-timeout",
                    "240",
                    "--oracle-heartbeat-interval",
                    "10",
                    "--json",
                ],
                540,
            ),
        ]
    )
    return cases


def run_case(case: Case, run_dir: Path) -> dict:
    started = time.time()
    slug = case.name.replace(" ", "-")
    stdout_path = run_dir / f"{slug}.stdout"
    stderr_path = run_dir / f"{slug}.stderr"
    process = None
    env = {key: value for key, value in os.environ.items() if key != "VIRTUAL_ENV"}
    env["ASK_SUBAGENT_OUTPUT_DIR"] = str(run_dir / "subagents")
    env["ASK_RUN_OUTPUT_DIR"] = str(run_dir / "runtime-runs")
    try:
        process = subprocess.Popen(
            case.command,
            cwd=ASK_ROOT,
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,
        )
        stdout, stderr = process.communicate(timeout=case.timeout)
        returncode = process.returncode
        timed_out = False
    except subprocess.TimeoutExpired as exc:
        if process is not None:
            os.killpg(process.pid, signal.SIGTERM)
            try:
                stdout, stderr = process.communicate(timeout=10)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                stdout, stderr = process.communicate()
            cleanup_subagents(run_dir)
        else:
            stdout = exc.stdout if isinstance(exc.stdout, str) else ""
            stderr = exc.stderr if isinstance(exc.stderr, str) else ""
        returncode = -2
        timed_out = True
    stdout_path.write_text(stdout or "", encoding="utf-8")
    stderr_path.write_text(stderr or "", encoding="utf-8")
    passed = (returncode == 0) if case.expect_zero else (returncode != 0)
    validation_error = ""
    if passed:
        validation_error = validate_case_output(case, stdout)
        if validation_error:
            passed = False
    runtime_status_path = ""
    ask_id = command_ask_id(case.command)
    if passed and ask_id:
        runtime_error, runtime_status_path = validate_runtime_artifacts(case, run_dir, ask_id)
        if runtime_error:
            validation_error = runtime_error
            passed = False
    return {
        "name": case.name,
        "command": case.command,
        "required": case.required,
        "returncode": returncode,
        "passed": passed,
        "timed_out": timed_out,
        "duration_seconds": round(time.time() - started, 3),
        "stdout_path": str(stdout_path),
        "stderr_path": str(stderr_path),
        "runtime_status_path": runtime_status_path,
        "stdout_excerpt": excerpt(stdout),
        "stderr_excerpt": excerpt(stderr),
        "validation_error": validation_error,
    }


def command_ask_id(command: list[str]) -> str:
    for index, value in enumerate(command):
        if value == "--ask-id" and index + 1 < len(command):
            return command[index + 1]
    return ""


def validate_runtime_artifacts(case: Case, run_dir: Path, ask_id: str) -> tuple[str, str]:
    status_path = run_dir / "runtime-runs" / ask_id / f"{ask_id}.status.json"
    if not status_path.exists():
        return f"missing runtime status: {status_path}", str(status_path)
    try:
        status = json.loads(status_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return f"invalid runtime status JSON: {exc}", str(status_path)
    artifacts = status.get("artifacts") if isinstance(status.get("artifacts"), dict) else {}
    for required in ("request", "status", "events"):
        if not artifacts.get(required):
            return f"runtime status missing artifact path: {required}", str(status_path)
    if case.name == "deep review":
        for required in ("review_md", "review_json"):
            artifact = artifacts.get(required)
            if not artifact or not Path(artifact).exists():
                return f"runtime status missing deep-review artifact: {required}", str(status_path)
    return "", str(status_path)


def cleanup_subagents(run_dir: Path) -> None:
    subagent_root = run_dir / "subagents"
    if not subagent_root.exists() or not SUBAGENT_RUNNER.exists():
        return
    for status_path in subagent_root.glob("*/status.json"):
        try:
            state = json.loads(status_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if state.get("status") in {"completed", "failed", "cancelled", "timed_out", "stalled"}:
            continue
        subprocess.run(
            [str(SUBAGENT_RUNNER), "cancel", str(status_path.parent)],
            cwd=ASK_ROOT,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=15,
            check=False,
        )


def excerpt(value: str, limit: int = 1200) -> str:
    value = value.strip()
    if len(value) <= limit:
        return value
    return value[:limit] + "\n... [truncated]"


def validate_case_output(case: Case, stdout: str) -> str:
    try:
        data = json.loads(stdout)
    except json.JSONDecodeError as exc:
        if case.name in {
            "oracle scillm",
            "oracle subagent-runner",
            "persona peer",
            "roundtable",
            "parallel review",
            "deep review",
            "cybersecurity oracle",
            "cybersecurity persona",
            "cybersecurity roundtable",
        }:
            return f"stdout is not valid JSON: {exc}"
        return ""
    if isinstance(data, dict) and ("question" in data or "answer" in data):
        answer_error = validate_answer(data)
        if answer_error:
            return answer_error
        if case.name.startswith("cybersecurity"):
            domain_error = validate_cybersecurity_answer(case, data)
            if domain_error:
                return domain_error
    if case.name not in {
        "oracle scillm",
        "oracle subagent-runner",
        "persona peer",
        "roundtable",
        "parallel review",
        "deep review",
        "cybersecurity oracle",
        "cybersecurity persona",
        "cybersecurity roundtable",
    }:
        return ""
    oracle = data.get("oracle")
    if not isinstance(oracle, dict):
        return "missing oracle metadata"
    if oracle.get("error"):
        return f"oracle error: {oracle['error']}"
    if case.name in {"roundtable", "cybersecurity roundtable"} and "roundtable" not in oracle:
        return "missing roundtable metadata"
    if case.name == "parallel review" and "parallel_review" not in oracle:
        return "missing parallel_review metadata"
    if case.name == "deep review":
        deep_review = data.get("deep_review")
        if not isinstance(deep_review, dict):
            return "missing deep_review metadata"
        artifacts = deep_review.get("artifact_paths") if isinstance(deep_review.get("artifact_paths"), dict) else {}
        if not artifacts.get("review_md") or not artifacts.get("review_json"):
            return "missing deep review artifacts"
    return ""


def validate_answer(data: dict) -> str:
    answer = str(data.get("answer") or "").strip()
    if not answer:
        return "empty answer"
    shallow_failures = {
        "no answer could be synthesized.",
    }
    if answer.lower() in shallow_failures:
        return f"non-substantive answer: {answer}"
    lower_answer = answer.lower()
    refusal_markers = [
        "no information about",
        "does not support any claims",
        "context is entirely unrelated",
        "retrieved knowledge does not support",
        "based solely on the retrieved context, no information",
    ]
    for marker in refusal_markers:
        if marker in lower_answer:
            return f"non-answer/refusal marker found: {marker}"
    if len(answer) < 20:
        return f"answer too short: {answer!r}"
    if data.get("oracle", {}).get("error"):
        return f"oracle error: {data['oracle']['error']}"
    return ""


def validate_cybersecurity_answer(case: Case, data: dict) -> str:
    answer = str(data.get("answer") or "").lower()
    required_terms = ["cybersecurity", "risk", "threat"]
    if not any(term in answer for term in required_terms):
        return "cybersecurity answer does not discuss cybersecurity/risk/threat"
    if "space-based" in " ".join(case.command).lower() and not any(
        term in answer for term in ["space", "satellite", "gnss", "ground station", "satcom"]
    ):
        return "space cybersecurity answer lacks space/satellite/GNSS grounding"
    oracle = data.get("oracle") if isinstance(data.get("oracle"), dict) else {}
    if case.name == "cybersecurity persona" and oracle.get("persona") != "Brandon":
        return "cybersecurity persona case did not run as Brandon"
    if case.name == "cybersecurity roundtable":
        roundtable = oracle.get("roundtable") if isinstance(oracle.get("roundtable"), dict) else {}
        personas = roundtable.get("personas", "")
        for name in ["Brandon", "Margaret", "Jennifer"]:
            if name not in personas:
                return f"cybersecurity roundtable missing persona {name}"
    return ""


def render_report(summary: dict) -> str:
    lines = [
        "# ask Phase 2 Live E2E Report",
        "",
        f"- Run directory: `{summary['run_dir']}`",
        f"- Total: `{summary['total']}`",
        f"- Passed: `{summary['passed']}`",
        f"- Required failed: `{summary['failed']}`",
        f"- Non-required failed: `{summary['non_required_failed']}`",
        "",
        "| Case | Status | Return | Seconds | Evidence | Runtime |",
        "| --- | --- | ---: | ---: | --- | --- |",
    ]
    for result in summary["results"]:
        status = "PASS" if result["passed"] else "FAIL"
        lines.append(
            f"| {result['name']} | {status} | {result['returncode']} | "
            f"{result['duration_seconds']} | `{Path(result['stdout_path']).name}` / `{Path(result['stderr_path']).name}` | "
            f"{_runtime_cell(result)} |"
        )
    lines.extend(["", "## Failures", ""])
    failures = [result for result in summary["results"] if not result["passed"]]
    if not failures:
        lines.append("No failures.")
    for result in failures:
        lines.extend(
            [
                f"### {result['name']}",
                "",
                f"- Command: `{' '.join(result['command'])}`",
                f"- Return code: `{result['returncode']}`",
                f"- Timed out: `{result['timed_out']}`",
                f"- Validation error: `{result.get('validation_error') or ''}`",
                f"- Stdout: `{result['stdout_path']}`",
                f"- Stderr: `{result['stderr_path']}`",
                "",
                "Stderr excerpt:",
                "",
                "```text",
                result["stderr_excerpt"],
                "```",
                "",
            ]
        )
    return "\n".join(lines) + "\n"


def _runtime_cell(result: dict) -> str:
    runtime_path = result.get("runtime_status_path") or ""
    if not runtime_path:
        return ""
    return f"`{Path(runtime_path).name}`"


if __name__ == "__main__":
    app()
