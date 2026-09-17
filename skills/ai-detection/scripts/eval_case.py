#!/usr/bin/env python3
"""Named project checks for the owning agentic-evals runner; no generic runner or judge."""
import hashlib
import os
import subprocess
import sys
import uuid
from enum import StrEnum
from pathlib import Path

import typer
from dotenv import load_dotenv
from loguru import logger
from pydantic import BaseModel, ConfigDict

from ai_detection.io import atomic_json

ROOT = Path(__file__).resolve().parents[1]
app = typer.Typer(pretty_exceptions_enable=False)



load_dotenv(override=False)
class Case(StrEnum):
    API = "api"
    AUTH = "auth"
    BOUNDARIES = "boundaries"
    REPLAY = "replay"
    LEAKAGE = "leakage"
    CALIBRATION = "calibration"
    UNICODE = "unicode"
    TRAINING = "training"
    HTTP = "http"
    BROWSER = "browser"
    EFFICACY = "efficacy"


SELECTIONS = {
    Case.API: ["tests/test_api.py::test_http_session_roundtrip"],
    Case.AUTH: ["tests/test_api.py::test_error_does_not_echo_sensitive_unknown_value",
                "tests/test_evidence.py::test_mutation_guards_preserve_durable_state"],
    Case.BOUNDARIES: ["tests/test_contracts.py"],
    Case.REPLAY: ["tests/test_evidence.py::test_independent_checker_rejects_changed_evidence"],
    Case.LEAKAGE: ["tests/test_detection.py::test_cross_split_leakage_rejected"],
    Case.CALIBRATION: ["tests/test_detection.py::test_independent_low_false_positive_confidence_bound"],
    Case.UNICODE: ["tests/test_evidence.py::test_fresh_unicode_edit_sequences"],
    Case.TRAINING: ["tests/test_detection.py::test_train_safe_serialization_and_frozen_test_protocol"],
    Case.HTTP: ["tests/test_live_http.py"],
    Case.BROWSER: ["tests/test_browser.py"],
}


class Receipt(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    schema_version: str = "ai_detection.case_execution.v1"
    case: str
    status: str
    executed: bool
    exit_code: int
    argv: list[str]
    unique_run_directory: str
    reason: str
    artifact_sha256: dict[str, str]


@app.command()
def main(case: Case, samples: int = 128):
    if not 50 <= samples <= 5000:
        raise typer.BadParameter("Use 50–5000 samples.")
    base = ROOT / "reports/native-cases"
    base.mkdir(parents=True, exist_ok=True)
    destination = base / f"{case.value}.json"
    destination.unlink(missing_ok=True)
    run = base / f"{case.value}-{uuid.uuid4().hex}"
    run.mkdir()
    argv, code, reason = [], 3, "Independent human and held-out-generator evidence has not been qualified."
    efficacy_request = os.environ.get("AI_DETECTION_EFFICACY_REQUEST")
    executed = case != Case.EFFICACY or bool(efficacy_request)
    if executed:
        argv = [sys.executable, "-m", "pytest", "-q", *SELECTIONS.get(case, []), "--samples", str(samples),
                "--junitxml", str(run / "junit.xml")]
        if case == Case.EFFICACY:
            argv = [sys.executable, "-m", "ai_detection", "efficacy-gate", efficacy_request,
                    "--output", str(run / "numeric-gate.json"), "--policy", str(ROOT / "specs/policy.json")]
        env = dict(os.environ, AI_DETECTION_TEST_ARTIFACTS=str(run / "readback"))
        with (run / "stdout.log").open("wb") as stdout, (run / "stderr.log").open("wb") as stderr:
            try:
                code = subprocess.run(argv, cwd=ROOT, env=env, check=False, timeout=300,
                                      stdout=stdout, stderr=stderr).returncode
            except subprocess.TimeoutExpired:
                logger.error("case_timeout case={}", case.value)
                code = 124
        reason = "Named project check executed; inspect independent assertions and JUnit."
    artifact_hashes = {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
                      for path in sorted(run.rglob("*")) if path.is_file()}
    result = Receipt(case=case.value, status="BLOCKED_EXTERNAL" if not executed else
                     ("PASS" if code == 0 else "FAIL"), executed=executed,
                     exit_code=code, argv=argv, unique_run_directory=str(run.relative_to(ROOT)),
                     reason=reason, artifact_sha256=artifact_hashes)
    atomic_json(destination, result.model_dump(mode="json"))
    typer.echo(result.model_dump_json())
    raise typer.Exit(code)


if __name__ == "__main__":
    app()
