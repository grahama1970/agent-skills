#!/usr/bin/env python3
"""Project-specific repeated pytest qualification; delegates native skill evaluation separately.

Inputs are committed tests/specs. Outputs are hash-bound per-trial JUnit/log/browser
records and a truthful readiness view. Missing/failing tests exit nonzero. This is
not a replacement for the owning agentic-evals runner or its receipt schema.
"""
import hashlib
import html
import importlib.metadata
import json
import os
import signal
import subprocess
import sys
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

import typer
from dotenv import load_dotenv
from loguru import logger
from pydantic import BaseModel, ConfigDict

from a_detection.io import atomic_json

ROOT = Path(__file__).resolve().parents[1]
app = typer.Typer(pretty_exceptions_enable=False)



load_dotenv(override=False)
class Trial(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    trial_id: str
    argv: list[str]
    exit_code: int
    duration_seconds: float
    evidence_directory: str
    junit_exists: bool
    transport_readback_status: Literal["PASS", "MISSING", "FAIL"]


class Report(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    schema_version: Literal["a_detection.mechanism_verification.v1"] = "a_detection.mechanism_verification.v1"
    run_id: str
    created_at: str
    mechanism_readiness: Literal["READY", "NOT_READY"]
    release_readiness: Literal["NOT_ESTABLISHED"] = "NOT_ESTABLISHED"
    real_world_detection: Literal["NOT_ESTABLISHED"] = "NOT_ESTABLISHED"
    profile: Literal["core", "full"]
    browser_journey: Literal["NOT_ESTABLISHED", "EXECUTED"]
    native_agentic_evals_executed: Literal[False] = False
    source_sha256: str
    source_unchanged: bool
    trials: list[Trial]
    artifact_sha256: dict[str, str]
    environment: dict[str, str]
    proves: list[str]
    does_not_prove: list[str]


def inventory() -> dict[str, str]:
    selected = []
    for name in ("src", "tests", "scripts", "specs", "fixtures", ".pi"):
        selected.extend((ROOT / name).rglob("*"))
    selected.extend(ROOT / name for name in ("pyproject.toml", "immutable_goal.json", "setup-project.yaml"))
    return {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(selected) if path.is_file() and "__pycache__" not in path.parts
            and path.suffix != ".pyc" and not any(part.endswith(".egg-info") for part in path.parts)}


@app.command()
def main(output: Path = Path("reports/qualification"), trials: int = 3, samples: int = 128, profile: str = "full"):
    if profile not in ("core", "full"):
        raise typer.BadParameter("profile must be core or full")
    if trials < 3 or not 50 <= samples <= 5000:
        raise typer.BadParameter("Use at least three trials and 50–5000 fresh samples.")
    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8]
    run_dir = output.resolve() / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    before = inventory()
    atomic_json(run_dir / "source-manifest.json", before)
    rows = []
    for number in range(1, trials + 1):
        trial_id = f"trial-{number}"
        location = run_dir / trial_id
        location.mkdir()
        argv = [sys.executable, "-m", "pytest", "-q", "--samples", str(samples),
                "--junitxml", str(location / "junit.xml")]
        if profile == "core":
            argv += ["--ignore=tests/test_browser.py"]
        env = dict(os.environ, A_DETECTION_TEST_ARTIFACTS=str(location / "browser"))
        started = time.monotonic()
        with (location / "stdout.log").open("wb") as stdout, (location / "stderr.log").open("wb") as stderr:
            process = subprocess.Popen(argv, cwd=ROOT, env=env, stdout=stdout, stderr=stderr,
                                       start_new_session=True)
            try:
                code = process.wait(timeout=300)
            except subprocess.TimeoutExpired:
                logger.error("qualification_trial_timeout trial={}", trial_id)
                os.killpg(process.pid, signal.SIGKILL)
                process.wait(timeout=10)
                code = 124
        readback = location / ("browser/browser-readback.json" if profile == "full" else "browser/http-readback.json")
        readback_status = "MISSING"
        if readback.is_file():
            parsed = json.loads(readback.read_text())
            readback_status = "PASS" if parsed.get("status") == "PASS" else "FAIL"
        row = Trial(trial_id=trial_id, argv=argv, exit_code=code,
                    duration_seconds=time.monotonic() - started,
                    evidence_directory=str(location.relative_to(run_dir)),
                    junit_exists=(location / "junit.xml").is_file(),
                    transport_readback_status=readback_status)
        rows.append(row)
        logger.info("trial={} exit_code={} browser_readback={}", trial_id, code, readback_status)
    unchanged = inventory() == before
    ready = unchanged and all(row.exit_code == 0 and row.junit_exists and
                              row.transport_readback_status == "PASS" for row in rows)
    files = {str(path.relative_to(run_dir)): hashlib.sha256(path.read_bytes()).hexdigest()
             for path in sorted(run_dir.rglob("*")) if path.is_file()}
    versions = {name: importlib.metadata.version(name) for name in
                ("fastapi", "pydantic", "scikit-learn", "pytest", "playwright", "httpx")}
    versions["python"] = sys.version
    report = Report(run_id=run_id, created_at=datetime.now(UTC).isoformat(),
        mechanism_readiness="READY" if ready else "NOT_READY", profile=profile,
        browser_journey="EXECUTED" if profile == "full" and ready else "NOT_ESTABLISHED",
        source_sha256=hashlib.sha256(json.dumps(before, sort_keys=True).encode()).hexdigest(),
        source_unchanged=unchanged, trials=rows, artifact_sha256=files, environment=versions,
        proves=["Declared schema, SQLite, statistical, training and independent-replay mechanisms.",
                "Actual HTTP server with independent exported-record readback; browser proof is profile-specific.",
                "Fresh Unicode sampling and negative controls under the declared source snapshot."],
        does_not_prove=["Real-human or unseen-generator detection efficacy.",
                       "Transformer-backed likelihood, Docker, clean uv resolution or public deployment.",
                       "Native agentic-evals, Battle, acceptance-contract or create-report qualification.",
                       "Human accessibility and fairness qualification."])
    atomic_json(run_dir / "report.json", report.model_dump(mode="json"))
    summary = f"# a-detection qualification\n\nMechanisms: **{report.mechanism_readiness}**\n\nRelease / real-world detection: **NOT_ESTABLISHED**\n\n"
    summary += f"Executed {trials} unchanged-source trials with {samples} fresh Unicode edit samples per trial.\n\n"
    summary += "\n".join(f"- {item}" for item in report.does_not_prove)
    (run_dir / "report.md").write_text(summary + "\n")
    rendered = "<!doctype html><meta charset='utf-8'><title>a-detection verification</title>"
    rendered += "<style>body{max-width:1000px;margin:40px auto;font:16px/1.6 system-ui;padding:20px}pre{white-space:pre-wrap}</style>"
    rendered += f"<h1>a-detection: {report.mechanism_readiness}</h1><h2>Release and detection efficacy: NOT_ESTABLISHED</h2>"
    rendered += "<pre>" + html.escape(json.dumps(report.model_dump(), indent=2)) + "</pre>"
    (run_dir / "index.html").write_text(rendered)
    typer.echo(str(run_dir / "report.json"))
    raise typer.Exit(0 if ready else 1)


if __name__ == "__main__":
    app()
