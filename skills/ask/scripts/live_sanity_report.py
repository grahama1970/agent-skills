"""Run opt-in live /ask sanity checks and write an HTML bug report.

This runner intentionally calls real composed skill paths. It is not a mocked
unit-test harness. It is designed to find integration bugs before humans hit
them in normal `$ask` usage.
"""

from __future__ import annotations

from dotenv import find_dotenv, load_dotenv

load_dotenv(find_dotenv(usecwd=True), override=False)

import argparse
import html
import json
import os
import signal
import subprocess
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ASK_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_ROOT = ASK_ROOT / ".ask_artifacts" / "live-sanity"
TERMINAL_STATES = {"answered", "completed", "needs_attention", "failed", "error"}
METADATA_ONLY_MODES = {"chains", "config", "doctor", "status"}
BAD_ANSWER_MARKERS = [
    "no answer could be synthesized",
    "based solely on the retrieved context, no information",
    "retrieved knowledge does not support",
    "context is entirely unrelated",
    "i don't have enough information",
    "i cannot answer",
]


@dataclass(frozen=True)
class Case:
    name: str
    question: str
    command: list[str]
    timeout_seconds: int
    mode: str
    feature: str
    case_type: str
    required: bool = True
    expected_state: set[str] = field(default_factory=lambda: {"answered", "completed"})
    semantic_terms: tuple[str, ...] = ()
    require_json: bool = True
    require_runtime: bool = True
    expect_needs_attention: bool = False
    expect_clarification: bool = False
    readiness_contribution: str = "supports_feature_readiness"


def main() -> int:
    parser = argparse.ArgumentParser(description="Run real-world /ask sanity E2E checks and render an HTML report.")
    parser.add_argument("--output-root", default=str(DEFAULT_OUTPUT_ROOT), help="Directory for live sanity reports.")
    parser.add_argument("--allow-live", action="store_true", help="Actually execute live checks.")
    parser.add_argument("--plan-only", action="store_true", help="Write the report without executing checks.")
    parser.add_argument("--profile", choices=("smoke", "core-live", "release"), default="release", help="Readiness profile to evaluate.")
    parser.add_argument("--include-expensive", action="store_true", help="Include fresh discovery and SPARTA evidence-case checks.")
    parser.add_argument("--only", action="append", default=[], help="Run cases whose name contains this substring.")
    parser.add_argument("--timeout-scale", type=float, default=1.0, help="Scale every case timeout by this multiplier.")
    args = parser.parse_args()

    if not args.allow_live and not args.plan_only and os.environ.get("ASK_LIVE_SANITY_E2E") != "1":
        raise SystemExit(
            "Refusing to run live checks without --allow-live, --plan-only, or ASK_LIVE_SANITY_E2E=1. "
            "These checks call real composed skills and may be slow or cost-bearing."
        )

    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_dir = Path(args.output_root).resolve() / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    include_expensive = args.include_expensive or args.profile == "release"
    cases = build_cases(run_dir=run_dir, include_expensive=include_expensive, profile=args.profile)
    all_cases = list(cases)
    total_case_count = len(all_cases)
    omitted_cases: list[Case] = []
    if args.only:
        filters = tuple(item.lower() for item in args.only)
        cases = [case for case in all_cases if any(filter_item in case.name.lower() for filter_item in filters)]
        omitted_cases = [case for case in all_cases if case not in cases]
    selected_case_count = len(cases)

    results = []
    for case in cases:
        if args.plan_only:
            results.append(plan_result(case, run_dir))
            continue
        results.append(run_case(case, run_dir, timeout_scale=args.timeout_scale))
    if omitted_cases:
        for case in omitted_cases:
            result = plan_result(case, run_dir)
            result["status"] = "skipped"
            result["execution_status"] = "skipped"
            result["assertion_status"] = "not_run"
            result["feature_readiness"] = "not_established"
            result["coverage_gaps"] = ["omitted by --only filtered debug run"]
            result["response"] = "Not executed in this filtered run; release readiness is not established."
            result["response_summary"] = "Not executed in this filtered run."
            results.append(result)

    summary = summarize(
        run_dir,
        results,
        plan_only=args.plan_only,
        profile=args.profile,
        include_expensive=include_expensive,
        filters=args.only,
        total_case_count=total_case_count,
        selected_case_count=selected_case_count,
    )
    (run_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    (run_dir / "report.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    (run_dir / "index.html").write_text(render_html(summary), encoding="utf-8")
    (run_dir / "report.md").write_text(render_markdown(summary), encoding="utf-8")

    print(json.dumps({"run_dir": str(run_dir), "html": str(run_dir / "index.html"), **summary["totals"]}, indent=2))
    return 1 if summary["totals"]["failed_required"] else 0


def build_cases(*, run_dir: Path, include_expensive: bool, profile: str) -> list[Case]:
    runtime_root = run_dir / "runtime"
    target = "README.md"
    cases = [
        Case(
            name="release-config-preflight",
            question="Is /ask configured for release readiness without prompting in continuous integration (CI)?",
            command=["./run.sh", "config", "doctor", "--profile", "release", "--json"],
            timeout_seconds=60,
            mode="config",
            feature="release-config",
            case_type="deployment-preflight",
            require_runtime=False,
            expected_state=set(),
            semantic_terms=("config", "release"),
            readiness_contribution="blocks_release_when_missing",
        ),
        Case(
            name="doctor-live-dependencies",
            question="Are composed runtime dependencies available?",
            command=["./run.sh", "doctor", "--live", "--json"],
            timeout_seconds=120,
            mode="doctor",
            feature="doctor-preflight",
            case_type="degraded-dependency",
            require_runtime=False,
            semantic_terms=("memory", "scillm", "artifact"),
        ),
        Case(
            name="memory-backed-question",
            question="What do we know about idempotent token refresh under concurrent auth retries?",
            command=[
                "./run.sh",
                "ask",
                "What do we know about idempotent token refresh under concurrent auth retries?",
                "--ask-id",
                "live-memory",
                "--run-output-root",
                str(runtime_root),
                "--json",
            ],
            timeout_seconds=120,
            mode="ask",
            feature="memory-backed-ask",
            case_type="semantic-quality",
            semantic_terms=("retry", "token", "auth"),
        ),
        Case(
            name="runtime-status-lookup",
            question="Can status inspect the previous live-memory run artifacts?",
            command=[
                "./run.sh",
                "status",
                "--run",
                "live-memory",
                "--run-output-root",
                str(runtime_root),
                "--tail-events",
                "10",
                "--json",
            ],
            timeout_seconds=120,
            mode="status",
            feature="runtime-status",
            case_type="artifact-contract",
            require_runtime=False,
            semantic_terms=("live-memory",),
        ),
        Case(
            name="chains-validate-real",
            question="Do saved review workflow specs validate in the current checkout?",
            command=["./run.sh", "chains", "validate", "--json"],
            timeout_seconds=120,
            mode="chains",
            feature="review-chains",
            case_type="docs-contract",
            require_runtime=False,
            semantic_terms=("deep-review", "parallel-review"),
        ),
        Case(
            name="missing-persona-clarification",
            question=(
                "Have the tester and maintainer roundtable the cache invalidation migration risk for cross-region "
                "writes, and clarify instead of silently inventing missing personas."
            ),
            command=[
                "./run.sh",
                "ask",
                "Have the tester and maintainer roundtable the cache invalidation migration risk for cross-region writes.",
                "--ask-id",
                "live-missing-persona",
                "--run-output-root",
                str(runtime_root),
                "--json",
            ],
            timeout_seconds=240,
            mode="missing-persona-clarification",
            feature="persona-clarification",
            case_type="negative-control",
            expected_state={"answered", "completed", "needs_attention"},
            semantic_terms=("tester", "maintainer", "persona", "interview"),
            expect_needs_attention=True,
            expect_clarification=True,
        ),
        Case(
            name="persona-oracle",
            question="Ask the reliability architect whether the queue fallback fails closed when Redis quorum is lost.",
            command=[
                "./run.sh",
                "ask",
                "Critique whether the queue fallback fails closed when Redis quorum is lost.",
                "--oracle",
                "--oracle-backend",
                "subagent-runner",
                "--oracle-persona",
                "ReliabilityArchitect",
                "--oracle-timeout",
                "360",
                "--oracle-idle-timeout",
                "180",
                "--ask-id",
                "live-persona",
                "--run-output-root",
                str(runtime_root),
                "--json",
            ],
            timeout_seconds=420,
            mode="oracle",
            feature="persona-oracle",
            case_type="positive-control",
            semantic_terms=("queue", "redis", "quorum", "fail"),
        ),
        Case(
            name="argue-real-scillm",
            question="Argue whether replayed webhook delivery handling is safe to ship.",
            command=[
                "./run.sh",
                "ask",
                "argue whether replayed webhook delivery handling is safe to ship",
                "--argue",
                "--ask-id",
                "live-argue",
                "--run-output-root",
                str(runtime_root),
                "--json",
            ],
            timeout_seconds=360,
            mode="argue",
            feature="argue",
            case_type="negative-control",
            expected_state={"answered", "completed", "needs_attention"},
            semantic_terms=("webhook", "replay", "ship"),
            expect_needs_attention=True,
            readiness_contribution="safe_failure_only",
        ),
        Case(
            name="argue-evidence-backed-success",
            question="Argue a tiny evidence-backed release-config claim and require the verifier to pass.",
            command=[
                "./run.sh",
                "ask",
                (
                    "argue whether the ask release config doctor should fail closed when required release config is missing. "
                    "Evidence: the ask release config contract states that if required release config is missing, "
                    "the config doctor must return needs_attention and must not claim release readiness."
                ),
                "--argue",
                "--ask-id",
                "live-argue-success",
                "--run-output-root",
                str(runtime_root),
                "--json",
            ],
            timeout_seconds=360,
            mode="argue",
            feature="argue",
            case_type="positive-control",
            expected_state={"answered", "completed"},
            semantic_terms=("config", "needs_attention", "release"),
        ),
        Case(
            name="parallel-review-real-target",
            question="Run independent reviewers on the README target and require evidence-bearing output.",
            command=[
                "./run.sh",
                "ask",
                "Review this README for README/code alignment risks",
                "--parallel-review",
                "--parallel-reviewers",
                "2",
                "--parallel-review-focus",
                "correctness,tests",
                "--review-target",
                target,
                "--ask-id",
                "live-parallel-review",
                "--run-output-root",
                str(runtime_root),
                "--json",
            ],
            timeout_seconds=420,
            mode="parallel-review",
            feature="parallel-review",
            case_type="positive-control",
            semantic_terms=("README", "alignment"),
        ),
        Case(
            name="deep-review-real-target",
            question="Deep review a real file and verify review artifacts exist.",
            command=[
                "./run.sh",
                "ask",
                "deep review this implementation",
                "--deep-review",
                "--deep-review-target",
                target,
                "--deep-reviewers",
                "2",
                "--deep-review-focus",
                "evidence,claims,readability",
                "--ask-id",
                "live-deep-review",
                "--run-output-root",
                str(runtime_root),
                "--json",
            ],
            timeout_seconds=540,
            mode="deep-review",
            feature="deep-review",
            case_type="artifact-contract",
            semantic_terms=("README", "evidence"),
        ),
        Case(
            name="os-health-real",
            question="Is memory healthy?",
            command=[
                "./run.sh",
                "os",
                "health",
                "is memory healthy?",
                "--ask-id",
                "live-os-health",
                "--run-output-root",
                str(runtime_root),
                "--json",
            ],
            timeout_seconds=180,
            mode="os-health",
            feature="os-health",
            case_type="semantic-quality",
            semantic_terms=("memory", "health"),
        ),
    ]
    expensive = [
        Case(
            name="learn-real-throwaway-scope",
            question="Can learn ingest a small real topic into an isolated live-sanity scope?",
            command=[
                "./run.sh",
                "learn",
                "architecture of this repository",
                "--scope",
                "ask-live-sanity",
                "--depth",
                "quick",
                "--max-books",
                "0",
                "--max-videos",
                "0",
                "--ask-id",
                "live-learn",
                "--run-output-root",
                str(runtime_root),
            ],
            timeout_seconds=600,
            mode="learn",
            feature="learn",
            case_type="positive-control",
            require_json=False,
            semantic_terms=("architecture",),
        ),
        Case(
            name="freshness-dogpile-real",
            question="Find current evidence about Python packaging state in 2026.",
            command=[
                "./run.sh",
                "ask",
                "What is the state of Python packaging in 2026?",
                "--dogpile",
                "force",
                "--oracle",
                "--ask-id",
                "live-dogpile",
                "--run-output-root",
                str(runtime_root),
                "--json",
            ],
            timeout_seconds=600,
            mode="dogpile",
            feature="dogpile-freshness",
            case_type="freshness",
            semantic_terms=("python", "packaging", "2026"),
        ),
        Case(
            name="sparta-evidence-preflight-real",
            question="Route a SPARTA/NIST control question through evidence-case preflight.",
            command=[
                "./run.sh",
                "ask",
                "How does NIST AC-3 relate to SPARTA countermeasure CM0001?",
                "--ask-id",
                "live-sparta",
                "--run-output-root",
                str(runtime_root),
                "--json",
            ],
            timeout_seconds=360,
            mode="sparta",
            feature="sparta-preflight",
            case_type="positive-control",
            expected_state={"answered", "completed", "needs_attention"},
            semantic_terms=("AC-3", "CM0001", "SPARTA"),
        ),
    ]
    if include_expensive:
        cases.extend(expensive)
    else:
        cases.extend(
            plan_skip(case, "requires --include-expensive because it can call fresh discovery or evidence-case routes")
            for case in expensive
        )
    return cases


def plan_skip(case: Case, reason: str) -> Case:
    return Case(
        name=case.name,
        question=f"{case.question} [SKIPPED BY DEFAULT: {reason}]",
        command=case.command,
        timeout_seconds=case.timeout_seconds,
        mode=case.mode,
        feature=case.feature,
        case_type="coverage-gap",
        required=False,
        expected_state=case.expected_state,
        semantic_terms=case.semantic_terms,
        require_json=case.require_json,
        require_runtime=case.require_runtime,
        expect_needs_attention=case.expect_needs_attention,
        expect_clarification=case.expect_clarification,
        readiness_contribution="no_support",
    )


def plan_result(case: Case, run_dir: Path) -> dict[str, Any]:
    return {
        "name": case.name,
        "question": case.question,
        "mode": case.mode,
        "feature": case.feature,
        "case_type": case.case_type,
        "command": case.command,
        "skills_used": infer_skills_used(case, None),
        "response": "Plan only: command not executed.",
        "response_summary": "Plan only: command not executed.",
        "required": case.required,
        "status": "planned" if case.required else "skipped",
        "execution_status": "planned" if case.required else "skipped",
        "assertion_status": "not_run",
        "feature_readiness": "not_established",
        "readiness_contribution": case.readiness_contribution,
        "passed": False,
        "bug_findings": [],
        "coverage_gaps": ["plan-only: command not executed"],
        "duration_seconds": 0,
        "returncode": None,
        "timed_out": False,
        "stdout_path": "",
        "stderr_path": "",
        "runtime_status_path": "",
        "artifact_paths": [],
        "report_dir": str(run_dir),
    }


def run_case(case: Case, run_dir: Path, *, timeout_scale: float) -> dict[str, Any]:
    if not case.required and "SKIPPED BY DEFAULT" in case.question:
        result = plan_result(case, run_dir)
        gap = case.question.split("SKIPPED BY DEFAULT:", 1)[-1].rstrip("]")
        result["bug_findings"] = []
        result["coverage_gaps"] = [gap]
        return result

    started = time.time()
    slug = slugify(case.name)
    stdout_path = run_dir / f"{slug}.stdout.txt"
    stderr_path = run_dir / f"{slug}.stderr.txt"
    env = {key: value for key, value in os.environ.items() if key != "VIRTUAL_ENV"}
    env["ASK_RUN_OUTPUT_DIR"] = str(run_dir / "runtime")
    env.setdefault("ASK_SUBAGENT_OUTPUT_DIR", str(run_dir / "subagents"))
    timed_out = False
    timeout_reason = ""
    returncode = -999
    stdout_bytes = bytearray()
    stderr_bytes = bytearray()
    process: subprocess.Popen[bytes] | None = None
    timeout = max(1, int(case.timeout_seconds * timeout_scale))
    idle_timeout = liveness_idle_timeout(case, timeout)
    last_liveness_at = started
    liveness_source = "process-start"
    event_count = 0
    last_event = ""
    event_offset = 0
    events_path = runtime_events_path(case, run_dir)
    try:
        process = subprocess.Popen(
            case.command,
            cwd=ASK_ROOT,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,
        )
        for stream in (process.stdout, process.stderr):
            if stream is not None:
                os.set_blocking(stream.fileno(), False)

        while True:
            stdout_chunk = drain_pipe(process.stdout)
            stderr_chunk = drain_pipe(process.stderr)
            if stdout_chunk:
                stdout_bytes.extend(stdout_chunk)
                last_liveness_at = time.time()
                liveness_source = "stdout"
            if stderr_chunk:
                stderr_bytes.extend(stderr_chunk)
                last_liveness_at = time.time()
                liveness_source = "stderr"

            event_delta, event_offset, event_name = tail_runtime_events(events_path, event_offset)
            if event_delta:
                event_count += event_delta
                last_event = event_name
                last_liveness_at = time.time()
                liveness_source = "events.jsonl"

            returncode = process.poll()
            if returncode is not None:
                stdout_bytes.extend(drain_pipe(process.stdout))
                stderr_bytes.extend(drain_pipe(process.stderr))
                break

            now = time.time()
            if now - started > timeout:
                timed_out = True
                timeout_reason = f"hard wall cap after {timeout}s"
                terminate_process(process)
                stdout_bytes.extend(drain_pipe(process.stdout))
                stderr_bytes.extend(drain_pipe(process.stderr))
                returncode = -2
                break
            time.sleep(0.2)
    finally:
        if process is not None and process.poll() is None:
            terminate_process(process)

    stdout = stdout_bytes.decode("utf-8", errors="replace")
    stderr = stderr_bytes.decode("utf-8", errors="replace")
    if timed_out and timeout_reason:
        stderr = (stderr + "\n" if stderr else "") + f"[live-sanity] {timeout_reason}\n"

    stdout_path.write_text(stdout or "", encoding="utf-8")
    stderr_path.write_text(stderr or "", encoding="utf-8")
    bug_findings, parsed = analyze_output(case, stdout, stderr, returncode, timed_out)
    runtime_status_path, artifact_paths = inspect_runtime(case, run_dir, bug_findings)
    if case.require_runtime and command_value(case.command, "--ask-id") and event_count <= 0:
        bug_findings.append("runtime liveness was not observed through events.jsonl")
    passed = not bug_findings
    return {
        "name": case.name,
        "question": case.question,
        "mode": case.mode,
        "feature": case.feature,
        "case_type": case.case_type,
        "command": case.command,
        "skills_used": infer_skills_used(case, parsed),
        "response": extract_actual_response(case, parsed, stdout),
        "response_summary": summarize_response(case, parsed, stdout),
        "required": case.required,
        "status": "pass" if passed else "fail",
        "execution_status": "pass" if returncode == 0 or (case.expect_needs_attention and returncode == 2) else "fail",
        "assertion_status": "pass" if passed else "fail",
        "feature_readiness": feature_readiness_for_result(case, passed),
        "readiness_contribution": case.readiness_contribution,
        "passed": passed,
        "bug_findings": bug_findings,
        "coverage_gaps": [],
        "duration_seconds": round(time.time() - started, 3),
        "returncode": returncode,
        "timed_out": timed_out,
        "timeout_reason": timeout_reason,
        "liveness_source": liveness_source,
        "liveness_idle_timeout_seconds": idle_timeout,
        "seconds_since_last_liveness": round(time.time() - last_liveness_at, 3),
        "runtime_event_count": event_count,
        "last_runtime_event": last_event,
        "stdout_path": str(stdout_path),
        "stderr_path": str(stderr_path),
        "stdout_excerpt": excerpt(stdout),
        "stderr_excerpt": excerpt(stderr),
        "json_keys": sorted(parsed.keys()) if isinstance(parsed, dict) else [],
        "runtime_status_path": runtime_status_path,
        "artifact_paths": artifact_paths,
        "report_dir": str(run_dir),
    }


def drain_pipe(pipe: Any) -> bytes:
    if pipe is None:
        return b""
    chunks: list[bytes] = []
    while True:
        try:
            chunk = os.read(pipe.fileno(), 65536)
        except BlockingIOError:
            break
        except OSError:
            break
        if not chunk:
            break
        chunks.append(chunk)
    return b"".join(chunks)


def terminate_process(process: subprocess.Popen[bytes]) -> None:
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    deadline = time.time() + 10
    while process.poll() is None and time.time() < deadline:
        time.sleep(0.1)
    if process.poll() is None:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait(timeout=10)


def runtime_events_path(case: Case, run_dir: Path) -> Path:
    ask_id = command_value(case.command, "--ask-id")
    if not ask_id or not case.require_runtime:
        return Path()
    return run_dir / "runtime" / ask_id / f"{ask_id}.events.jsonl"


def liveness_idle_timeout(case: Case, hard_timeout: int) -> int:
    explicit = command_value(case.command, "--oracle-idle-timeout")
    if explicit.isdigit():
        return max(15, int(explicit))
    if case.require_runtime and command_value(case.command, "--ask-id"):
        return 180
    return min(60, hard_timeout)


def tail_runtime_events(events_path: Path, offset: int) -> tuple[int, int, str]:
    if not events_path or not events_path.exists():
        return 0, offset, ""
    try:
        size = events_path.stat().st_size
        if size < offset:
            offset = 0
        if size == offset:
            return 0, offset, ""
        with events_path.open("rb") as handle:
            handle.seek(offset)
            data = handle.read()
            offset = handle.tell()
    except OSError:
        return 0, offset, ""
    count = 0
    last_event = ""
    for raw_line in data.splitlines():
        if not raw_line.strip():
            continue
        count += 1
        try:
            event = json.loads(raw_line)
        except json.JSONDecodeError:
            continue
        last_event = str(event.get("event") or event.get("phase") or "")
    return count, offset, last_event


def analyze_output(
    case: Case,
    stdout: str,
    stderr: str,
    returncode: int,
    timed_out: bool,
) -> tuple[list[str], Any]:
    bugs: list[str] = []
    parsed: Any = None
    if timed_out:
        bugs.append(f"timed out after {case.timeout_seconds}s")
    if returncode != 0 and not (case.expect_needs_attention and returncode == 2):
        bugs.append(f"non-zero exit code: {returncode}")
    if "Traceback (most recent call last)" in stderr:
        bugs.append("stderr contains Python traceback")
    if "Traceback (most recent call last)" in stdout:
        bugs.append("stdout contains Python traceback")
    if case.require_json:
        try:
            parsed = json.loads(stdout)
        except json.JSONDecodeError as exc:
            bugs.append(f"stdout is not valid JSON: {exc}")
            return bugs, parsed
    if isinstance(parsed, dict):
        bugs.extend(validate_semantics(case, parsed))
    return bugs, parsed


def summarize_response(case: Case, parsed: Any, stdout: str) -> str:
    if not isinstance(parsed, dict):
        return excerpt(stdout, limit=500) or "No structured response captured."
    if isinstance(parsed.get("needs_attention"), dict):
        attention = parsed["needs_attention"]
        reason = attention.get("reason") or "needs_attention"
        hint = attention.get("resume_hint") or ""
        missing = attention.get("missing_personas")
        parts = [f"needs_attention: {reason}"]
        if missing:
            parts.append(f"missing={', '.join(str(item) for item in missing)}")
        if hint:
            parts.append(str(hint))
        return excerpt(" — ".join(parts), limit=500)
    for key in ("answer", "summary"):
        value = parsed.get(key)
        if isinstance(value, str) and value.strip():
            return excerpt(value, limit=500)
    if isinstance(parsed.get("deep_review"), dict):
        review = parsed["deep_review"]
        verdict = review.get("verdict") or review.get("final_verdict") or ""
        summary = review.get("summary") or review.get("executive_summary") or ""
        return excerpt(" ".join(str(item) for item in (verdict, summary) if item), limit=500)
    if isinstance(parsed.get("oracle"), dict):
        oracle = parsed["oracle"]
        for key in ("answer", "summary", "response"):
            value = oracle.get(key)
            if isinstance(value, str) and value.strip():
                return excerpt(value, limit=500)
    if isinstance(parsed.get("items"), list):
        return f"Returned {len(parsed['items'])} memory item(s)."
    return f"Structured JavaScript Object Notation (JSON) response with keys: {', '.join(sorted(parsed.keys()))}"


def extract_actual_response(case: Case, parsed: Any, stdout: str) -> str:
    if not isinstance(parsed, dict):
        return excerpt(stdout, limit=1500) or "No response captured."
    for key in ("answer", "summary"):
        value = parsed.get(key)
        if isinstance(value, str) and value.strip():
            return excerpt(value, limit=1500)
    if isinstance(parsed.get("needs_attention"), dict):
        return excerpt(json.dumps(parsed["needs_attention"], indent=2, sort_keys=True, default=str), limit=1500)
    if isinstance(parsed.get("deep_review"), dict):
        return excerpt(json.dumps(parsed["deep_review"], indent=2, sort_keys=True, default=str), limit=1500)
    if isinstance(parsed.get("oracle"), dict):
        oracle = parsed["oracle"]
        for key in ("answer", "summary", "response"):
            value = oracle.get(key)
            if isinstance(value, str) and value.strip():
                return excerpt(value, limit=1500)
        return excerpt(json.dumps(oracle, indent=2, sort_keys=True, default=str), limit=1500)
    return excerpt(json.dumps(parsed, indent=2, sort_keys=True, default=str), limit=1500)


def infer_skills_used(case: Case, parsed: Any) -> list[str]:
    command = case.command
    skills: list[str] = []

    def add(*values: str) -> None:
        for value in values:
            if value and value not in skills:
                skills.append(value)

    add("/ask")
    if "ask" in command:
        add("/memory")
    if "learn" in command:
        add("/memory", "/dogpile", "/extractor")
    if "doctor" in command:
        add("/memory", "/scillm", "/subagent-runner")
    if "status" in command:
        add("runtime-artifacts")
    if "chains" in command:
        add("review-chain-specs")
    if "os" in command:
        add("/memory", "monitor/ops skill")
    if "--dogpile" in command:
        add("/dogpile")
    if "--oracle" in command:
        backend = command_value(command, "--oracle-backend")
        if backend == "subagent-runner":
            add("/subagent-runner")
        elif backend == "scillm":
            add("/scillm")
        else:
            add("/scillm", "/subagent-runner")
    if "--argue" in command:
        add("/scillm")
    if "--parallel-review" in command:
        add("/scillm", "reviewer specs")
    if "--deep-review" in command:
        add("/subagent-runner", "/scillm", "deep-review verifier")
    if "--roundtable" in command:
        add("/memory", "/subagent-runner", "reviewer specs")
    if case.expect_clarification or case.mode == "missing-persona-clarification":
        add("/memory clarify", "/interview", "/create-persona")
    if case.mode == "sparta":
        add("/extract-entities", "/create-evidence-case")
    if isinstance(parsed, dict) and isinstance(parsed.get("needs_attention"), dict):
        for skill in parsed["needs_attention"].get("suggested_skills", []):
            add(str(skill))
    return skills


def feature_readiness_for_result(case: Case, passed: bool) -> str:
    if not passed:
        return "not_ready" if case.required else "not_established"
    if case.readiness_contribution == "safe_failure_only":
        return "partial"
    if case.mode in {"deep-review", "parallel-review"}:
        return "ready_with_conditions"
    return "ready"


def validate_semantics(case: Case, data: dict[str, Any]) -> list[str]:
    bugs: list[str] = []
    answer = str(data.get("answer") or data.get("summary") or "")
    serialized = json.dumps(data, sort_keys=True, default=str).lower()
    if case.mode not in METADATA_ONLY_MODES and not case.expect_needs_attention:
        if not answer and not data.get("deep_review") and not data.get("oracle") and not data.get("items"):
            bugs.append("no answer, oracle, deep_review, or items payload found")
        if answer:
            lowered = answer.lower()
            for marker in BAD_ANSWER_MARKERS:
                if marker in lowered and (lowered.strip().startswith(marker) or len(answer.strip()) < 1000):
                    bugs.append(f"answer contains non-answer marker: {marker}")
            if len(answer.strip()) < 40:
                bugs.append("answer is suspiciously short")
    if case.semantic_terms:
        missing_terms = [term for term in case.semantic_terms if term.lower() not in serialized]
        if len(missing_terms) == len(case.semantic_terms):
            bugs.append(f"output lacks all expected semantic terms: {', '.join(case.semantic_terms)}")
    if case.expect_clarification:
        clarify_markers = ("clarify", "clarification", "needs_attention", "ambiguous", "missing persona", "persona not found")
        creation_markers = ("interview", "create-persona", "create persona", "create these personas")
        if not any(marker in serialized for marker in clarify_markers):
            bugs.append("missing-persona prompt did not ask for clarification or surface needs_attention")
        if not any(marker in serialized for marker in creation_markers):
            bugs.append("missing-persona prompt did not offer persona creation via interview/create-persona")
        for expected in ("tester", "maintainer"):
            if expected not in serialized:
                bugs.append(f"missing-persona clarification omitted requested persona: {expected}")
    if isinstance(data.get("oracle"), dict):
        oracle = data["oracle"]
        if oracle.get("error"):
            bugs.append(f"oracle error: {oracle['error']}")
    if isinstance(data.get("needs_attention"), dict) and not case.expect_needs_attention:
        bugs.append(f"unexpected needs_attention: {data['needs_attention']}")
    return bugs


def inspect_runtime(case: Case, run_dir: Path, bugs: list[str]) -> tuple[str, list[str]]:
    ask_id = command_value(case.command, "--ask-id")
    if not ask_id or not case.require_runtime:
        return "", []
    status_path = run_dir / "runtime" / ask_id / f"{ask_id}.status.json"
    if not status_path.exists():
        bugs.append(f"missing runtime status artifact: {status_path}")
        return str(status_path), []
    try:
        status = json.loads(status_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        bugs.append(f"runtime status is invalid JSON: {exc}")
        return str(status_path), []
    state = str(status.get("state") or "")
    if state and state not in TERMINAL_STATES:
        bugs.append(f"runtime status is not terminal: {state}")
    if case.expected_state and state not in case.expected_state:
        bugs.append(f"runtime state {state!r} not in expected states: {sorted(case.expected_state)}")
    artifact_paths = collect_artifact_paths(status)
    for artifact in artifact_paths:
        if not Path(artifact).exists():
            bugs.append(f"registered artifact is missing: {artifact}")
    events_path = run_dir / "runtime" / ask_id / f"{ask_id}.events.jsonl"
    if not events_path.exists():
        bugs.append(f"missing runtime events artifact: {events_path}")
    return str(status_path), artifact_paths


def collect_artifact_paths(status: dict[str, Any]) -> list[str]:
    artifacts = status.get("artifacts")
    if not isinstance(artifacts, dict):
        return []
    paths: list[str] = []
    for value in artifacts.values():
        if isinstance(value, str):
            paths.append(value)
        elif isinstance(value, list):
            paths.extend(item for item in value if isinstance(item, str))
        elif isinstance(value, dict):
            paths.extend(item for item in value.values() if isinstance(item, str))
    return paths


def command_value(command: list[str], flag: str) -> str:
    try:
        index = command.index(flag)
    except ValueError:
        return ""
    if index + 1 >= len(command):
        return ""
    return command[index + 1]


def summarize(
    run_dir: Path,
    results: list[dict[str, Any]],
    *,
    plan_only: bool,
    profile: str,
    include_expensive: bool,
    filters: list[str],
    total_case_count: int,
    selected_case_count: int,
) -> dict[str, Any]:
    failed_required = sum(1 for result in results if result["required"] and result["status"] == "fail")
    skipped = sum(1 for result in results if result["status"] in {"planned", "skipped"})
    coverage_gaps = [gap for result in results for gap in result.get("coverage_gaps", [])]
    filtered = bool(filters)
    if filtered and len(results) < total_case_count:
        coverage_gaps.append(f"filtered run: {total_case_count - len(results)} release case(s) omitted by --only")
    features = build_feature_matrix(results)
    overall = overall_readiness(profile, failed_required, coverage_gaps, features, plan_only, filtered)
    return {
        "schema": "ask.live_sanity_report.v2",
        "title": "ask Release Readiness Report",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "run_dir": str(run_dir),
        "profile": profile,
        "filters": filters,
        "filtered": filtered,
        "selected_cases": selected_case_count,
        "total_profile_cases": total_case_count,
        "overall_readiness": overall,
        "release_readiness": overall if profile == "release" and not filtered else "not_established",
        "include_expensive": include_expensive,
        "plan_only": plan_only,
        "totals": {
            "total": len(results),
            "passed": sum(1 for result in results if result["status"] == "pass"),
            "failed_required": failed_required,
            "failed_optional": sum(1 for result in results if not result["required"] and result["status"] == "fail"),
            "skipped_or_planned": skipped,
        },
        "features": features,
        "findings": build_findings(results, coverage_gaps),
        "results": results,
    }


def build_feature_matrix(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    features: dict[str, dict[str, Any]] = {}
    for result in results:
        feature = result.get("feature") or result.get("mode") or "unknown"
        row = features.setdefault(
            feature,
            {
                "id": feature,
                "readiness": "not_established",
                "required_cases": 0,
                "passed_cases": 0,
                "failed_cases": 0,
                "coverage_gaps": [],
                "notes": [],
                "readiness_contributions": [],
            },
        )
        if result.get("required"):
            row["required_cases"] += 1
        if result.get("status") == "pass":
            row["passed_cases"] += 1
        if result.get("status") == "fail":
            row["failed_cases"] += 1
        row["coverage_gaps"].extend(result.get("coverage_gaps", []))
        if result.get("status") == "pass":
            row["readiness_contributions"].append(result.get("readiness_contribution") or "")

    for row in features.values():
        safe_failure_only = "safe_failure_only" in row["readiness_contributions"]
        has_positive_support = any(
            contribution not in {"", "safe_failure_only", "no_support"}
            for contribution in row["readiness_contributions"]
        )
        if safe_failure_only and not has_positive_support:
            row["notes"].append("Only safe-failure behavior is proven.")
        elif safe_failure_only and has_positive_support:
            row["notes"].append("Includes safe-failure and positive readiness evidence.")
        if row["failed_cases"]:
            row["readiness"] = "not_ready"
        elif row["coverage_gaps"] or row["required_cases"] == 0:
            row["readiness"] = "not_established"
        elif row["passed_cases"] == 0:
            row["readiness"] = "not_established"
        elif row["notes"] and not has_positive_support:
            row["readiness"] = "partial"
        elif row["passed_cases"] >= row["required_cases"]:
            row["readiness"] = "ready"
        else:
            row["readiness"] = "questionable"
    return sorted(features.values(), key=lambda item: item["id"])


def overall_readiness(
    profile: str,
    failed_required: int,
    coverage_gaps: list[str],
    features: list[dict[str, Any]],
    plan_only: bool,
    filtered: bool,
) -> str:
    if plan_only:
        return "not_established"
    if filtered:
        return "not_established"
    if failed_required:
        return "not_ready"
    if profile == "release" and coverage_gaps:
        return "not_established"
    if any(feature["readiness"] in {"partial", "questionable"} for feature in features):
        return "usable_with_gaps"
    return "ready"


def build_findings(results: list[dict[str, Any]], coverage_gaps: list[str]) -> dict[str, list[dict[str, Any]]]:
    blockers: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    gaps: list[dict[str, Any]] = []
    for result in results:
        for finding in result.get("bug_findings", []):
            item = {
                "case_id": result["name"],
                "feature": result.get("feature"),
                "message": finding,
                "reproduce": " ".join(result.get("command", [])),
            }
            if result.get("required"):
                blockers.append(item)
            else:
                warnings.append(item)
        for gap in result.get("coverage_gaps", []):
            gaps.append(
                {
                    "case_id": result["name"],
                    "feature": result.get("feature"),
                    "message": gap,
                    "blocks_release_profile": True,
                    "blocks_core_live_profile": False,
                }
            )
    existing_messages = {item.get("message") for item in gaps}
    for gap in coverage_gaps:
        if gap not in existing_messages:
            gaps.append({"message": gap, "blocks_release_profile": True})
    return {"blockers": blockers, "warnings": warnings, "coverage_gaps": gaps}


def render_html(summary: dict[str, Any]) -> str:
    feature_rows = "\n".join(render_feature_row(feature) for feature in summary["features"])
    rows = "\n".join(render_row(result) for result in summary["results"])
    findings = render_findings(summary["findings"])
    outstanding = render_outstanding_summary(summary)
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{escape(summary['title'])}</title>
  <style>
    :root {{ color-scheme: dark; --bg:#090d14; --panel:#111827; --panel-2:#172033; --text:#f8fafc; --muted:#cbd5e1; --line:#334155; --pass:#86efac; --fail:#fca5a5; --skip:#facc15; --focus:#93c5fd; --chip:#23324a; --info:#93c5fd; }}
    * {{ box-sizing:border-box; }}
    body {{ margin:0; background:linear-gradient(180deg,#090d14,#111827); color:var(--text); font:16px/1.55 system-ui,-apple-system,Segoe UI,sans-serif; }}
    main {{ max-width:1440px; margin:32px auto; padding:28px; background:var(--panel); border:1px solid var(--line); border-radius:16px; box-shadow:0 24px 80px rgba(0,0,0,.35); }}
    h1 {{ margin:0 0 8px; font-size:32px; }}
    h2 {{ margin-top:32px; border-bottom:1px solid var(--line); padding-bottom:6px; }}
    .meta {{ color:var(--muted); }}
    .totals {{ display:flex; flex-wrap:wrap; gap:12px; margin:20px 0; }}
    .card {{ border:1px solid var(--line); border-radius:12px; padding:12px 14px; min-width:150px; background:var(--panel-2); }}
    .card strong {{ display:block; font-size:22px; }}
    table {{ width:100%; border-collapse:collapse; table-layout:fixed; }}
    th, td {{ border:1px solid var(--line); padding:10px 12px; vertical-align:top; overflow-wrap:anywhere; }}
    th {{ background:#0f172a; text-align:left; position:sticky; top:0; z-index:1; }}
    code, pre {{ font-family:ui-monospace,SFMono-Regular,Consolas,monospace; }}
    code {{ background:#020617; color:#e2e8f0; padding:2px 5px; border-radius:4px; }}
    pre {{ white-space:pre-wrap; background:#020617; color:#f8fafc; padding:12px; border-radius:10px; overflow:auto; }}
    .pass {{ color:var(--pass); font-weight:700; }}
    .fail {{ color:var(--fail); font-weight:700; }}
    .ready {{ color:var(--pass); font-weight:700; }}
    .not_ready {{ color:var(--fail); font-weight:700; }}
    .partial, .questionable, .not_established {{ color:var(--skip); font-weight:700; }}
    .planned, .skipped {{ color:var(--skip); font-weight:700; }}
    .finding {{ border-left:5px solid var(--fail); background:#2a1518; padding:12px 14px; border-radius:8px; margin:14px 0; }}
    .response {{ max-width:420px; white-space:pre-wrap; }}
    .skills {{ min-width:220px; }}
    .chip {{ display:inline-block; margin:0 6px 6px 0; padding:4px 8px; min-height:28px; border:1px solid var(--line); border-radius:999px; background:var(--chip); color:var(--text); }}
    .status-label {{ display:block; color:var(--muted); font-size:16px; font-weight:500; }}
    .case-grid {{ display:grid; gap:14px; }}
    .case-card {{ border:1px solid var(--line); border-radius:14px; background:#0f172a; padding:16px; }}
    .case-card h3 {{ margin:0 0 8px; font-size:20px; }}
    .case-meta {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(160px,1fr)); gap:10px; margin:12px 0; }}
    .case-meta div, .case-section {{ border:1px solid #25334d; border-radius:10px; background:#111827; padding:10px; }}
    .case-section {{ margin-top:10px; }}
    .case-section strong, .case-meta span {{ display:block; color:var(--muted); font-size:13px; margin-bottom:4px; }}
    .artifact-links a {{ display:inline-block; margin:0 8px 8px 0; }}
    details.case-section summary {{ cursor:pointer; color:var(--focus); font-weight:700; }}
    a:focus, code:focus, .chip:focus {{ outline:3px solid var(--focus); outline-offset:2px; }}
  </style>
</head>
<body>
<main data-qid="ask-live-sanity-report">
  <h1>{escape(summary['title'])}</h1>
  <p class="meta" data-qid="audit-trail">Created {escape(summary['created_at'])} · profile <code>{escape(summary['profile'])}</code> · report dir <code>{escape(summary['run_dir'])}</code></p>
  <div class="totals" data-qid="summary-metrics">
    {render_total('Overall Readiness', summary['overall_readiness'])}
    {render_total('Release Readiness', summary['release_readiness'])}
    {render_total('Total', summary['totals']['total'])}
    {render_total('Passed', summary['totals']['passed'])}
    {render_total('Required Failed', summary['totals']['failed_required'])}
    {render_total('Optional Failed', summary['totals']['failed_optional'])}
    {render_total('Skipped/Planned', summary['totals']['skipped_or_planned'])}
  </div>
  <h2>State At A Glance</h2>
  {outstanding}
  <h2>Feature Readiness Matrix</h2>
  <table data-qid="feature-readiness-table" aria-label="Feature readiness matrix">
    <thead><tr><th>Feature</th><th>Readiness</th><th>Required</th><th>Passed</th><th>Gaps</th><th>Notes</th></tr></thead>
    <tbody>{feature_rows}</tbody>
  </table>
  <h2>Findings</h2>
  {findings}
  <h2>Case Results</h2>
  <div class="case-grid" data-qid="questions-results-table" aria-label="Live sanity questions, actual responses, skills, and results">
    {rows}
  </div>
</main>
</body>
</html>
"""


def render_total(label: str, value: Any) -> str:
    return f'<div class="card"><span>{escape(label)}</span><strong>{escape(value)}</strong></div>'


def render_outstanding_summary(summary: dict[str, Any]) -> str:
    not_ready = [feature for feature in summary["features"] if feature["readiness"] == "not_ready"]
    not_established = [feature for feature in summary["features"] if feature["readiness"] == "not_established"]
    partial = [feature for feature in summary["features"] if feature["readiness"] in {"partial", "questionable"}]
    ready = [feature for feature in summary["features"] if feature["readiness"] == "ready"]
    coverage_count = len(summary["findings"].get("coverage_gaps", []))
    blocker_count = len(summary["findings"].get("blockers", []))
    warning_count = len(summary["findings"].get("warnings", []))
    omitted = max(0, int(summary.get("total_profile_cases", 0)) - int(summary.get("selected_cases", 0)))
    items = [
        f"Release readiness: {summary['release_readiness']}.",
        f"Complete: {len(ready)} feature(s) have executed evidence.",
        f"Broken: {len(not_ready)} feature(s) have failing required checks.",
        f"Incomplete or missing evidence: {len(not_established)} feature(s) are not established by executed release evidence.",
        f"Partial/questionable: {len(partial)} feature(s) need stronger proof.",
        f"Bug findings and error findings: {blocker_count} blocking item(s).",
        f"Outstanding findings: {coverage_count} coverage gap(s), {blocker_count} blocker(s), and {warning_count} warning(s).",
    ]
    if summary.get("filtered"):
        items.append(f"This is a filtered debug run: {omitted} release case(s) were not executed.")
    rendered = "".join(f"<li>{escape(item)}</li>" for item in items)
    gap_items = []
    for gap in summary["findings"].get("coverage_gaps", [])[:12]:
        label = gap.get("feature") or gap.get("case_id") or "coverage"
        gap_items.append(f"<li><strong>{escape(label)}</strong>: {escape(gap.get('message') or '')}</li>")
    gap_html = ""
    if gap_items:
        gap_html = f"<h3>Still Outstanding</h3><ul>{''.join(gap_items)}</ul>"
    return f'<section data-qid="outstanding-summary"><ul>{rendered}</ul>{gap_html}</section>'


def render_feature_row(feature: dict[str, Any]) -> str:
    gaps = "<br>".join(escape(item) for item in feature.get("coverage_gaps", [])) or "—"
    notes = "<br>".join(escape(item) for item in feature.get("notes", [])) or "—"
    readiness = str(feature["readiness"])
    return (
        "<tr>"
        f"<td>{escape(feature['id'])}</td>"
        f"<td class=\"{escape(readiness)}\">{escape(readiness)}</td>"
        f"<td>{escape(feature['required_cases'])}</td>"
        f"<td>{escape(feature['passed_cases'])}</td>"
        f"<td>{gaps}</td>"
        f"<td>{notes}</td>"
        "</tr>"
    )


def render_findings(findings: dict[str, list[dict[str, Any]]]) -> str:
    sections = []
    labels = (
        ("blockers", "Blocking Bug Findings and Error Findings"),
        ("warnings", "Warnings"),
        ("coverage_gaps", "Coverage Gaps"),
    )
    for key, label in labels:
        items = findings.get(key, [])
        if not items:
            sections.append(f"<h3>{escape(label)}</h3><p>None.</p>")
            continue
        rendered = []
        for item in items:
            rendered.append(
                "<li>"
                f"<strong>{escape(item.get('feature') or item.get('case_id') or key)}</strong>: "
                f"{escape(item.get('message') or '')}"
                "</li>"
            )
        sections.append(f"<h3>{escape(label)}</h3><ul>{''.join(rendered)}</ul>")
    return "\n".join(sections)


def render_row(result: dict[str, Any]) -> str:
    findings = "<br>".join(escape(item) for item in result["bug_findings"] + result.get("coverage_gaps", [])) or "None"
    skills = "".join(f'<span class="chip">{escape(skill)}</span>' for skill in result.get("skills_used", []))
    liveness = (
        f"{escape(result.get('liveness_source') or '')}"
        f"<br><code>events={escape(result.get('runtime_event_count', 0))}</code>"
    )
    if result.get("last_runtime_event"):
        liveness += f"<br><code>last={escape(result['last_runtime_event'])}</code>"
    if result.get("seconds_since_last_liveness") is not None:
        liveness += f"<br><code>quiet={escape(result['seconds_since_last_liveness'])}s</code>"
    artifacts = []
    report_dir = Path(result.get("report_dir") or ".")
    for key in ("stdout_path", "stderr_path", "runtime_status_path"):
        value = result.get(key)
        if value:
            artifacts.append(render_artifact_link(report_dir, value))
    for value in result.get("artifact_paths", []):
        artifacts.append(render_artifact_link(report_dir, value))
    return (
        '<article class="case-card">'
        f"<h3>{escape(result['name'])}</h3>"
        '<div class="case-meta">'
        f"<div><span>Feature</span>{escape(result.get('feature') or '')}</div>"
        f"<div><span>Type</span>{escape(result.get('case_type') or '')}</div>"
        f"<div><span>Execution</span><strong class=\"{escape(result['execution_status'])}\">{escape(result['execution_status'].upper())}</strong></div>"
        f"<div><span>Assertion</span><strong class=\"{escape(result['assertion_status'])}\">{escape(result['assertion_status'].upper())}</strong></div>"
        f"<div><span>Readiness</span><strong class=\"{escape(result['feature_readiness'])}\">{escape(result['feature_readiness'])}</strong></div>"
        f"<div><span>Seconds</span>{escape(result.get('duration_seconds', ''))}</div>"
        "</div>"
        f'<div class="case-section"><strong>Question</strong>{escape(result["question"])}<br><code>{escape(" ".join(result["command"]))}</code></div>'
        f'<div class="case-section response"><strong>Actual Response</strong>{escape(result.get("response") or "")}</div>'
        f'<div class="case-section response"><strong>Output Summary</strong>{escape(result.get("response_summary") or "")}</div>'
        f'<div class="case-section skills"><strong>Skills Used</strong>{skills or "None"}</div>'
        f'<div class="case-section"><strong>Liveness</strong>{liveness}</div>'
        f'<div class="case-section"><strong>Findings</strong>{findings}</div>'
        f'<div class="case-section artifact-links"><strong>Artifacts</strong>{" ".join(artifacts) or "None"}</div>'
        "</article>"
    )


def render_artifact_link(report_dir: Path, value: str) -> str:
    path = Path(value)
    try:
        href = path.relative_to(report_dir).as_posix()
    except ValueError:
        href = path.name
    return f'<a href="{escape(href)}"><code>{escape(path.name)}</code></a>'


def render_failure(result: dict[str, Any]) -> str:
    findings = "".join(f"<li>{escape(item)}</li>" for item in result["bug_findings"])
    return (
        '<section class="finding">'
        f"<h3>{escape(result['name'])}</h3>"
        f"<ul>{findings}</ul>"
        f"<p><strong>Command:</strong> <code>{escape(' '.join(result['command']))}</code></p>"
        f"<p><strong>Stdout:</strong> <code>{escape(result.get('stdout_path') or '')}</code></p>"
        f"<p><strong>Stderr:</strong> <code>{escape(result.get('stderr_path') or '')}</code></p>"
        "</section>"
    )


def render_markdown(summary: dict[str, Any]) -> str:
    lines = [
        f"# {summary['title']}",
        "",
        f"- Created: `{summary['created_at']}`",
        f"- Run dir: `{summary['run_dir']}`",
        f"- Total: `{summary['totals']['total']}`",
        f"- Passed: `{summary['totals']['passed']}`",
        f"- Required failed: `{summary['totals']['failed_required']}`",
        f"- Optional failed: `{summary['totals']['failed_optional']}`",
        f"- Skipped/planned: `{summary['totals']['skipped_or_planned']}`",
        "",
        "| Case | Status | Question | Actual response | Output summary | Skills used | Bug findings |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for result in summary["results"]:
        findings = "<br>".join(result["bug_findings"])
        skills = ", ".join(result.get("skills_used", []))
        response = str(result.get("response", "")).replace("\n", "<br>")
        response_summary = str(result.get("response_summary", "")).replace("\n", "<br>")
        lines.append(
            f"| {result['name']} | {result['status']} | {result['question']} | "
            f"{response} | {response_summary} | {skills} | {findings} |"
        )
    return "\n".join(lines) + "\n"


def slugify(value: str) -> str:
    return "".join(ch if ch.isalnum() else "-" for ch in value.lower()).strip("-")


def excerpt(value: str, limit: int = 1500) -> str:
    value = (value or "").strip()
    if len(value) <= limit:
        return value
    return value[:limit] + "\n... [truncated]"


def escape(value: Any) -> str:
    return html.escape(str(value), quote=True)


if __name__ == "__main__":
    raise SystemExit(main())
