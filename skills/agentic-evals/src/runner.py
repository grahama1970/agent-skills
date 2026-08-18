"""Run deterministic multi-trial command evaluations from JSON fixtures.

Inputs are versioned fixture files with cases, commands, expected exit codes,
and optional stdout/stderr containment checks. Outputs are JSON readiness
reports. Failures are represented in the report; invalid fixtures fail closed
with a non-zero CLI exit.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import signal
import subprocess
import sys
import time
import uuid
from pathlib import Path
from statistics import mean
from typing import Any

import typer
from dotenv import load_dotenv
from loguru import logger

load_dotenv(override=False)

app = typer.Typer(no_args_is_help=True)

VALID_CASE_TYPES = {"positive", "negative", "adversarial"}
EVAL_FIXTURES = ("fixtures/agentic_eval.json", "fixtures/eval.json")
EVAL_PROVIDER_SKILLS = {"agentic-evals", "eval-skills"}
TRIAL_ENV_SCRUB_KEYS = ("UV_PROJECT_ENVIRONMENT", "VIRTUAL_ENV", "PYTHONPYCACHEPREFIX")

#: Captured streams are evidence, not logs. Bound them so one chatty case cannot
#: make a report unreadable or unwritable, and scrub obvious secrets before they
#: are persisted into a report that gets attached to tickets.
MAX_STREAM_CHARS = 20000
_SECRET_RE = re.compile(
    r"(?i)\b(token|secret|api[_-]?key|password|passwd|authorization|bearer)\b(\s*[=:]\s*|\s+)(\S+)"
)

#: Outcomes are distinguished because they mean different things to a release
#: gate: FAIL is a defect, BLOCKED is an unmet precondition, NOT_TESTED is
#: absence of evidence. Only PASS on a required case contributes to READY.
OUTCOME_PASS = "PASS"
OUTCOME_FAIL = "FAIL"
OUTCOME_BLOCKED = "BLOCKED"
OUTCOME_NOT_TESTED = "NOT_TESTED"
OUTCOME_SKIPPED = "SKIPPED"


def _redact(text: str) -> str:
    return _SECRET_RE.sub(lambda m: f"{m.group(1)}{m.group(2)}[REDACTED]", text or "")


def _bound(text: str) -> str:
    text = _redact(text or "")
    if len(text) <= MAX_STREAM_CHARS:
        return text
    half = MAX_STREAM_CHARS // 2
    dropped = len(text) - MAX_STREAM_CHARS
    return f"{text[:half]}\n...[{dropped} chars omitted]...\n{text[-half:]}"


def _sha256_file(path: Path) -> str | None:
    try:
        return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


def _json_pointer(doc: Any, pointer: str) -> Any:
    """RFC6901 lookup. Raises KeyError with the failing segment."""
    if pointer in ("", "/"):
        return doc
    node = doc
    for raw in pointer.lstrip("/").split("/"):
        token = raw.replace("~1", "/").replace("~0", "~")
        if isinstance(node, list):
            node = node[int(token)]
        else:
            node = node[token]
    return node


def _resolve(cwd: Path, raw: str) -> Path:
    candidate = Path(raw)
    return candidate if candidate.is_absolute() else (cwd / candidate)


def _artifact_value(cwd: Path, spec: dict[str, Any]) -> Any:
    path = _resolve(cwd, spec["path"])
    doc = json.loads(path.read_text(encoding="utf-8"))
    return _json_pointer(doc, spec.get("json_pointer", ""))


def check_artifacts(case: dict[str, Any], cwd: Path) -> tuple[list[str], dict[str, str]]:
    """Assert on files the case produced, not on what it printed.

    stdout substring matching cannot express "these two receipts name the same
    session" or "the run left no artifact behind", which is what a real E2E case
    needs to prove.
    """
    specs = case.get("expected", {}).get("artifacts") or []
    problems: list[str] = []
    hashes: dict[str, str] = {}
    for spec in specs:
        raw = spec.get("path")
        if not raw:
            problems.append("artifact spec missing 'path'")
            continue
        path = _resolve(cwd, raw)
        if spec.get("absent"):
            if path.exists():
                problems.append(f"{raw}: expected absent, but it exists")
            continue
        if not path.is_file():
            problems.append(f"{raw}: missing")
            continue
        digest = _sha256_file(path)
        if digest:
            hashes[raw] = digest
        if "sha256" in spec and digest != spec["sha256"]:
            problems.append(f"{raw}: sha256 {digest} != {spec['sha256']}")
        if spec.get("min_bytes") is not None and path.stat().st_size < int(spec["min_bytes"]):
            problems.append(f"{raw}: {path.stat().st_size} bytes < min_bytes {spec['min_bytes']}")
        wants_value = "equals" in spec or "json_pointer" in spec or "equals_artifact" in spec
        if not wants_value:
            continue
        try:
            value = _artifact_value(cwd, spec)
        except (OSError, ValueError, KeyError, IndexError) as exc:
            problems.append(f"{raw}: cannot read {spec.get('json_pointer', '')!r}: {exc}")
            continue
        if "equals" in spec and value != spec["equals"]:
            problems.append(f"{raw}{spec.get('json_pointer', '')}: {value!r} != {spec['equals']!r}")
        other = spec.get("equals_artifact")
        if other:
            try:
                other_value = _artifact_value(cwd, other)
            except (OSError, ValueError, KeyError, IndexError) as exc:
                problems.append(f"{other.get('path')}: cannot read for cross-check: {exc}")
                continue
            if value != other_value:
                problems.append(
                    f"cross-artifact mismatch: {raw}{spec.get('json_pointer', '')}={value!r} "
                    f"!= {other['path']}{other.get('json_pointer', '')}={other_value!r}"
                )
    return problems, hashes


def _pids_in_group(pgid: int) -> list[int]:
    survivors: list[int] = []
    proc_root = Path("/proc")
    if not proc_root.is_dir():
        return survivors
    for entry in proc_root.iterdir():
        if not entry.name.isdigit():
            continue
        pid = int(entry.name)
        try:
            if os.getpgid(pid) == pgid:
                survivors.append(pid)
        except (ProcessLookupError, PermissionError, OSError):
            continue
    return survivors


def _terminate_group(proc: subprocess.Popen) -> list[int]:
    """Kill the trial's whole process group and report survivors.

    subprocess timeouts kill only the direct child. A timed-out case that leaves
    a grandchild holding a lock silently corrupts every later case in a serial
    run, so teardown is verified rather than assumed.
    """
    try:
        pgid = os.getpgid(proc.pid)
    except (ProcessLookupError, PermissionError, OSError):
        return []
    for sig in (signal.SIGTERM, signal.SIGKILL):
        try:
            os.killpg(pgid, sig)
        except (ProcessLookupError, PermissionError, OSError):
            break
        try:
            proc.wait(timeout=5)
            break
        except subprocess.TimeoutExpired:
            continue
    return [pid for pid in _pids_in_group(pgid) if pid != os.getpid()]


def load_manifest(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        manifest = json.load(handle)
    if manifest.get("version") != 2:
        raise typer.BadParameter("fixture version must be 2")
    cases = manifest.get("cases")
    if not isinstance(cases, list):
        raise typer.BadParameter("fixture must contain a cases list")
    trials = manifest.get("trials", 3)
    if not isinstance(trials, int) or trials < 1:
        raise typer.BadParameter("trials must be a positive integer")
    for case in cases:
        validate_case(case)
    _assert_not_slop(manifest, cases, trials)
    return manifest


_TRIVIAL_PROGRAMS = frozenset({"echo", "true", ":", "printf", "test", "[", "cat", "ls", "pwd", "head"})


def _command_text(command: list[str]) -> str:
    """Effective command text, unwrapping bash/sh -c so heuristics see the real work."""
    if len(command) >= 3 and command[0] in {"bash", "sh"} and command[1] == "-c":
        return command[2]
    return " ".join(command)


def _is_trivial(command: list[str]) -> bool:
    """A case that only echoes/returns a constant proves nothing — self-serving slop."""
    text = _command_text(command).strip()
    first = text.split()[0] if text.split() else ""
    if first in _TRIVIAL_PROGRAMS and not any(tok in text for tok in ("&&", "||", ";", "|", ".sh", ".py", "curl", "http")):
        return True
    return False


def _is_real_world(case: dict[str, Any]) -> bool:
    """A real-world case is explicitly flagged AND exercises a live path, not a stub.

    It must invoke a substantive program (a skill entrypoint, script, live HTTP,
    or test runner) and must NOT feed itself canned fixture/stub inputs, which
    would make it prove plumbing rather than real behavior.
    """
    if not case.get("real_world"):
        return False
    text = _command_text(case["command"])
    if "fixtures/" in text or "/fixtures/" in text:
        return False
    return any(marker in text for marker in ("run.sh", ".py", "curl", "http://", "https://", "pytest", "nightly", "e2e"))


def _is_non_deterministic(case: dict[str, Any]) -> bool:
    """A case that samples fresh inputs each run rather than a hard-coded key.

    Non-determinism is what makes an adversarial eval bite: a fixed-key case can
    be satisfied by overfitting to that one key, and it silently rots as the
    system moves. The markers below name the sampling explicitly so the runner
    can require it, not infer it.
    """
    text = _command_text(case["command"])
    # Explicit sampling markers only. A probe SCRIPT name is not enough --
    # "analyst_probe.py resolve CWE-999999" is a fixed key. Non-determinism
    # means the case draws fresh inputs each run: a --samples/--seed sweep or a
    # shell $RANDOM. (Caught by the gate on monitor-sparta, whose fixed-key
    # probe calls were wrongly counted as non-deterministic.)
    return "--samples" in text or "--seed" in text or "RANDOM" in text


def _compliance_tier_problems(manifest: dict[str, Any], cases: list[dict[str, Any]]) -> list[str]:
    """Enforce the compliance-grade eval contract when a fixture declares it.

    Ordinary skills keep the baseline gate (>=1 adversarial, >=1 real-world). A
    fixture that sets `eval_tier: "compliance"` is asserting it guards a
    compliance pipeline stage, and the runner then MANDATES what practice alone
    does not guarantee (operator directive 2026-08-12, "this is a compliance
    pipeline and must be robustly hardened"):

      - the majority of cases are adversarial/negative, not positive controls
      - at least one case is non-deterministic (samples fresh inputs per run)
      - every non-deterministic case names a per-run sample size of >= 50, so a
        stage's nightly coverage is hundreds-to-thousands of assertions, not a
        handful

    Declaring the tier and then failing to meet it is itself a slop failure:
    the mandate cannot be satisfied by removing the declaration quietly, because
    the compliance pipeline's own fixtures set it and their conformance tests
    read it back.
    """
    if manifest.get("eval_tier") != "compliance":
        return []
    problems: list[str] = []
    adversarial = [c for c in cases if c.get("type") in {"negative", "adversarial"}]
    if len(adversarial) * 2 <= len(cases):
        problems.append(
            f"eval_tier=compliance requires a strict MAJORITY of cases to be adversarial/negative "
            f"(more than half, not exactly half); got {len(adversarial)}/{len(cases)}"
        )
    nd = [c for c in cases if _is_non_deterministic(c)]
    if not nd:
        problems.append(
            "eval_tier=compliance requires at least one non-deterministic case "
            "(--samples/--seed/random probe); a fixed-key-only fixture cannot harden a pipeline"
        )
    for c in nd:
        text = _command_text(c["command"])
        import re as _re
        sizes = [int(n) for n in _re.findall(r"--samples\s+(\d+)", text)]
        if sizes and max(sizes) < 50:
            problems.append(
                f"eval_tier=compliance case {c['name']!r} samples only {max(sizes)}; "
                "compliance stages need >= 50 assertions per run (target ~1000/stage across modes)"
            )
    return problems


def _assert_not_slop(manifest: dict[str, Any], cases: list[dict[str, Any]], trials: int) -> None:
    """Fail-closed on self-serving slop fixtures.

    Prevents the failure mode where an eval passes trivially without proving the
    skill works: it requires repeatability, an adversarial/negative check, and at
    least one real-world case that exercises a live path without stub inputs.
    """
    # Narrow, explicit exemption: fixtures that test the runner itself or serve
    # as documentation examples are not skill evaluations. They must say so.
    # This is NEVER valid for a real skill's evaluation fixture.
    if manifest.get("eval_kind") in {"runner_selftest", "scaffold"}:
        return
    problems: list[str] = []
    if trials < 2:
        problems.append("trials must be >= 2 for repeatability (a single-trial eval is not evidence)")
    trivial = [c["name"] for c in cases if _is_trivial(c["command"])]
    if trivial:
        problems.append(f"trivial echo/constant cases prove nothing: {trivial}")
    if not any(c.get("type") in {"negative", "adversarial"} for c in cases):
        problems.append("no negative or adversarial case — an all-positive fixture is self-serving")
    if not any(_is_real_world(c) for c in cases):
        problems.append(
            "no real-world case: at least one case must set \"real_world\": true and exercise a live "
            "path (skill entrypoint / script / live HTTP / test runner) WITHOUT feeding itself "
            "fixtures/ stub inputs"
        )
    problems.extend(_compliance_tier_problems(manifest, cases))
    if problems:
        raise typer.BadParameter(
            "fixture rejected as low-value ('slop'): "
            + "; ".join(problems)
            + ". An agentic eval must prove real-world behavior, not deterministic plumbing."
        )


def validate_case(case: dict[str, Any]) -> None:
    if not isinstance(case.get("name"), str) or not case["name"]:
        raise typer.BadParameter("each case needs a non-empty name")
    if case.get("type") not in VALID_CASE_TYPES:
        raise typer.BadParameter(f"case {case['name']} has invalid type")
    command = case.get("command")
    if (
        not isinstance(command, list)
        or not command
        or not all(isinstance(part, str) for part in command)
    ):
        raise typer.BadParameter(f"case {case['name']} command must be a non-empty argv list")
    expected = case.get("expected")
    if not isinstance(expected, dict) or not isinstance(expected.get("exit_code"), int):
        raise typer.BadParameter(f"case {case['name']} expected.exit_code must be an integer")


def _stream_text(value: str | bytes | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


def trial_environment() -> dict[str, str]:
    """Return an environment for evaluated commands without runner venv leakage."""
    env = os.environ.copy()
    for key in TRIAL_ENV_SCRUB_KEYS:
        env.pop(key, None)
    return env


def run_trial(command: list[str], cwd: Path, timeout_seconds: float) -> dict[str, Any]:
    started = time.monotonic()
    proc = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=cwd,
        env=trial_environment(),
        text=True,
        start_new_session=True,
    )
    timed_out = False
    survivors: list[int] = []
    try:
        out, err = proc.communicate(timeout=timeout_seconds)
    except subprocess.TimeoutExpired:
        timed_out = True
        survivors = _terminate_group(proc)
        try:
            out, err = proc.communicate(timeout=10)
        except subprocess.TimeoutExpired:
            out, err = "", ""
    return {
        "exit_code": None if timed_out else proc.returncode,
        "stdout": _bound(_stream_text(out)),
        "stderr": _bound(_stream_text(err)),
        "duration_ms": round((time.monotonic() - started) * 1000, 3),
        "timed_out": timed_out,
        "orphan_pids_after_teardown": survivors,
    }


def trial_passed(case: dict[str, Any], trial: dict[str, Any]) -> bool:
    """Back-compatible boolean view of trial_outcome."""
    return trial_outcome(case, trial, Path(trial.get("_cwd", ".")))[0] == OUTCOME_PASS


def trial_outcome(case: dict[str, Any], trial: dict[str, Any], cwd: Path) -> tuple[str, list[str]]:
    """Classify one trial, and say why when it is not a pass."""
    if trial["timed_out"]:
        detail = [f"timed out after {round(trial['duration_ms'] / 1000)}s"]
        if trial.get("orphan_pids_after_teardown"):
            detail.append(
                "process group survived teardown: "
                + ", ".join(str(pid) for pid in trial["orphan_pids_after_teardown"])
            )
        return OUTCOME_FAIL, detail
    if trial.get("orphan_pids_after_teardown"):
        return OUTCOME_FAIL, [
            "process group survived teardown: "
            + ", ".join(str(pid) for pid in trial["orphan_pids_after_teardown"])
        ]
    for marker in case.get("blocked_when_stdout_contains", []) or []:
        if marker in trial["stdout"] or marker in trial["stderr"]:
            return OUTCOME_BLOCKED, [f"precondition unmet: saw {marker!r}"]
    expected = case["expected"]
    problems: list[str] = []
    if trial["exit_code"] != expected["exit_code"]:
        problems.append(f"exit_code {trial['exit_code']} != {expected['exit_code']}")
    for needle in expected.get("stdout_contains", []):
        if needle not in trial["stdout"]:
            problems.append(f"stdout missing {needle!r}")
    for needle in expected.get("stderr_contains", []):
        if needle not in trial["stderr"]:
            problems.append(f"stderr missing {needle!r}")
    for needle in expected.get("stdout_excludes", []) or []:
        if needle in trial["stdout"]:
            problems.append(f"stdout unexpectedly contains {needle!r}")
    artifact_problems, hashes = check_artifacts(case, cwd)
    problems.extend(artifact_problems)
    if hashes:
        trial["artifact_hashes"] = hashes
    return (OUTCOME_PASS if not problems else OUTCOME_FAIL), problems


def case_outcome(trial_outcomes: list[str]) -> str:
    if not trial_outcomes:
        return OUTCOME_NOT_TESTED
    if all(outcome == OUTCOME_PASS for outcome in trial_outcomes):
        return OUTCOME_PASS
    if any(outcome == OUTCOME_FAIL for outcome in trial_outcomes):
        return OUTCOME_FAIL
    return OUTCOME_BLOCKED


def readiness_for(case_reports: list[dict[str, Any]]) -> str:
    """READY means every REQUIRED case passed every trial.

    A required BLOCKED case is an unmet precondition, so it cannot contribute to
    READY -- otherwise a suite that never exercised its own subject reports the
    same state as one that passed.
    """
    if not case_reports:
        return "NOT_ESTABLISHED"
    required = [c for c in case_reports if c.get("required", True)]
    scored = required or case_reports
    if all(c.get("outcome", OUTCOME_NOT_TESTED) == OUTCOME_PASS for c in scored):
        return "READY"
    if any(c["passed_trials"] > 0 for c in scored):
        return "USABLE_WITH_GAPS"
    return "NOT_READY"


def _repo_provenance(cwd: Path) -> dict[str, Any]:
    def _git(*args: str) -> str | None:
        try:
            out = subprocess.run(
                ["git", *args], cwd=cwd, capture_output=True, text=True, timeout=10, check=False
            )
        except (OSError, subprocess.SubprocessError):
            return None
        value = out.stdout.strip()
        return value or None

    return {"sha": _git("rev-parse", "HEAD"), "ref": _git("rev-parse", "--abbrev-ref", "HEAD")}


def evaluate_manifest(path: Path, timeout_seconds: float) -> dict[str, Any]:
    manifest = load_manifest(path)
    trials = manifest.get("trials", 3)
    cwd = path.parent
    run_id = uuid.uuid4().hex[:12]
    cases = []
    raw_cases = manifest["cases"]
    for index, case in enumerate(raw_cases):
        case_id = f"{run_id}-c{index:03d}"
        # A case may declare its own timeout (real-world cases that run a live
        # nightly need minutes, not the 30s default that fits unit-test cases).
        case_timeout = case.get("timeout_seconds", timeout_seconds)
        try:
            case_timeout = max(0.1, float(case_timeout))
        except (TypeError, ValueError):
            case_timeout = timeout_seconds
        results = []
        outcomes = []
        problems: list[str] = []
        for trial_index in range(trials):
            trial = run_trial(case["command"], cwd, case_timeout)
            trial["trial_id"] = f"{case_id}-t{trial_index:02d}"
            outcome, why = trial_outcome(case, trial, cwd)
            trial["outcome"] = outcome
            trial["problems"] = why
            outcomes.append(outcome)
            problems.extend(why)
            results.append(trial)
        passed_trials = sum(1 for outcome in outcomes if outcome == OUTCOME_PASS)
        cases.append(
            {
                "name": case["name"],
                "type": case["type"],
                "case_id": case_id,
                "required": bool(case.get("required", True)),
                "outcome": case_outcome(outcomes),
                "problems": sorted(set(problems)),
                "argv": list(case["command"]),
                "passed_trials": passed_trials,
                "total_trials": trials,
                "pass_rate": round(passed_trials / trials, 4) if trials else 0.0,
                "avg_latency_ms": round(mean(result["duration_ms"] for result in results), 3)
                if results
                else 0.0,
                "trials": results,
            }
        )
    # The manifest's own proof scope and claims are the honest description of
    # what this suite proves. Overwriting them with a generic "fixture wiring
    # smoke" claim made every report -- including live-provider suites --
    # understate or misstate its own evidence.
    default_claims = {
        "proves": "declared local commands met explicit fixture expectations across repeated trials",
        "does_not_prove": "semantic correctness, live services, LLM judge behavior, or release readiness",
    }
    live = bool(manifest.get("live", any(c.get("real_world") for c in raw_cases)))
    return {
        "schema": "agentic_evals.report.v2",
        "source": str(path),
        "run_id": run_id,
        "fixture_sha256": _sha256_file(path),
        "repo": _repo_provenance(cwd),
        "mocked": bool(manifest.get("mocked", False)),
        "fixture_backed": True,
        "live": live,
        "proof_scope": manifest.get("proof_scope") or "fixture wiring smoke",
        "claims": manifest.get("claims") or default_claims,
        "what_was_exercised": manifest.get("what_was_exercised")
        or "local commands declared in the fixture manifest",
        "what_remains_unverified": manifest.get("what_remains_unverified")
        or "semantic correctness, live services, LLM judge behavior, and release readiness",
        "readiness": readiness_for(cases),
        "case_count": len(cases),
        "required_case_count": sum(1 for c in cases if c["required"]),
        "outcome_counts": {
            outcome: sum(1 for c in cases if c["outcome"] == outcome)
            for outcome in (OUTCOME_PASS, OUTCOME_FAIL, OUTCOME_BLOCKED, OUTCOME_NOT_TESTED)
        },
        "trial_count": sum(case["total_trials"] for case in cases),
        "cases": cases,
    }


def classify_eval_posture(skill_dir: Path) -> str:
    skill_md = skill_dir / "SKILL.md"
    text = skill_md.read_text(encoding="utf-8", errors="ignore") if skill_md.exists() else ""
    if skill_dir.name in EVAL_PROVIDER_SKILLS:
        return "eval_provider"
    if (skill_dir / "fixtures" / "agentic_eval.json").exists():
        return "agentic_fixture"
    if (skill_dir / "fixtures" / "eval.json").exists():
        return "legacy_eval_fixture"
    if "agentic-evals" in text or "eval-skills" in text:
        return "delegates_to_eval_skill"
    if "eval_not_required" in text:
        return "eval_not_required"
    return "missing"


def run_validator(skill_dir: Path, skills_root: Path, validator: Path, timeout_seconds: float) -> list[dict[str, Any]]:
    try:
        result = subprocess.run(
            [
                sys.executable,
                str(validator),
                str(skill_dir),
                "--json",
                "--skills-root",
                str(skills_root),
            ],
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        logger.error("validator timed out for {}: {}", skill_dir.name, exc)
        return [
            {
                "rule": "VALIDATOR_TIMEOUT",
                "severity": "error",
                "skill": skill_dir.name,
                "message": f"validator exceeded {timeout_seconds} seconds",
            }
        ]
    if result.returncode != 0:
        return [
            {
                "rule": "VALIDATOR_RUNNER",
                "severity": "error",
                "skill": skill_dir.name,
                "message": result.stderr.strip() or result.stdout.strip() or "validator failed",
            }
        ]
    try:
        parsed = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        logger.error("validator returned invalid JSON for {}: {}", skill_dir.name, exc)
        return [
            {
                "rule": "VALIDATOR_JSON",
                "severity": "error",
                "skill": skill_dir.name,
                "message": "validator returned invalid JSON",
            }
        ]
    return parsed if isinstance(parsed, list) else []


def audit_skills_report(skills_root: Path, validator: Path, timeout_seconds: float) -> dict[str, Any]:
    skills = sorted(path for path in skills_root.iterdir() if (path / "SKILL.md").exists())
    skill_reports = []
    findings: list[dict[str, Any]] = []
    for skill_dir in skills:
        posture = classify_eval_posture(skill_dir)
        skill_findings = run_validator(skill_dir, skills_root, validator, timeout_seconds)
        eval_findings = [finding for finding in skill_findings if finding.get("rule") in {"EVAL001", "EVAL002"}]
        eval001_findings = [finding for finding in eval_findings if finding.get("rule") == "EVAL001"]
        eval002_findings = [finding for finding in eval_findings if finding.get("rule") == "EVAL002"]
        recommended_action = recommended_action_for(
            skill_dir,
            posture,
            needs_fixture=bool(eval001_findings),
            needs_composition=bool(eval002_findings),
        )
        findings.extend(skill_findings)
        skill_reports.append(
            {
                "skill": skill_dir.name,
                "eval_posture": posture,
                "eval_required": bool(eval_findings),
                "needs_agentic_evals_composition": bool(eval002_findings),
                "recommended_action": recommended_action,
                "eval_findings": eval_findings,
            }
        )

    posture_counts: dict[str, int] = {}
    for item in skill_reports:
        posture = item["eval_posture"]
        posture_counts[posture] = posture_counts.get(posture, 0) + 1
    action_counts: dict[str, int] = {}
    for item in skill_reports:
        action = item["recommended_action"]
        action_counts[action] = action_counts.get(action, 0) + 1

    eval001 = [finding for finding in findings if finding.get("rule") == "EVAL001"]
    eval002 = [finding for finding in findings if finding.get("rule") == "EVAL002"]
    return {
        "schema": "agentic_evals.skill_posture_audit.v1",
        "mocked": False,
        "live": False,
        "proof_scope": "static repository eval posture audit",
        "claims": {
            "proves": "which top-level skills currently declare eval posture and compose agentic-evals",
            "does_not_prove": "per-skill semantic behavior, live service behavior, or fixture quality",
        },
        "skills_root": str(skills_root),
        "validator": str(validator),
        "summary": {
            "skills_checked": len(skills),
            "total_findings": len(findings),
            "eval001_count": len(eval001),
            "eval002_count": len(eval002),
            "posture_counts": posture_counts,
            "recommended_action_counts": action_counts,
            "eval001_skills": sorted({finding["skill"] for finding in eval001}),
            "eval002_skills": sorted({finding["skill"] for finding in eval002}),
        },
        "skills": skill_reports,
        "findings": findings,
    }


def recommended_action_for(
    skill_dir: Path,
    posture: str,
    needs_fixture: bool,
    needs_composition: bool,
) -> str:
    if not needs_fixture and not needs_composition:
        return "none"
    if needs_composition and not needs_fixture:
        return "compose_agentic_evals"
    if needs_composition and needs_fixture:
        if (skill_dir / "sanity.sh").exists() or (skill_dir / "run.sh").exists():
            return "compose_agentic_evals_and_scaffold_fixture"
        return "compose_agentic_evals_and_scaffold_static_validation_fixture"
    if posture != "missing":
        return "strengthen_existing_eval"
    if (skill_dir / "sanity.sh").exists() or (skill_dir / "run.sh").exists():
        return "scaffold_fixture"
    return "scaffold_static_validation_fixture"


def _entrypoint_command(fixture_dir: Path, entrypoint: Path, *args: str) -> list[str]:
    rel_entrypoint = os.path.relpath(entrypoint, start=fixture_dir)
    return ["bash", rel_entrypoint, *args]


def _validator_command(fixture_dir: Path, skill_dir: Path) -> list[str]:
    validator = skill_dir.parent / "best-practices-skills" / "scripts" / "validate_skill.py"
    rel_validator = os.path.relpath(validator, start=fixture_dir)
    rel_skill = os.path.relpath(skill_dir, start=fixture_dir)
    return ["python3", rel_validator, rel_skill, "--json"]


def scaffold_manifest(skill_dir: Path, fixture_dir: Path) -> dict[str, Any]:
    skill_name = skill_dir.name
    if (skill_dir / "sanity.sh").exists():
        case = {
            "name": "sanity",
            "type": "positive",
            "command": _entrypoint_command(fixture_dir, skill_dir / "sanity.sh"),
            "expected": {"exit_code": 0},
        }
    elif (skill_dir / "run.sh").exists():
        case = {
            "name": "run-help",
            "type": "positive",
            "command": _entrypoint_command(fixture_dir, skill_dir / "run.sh", "--help"),
            "expected": {"exit_code": 0},
        }
    else:
        case = {
            "name": "skill-contract-validation",
            "type": "positive",
            "command": _validator_command(fixture_dir, skill_dir),
            "expected": {"exit_code": 0},
        }

    entrypoint_backed = case["name"] in {"sanity", "run-help"}
    return {
        "version": 2,
        "skill": skill_name,
        "eval_kind": "scaffold",
        "trials": 3,
        "proof_scope": "fixture wiring smoke" if entrypoint_backed else "static skill contract validation",
        "claims": {
            "proves": (
                "the existing skill entrypoint exits with the expected status"
                if entrypoint_backed
                else "the skill contract can be parsed and checked by the best-practices-skills validator"
            ),
            "does_not_prove": "semantic correctness, live service behavior, or full skill readiness",
        },
        "cases": [case],
    }


def write_scaffold_fixture(skill_dir: Path, force: bool) -> dict[str, Any]:
    target = skill_dir / "fixtures" / "agentic_eval.json"
    if target.exists() and not force:
        return {
            "skill": skill_dir.name,
            "status": "skipped",
            "reason": "fixture_exists",
            "path": str(target),
        }
    manifest = scaffold_manifest(skill_dir.resolve(), target.resolve().parent)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return {
        "skill": skill_dir.name,
        "status": "created",
        "path": str(target),
        "case": manifest["cases"][0]["name"],
        "proof_scope": manifest["proof_scope"],
    }


def apply_scaffolds_report(
    skills_root: Path,
    validator: Path,
    timeout_seconds: float,
    write: bool,
    force: bool,
    limit: int | None,
) -> dict[str, Any]:
    audit = audit_skills_report(skills_root, validator, timeout_seconds)
    eligible = [
        item
        for item in audit["skills"]
        if item["recommended_action"]
        in {
            "scaffold_fixture",
            "scaffold_static_validation_fixture",
            "compose_agentic_evals_and_scaffold_fixture",
            "compose_agentic_evals_and_scaffold_static_validation_fixture",
        }
    ]
    selected = eligible[:limit] if limit is not None else eligible
    results = []
    for item in selected:
        skill_dir = skills_root / item["skill"]
        if not write:
            results.append(
                {
                    "skill": item["skill"],
                    "status": "dry_run",
                    "path": str(skill_dir / "fixtures" / "agentic_eval.json"),
                }
            )
            continue
        try:
            results.append(write_scaffold_fixture(skill_dir, force))
        except Exception as exc:
            logger.error("failed to scaffold {}: {}", item["skill"], exc)
            results.append(
                {
                    "skill": item["skill"],
                    "status": "error",
                    "message": str(exc),
                }
            )

    status_counts: dict[str, int] = {}
    for result in results:
        status = result["status"]
        status_counts[status] = status_counts.get(status, 0) + 1
    return {
        "schema": "agentic_evals.scaffold_apply_report.v1",
        "mocked": False,
        "live": False,
        "proof_scope": "fixture wiring scaffold application",
        "claims": {
            "proves": "which missing eval-posture skills had wiring fixtures created or would be created",
            "does_not_prove": "semantic correctness, fixture pass status, live service behavior, or release readiness",
        },
        "skills_root": str(skills_root),
        "write": write,
        "force": force,
        "limit": limit,
        "summary": {
            "eligible": len(eligible),
            "selected": len(selected),
            "created": status_counts.get("created", 0),
            "skipped": status_counts.get("skipped", 0),
            "dry_run": status_counts.get("dry_run", 0),
            "errors": status_counts.get("error", 0),
            "status_counts": status_counts,
        },
        "results": results,
    }


@app.command("run")
def run(
    manifest: Path = typer.Argument(..., exists=True, dir_okay=False, readable=True),
    output: Path | None = typer.Option(None, "--output", "-o", help="Optional path for the JSON report."),
    timeout_seconds: float = typer.Option(30.0, "--timeout-seconds", min=0.1),
    report_only: bool = typer.Option(
        False,
        "--report-only",
        help="Emit the report and exit 0 even when required cases failed.",
    ),
) -> None:
    """Run an agentic evaluation manifest.

    Exits non-zero unless every required case reached READY. A runner that exits
    0 on USABLE_WITH_GAPS lets an outer CI job go green over failed cases, which
    is the failure this gate exists to prevent. Use --report-only when you want
    the report without the gate.
    """
    report = evaluate_manifest(manifest, timeout_seconds)
    payload = json.dumps(report, indent=2)
    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        # Atomic: a killed run must not leave a half-written report that a
        # downstream reader would parse as truth.
        tmp = output.with_suffix(output.suffix + ".partial")
        tmp.write_text(payload + "\n", encoding="utf-8")
        os.replace(tmp, output)
    typer.echo(payload)
    if report["readiness"] != "READY" and not report_only:
        failed = [c["name"] for c in report["cases"] if c["outcome"] != OUTCOME_PASS and c["required"]]
        logger.error(
            "readiness={} required_not_passing={}", report["readiness"], ", ".join(failed) or "none"
        )
        raise typer.Exit(1)


@app.command("apply-scaffolds")
def apply_scaffolds(
    skills_root: Path = typer.Argument(..., exists=True, file_okay=False, readable=True),
    output: Path | None = typer.Option(None, "--output", "-o", help="Optional path for the JSON report."),
    validator: Path | None = typer.Option(None, "--validator", help="Path to validate_skill.py."),
    timeout_seconds: float = typer.Option(10.0, "--timeout-seconds", min=0.1),
    write: bool = typer.Option(False, "--write", help="Create missing fixtures. Default is dry-run."),
    force: bool = typer.Option(False, "--force", help="Overwrite existing generated fixtures."),
    limit: int | None = typer.Option(None, "--limit", min=1, help="Maximum scaffoldable skills to process."),
) -> None:
    """Create first-pass fixtures for skills whose audit action is scaffold_fixture."""
    resolved_root = skills_root.resolve()
    resolved_validator = (
        validator.resolve()
        if validator is not None
        else (Path(__file__).resolve().parents[2] / "best-practices-skills" / "scripts" / "validate_skill.py")
    )
    report = apply_scaffolds_report(resolved_root, resolved_validator, timeout_seconds, write, force, limit)
    payload = json.dumps(report, indent=2)
    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(payload + "\n", encoding="utf-8")
    typer.echo(payload)


@app.command("scaffold-fixture")
def scaffold_fixture(
    skill_dir: Path = typer.Argument(..., exists=True, file_okay=False, readable=True),
    output: Path | None = typer.Option(None, "--output", "-o", help="Path for the generated fixture."),
    force: bool = typer.Option(False, "--force", help="Overwrite an existing fixture."),
) -> None:
    """Create a first-pass agentic eval fixture from a skill entrypoint."""
    target = output or (skill_dir / "fixtures" / "agentic_eval.json")
    manifest = scaffold_manifest(skill_dir.resolve(), target.resolve().parent)
    if target.exists() and not force:
        raise typer.BadParameter(f"{target} already exists; pass --force to overwrite")
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(manifest, indent=2) + "\n"
    target.write_text(payload, encoding="utf-8")
    typer.echo(payload)


@app.command("audit-skills")
def audit_skills(
    skills_root: Path = typer.Argument(..., exists=True, file_okay=False, readable=True),
    output: Path | None = typer.Option(None, "--output", "-o", help="Optional path for the JSON report."),
    validator: Path | None = typer.Option(None, "--validator", help="Path to validate_skill.py."),
    timeout_seconds: float = typer.Option(10.0, "--timeout-seconds", min=0.1),
) -> None:
    """Audit top-level skills for an explicit agentic eval posture."""
    resolved_root = skills_root.resolve()
    resolved_validator = (
        validator.resolve()
        if validator is not None
        else (Path(__file__).resolve().parents[2] / "best-practices-skills" / "scripts" / "validate_skill.py")
    )
    report = audit_skills_report(resolved_root, resolved_validator, timeout_seconds)
    payload = json.dumps(report, indent=2)
    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(payload + "\n", encoding="utf-8")
    typer.echo(payload)


@app.command("schema")
def schema() -> None:
    """Print the report schema identifier."""
    typer.echo("agentic_evals.report.v1")


if __name__ == "__main__":
    app()
