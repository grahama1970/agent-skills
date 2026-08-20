#!/usr/bin/env python3
"""Exercise the captcha verify CLI against a real local fixture run."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from types import ModuleType


SKILL_ROOT = Path(__file__).resolve().parents[1]
RUN_SH = SKILL_ROOT / "run.sh"
TEST_RUNTIME = SKILL_ROOT / "tests" / "test_runtime.py"


def _load_test_runtime() -> ModuleType:
    sys.path.insert(0, str(SKILL_ROOT / "src"))
    spec = importlib.util.spec_from_file_location("captcha_test_runtime", TEST_RUNTIME)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not import {TEST_RUNTIME}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run_verify(run_dir: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(RUN_SH), "verify", "--run-dir", str(run_dir), "--json"],
        cwd=SKILL_ROOT,
        text=True,
        capture_output=True,
        timeout=60,
        check=False,
    )


def _json_or_none(value: str) -> object | None:
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return None


def main() -> int:
    runtime_tests = _load_test_runtime()
    base_dir = Path(tempfile.mkdtemp(prefix="captcha-verify-cli-feature-"))
    run_dir = runtime_tests._create_pass_run(base_dir)  # noqa: SLF001 - test fixture factory

    positive = _run_verify(run_dir)
    (run_dir / "request.json").write_text('{"tampered":true}\n', encoding="utf-8")
    negative = _run_verify(run_dir)

    positive_payload = _json_or_none(positive.stdout)
    negative_payload = _json_or_none(negative.stdout)
    success = (
        positive.returncode == 0
        and isinstance(positive_payload, dict)
        and positive_payload.get("status") == "PASS"
        and positive_payload.get("evidence_files_verified") == 12
        and negative.returncode == 2
        and isinstance(negative_payload, dict)
        and negative_payload.get("failure_code") == "receipt_invalid"
    )
    receipt = {
        "schema_version": "captcha.verify_cli_feature_eval.v1",
        "mocked": False,
        "live": False,
        "fixture_backed": True,
        "exercised": "./run.sh verify --run-dir <fixture> --json",
        "proof_boundary": {
            "proves": "verify CLI checks receipt-bound local evidence hashes and rejects tampered evidence",
            "does_not_prove": "live ReCAP model performance or public CAPTCHA solving",
        },
        "run_dir": str(run_dir),
        "positive": {
            "exit_code": positive.returncode,
            "status": positive_payload.get("status") if isinstance(positive_payload, dict) else None,
            "evidence_files_verified": (
                positive_payload.get("evidence_files_verified")
                if isinstance(positive_payload, dict)
                else None
            ),
        },
        "negative": {
            "exit_code": negative.returncode,
            "failure_code": (
                negative_payload.get("failure_code")
                if isinstance(negative_payload, dict)
                else None
            ),
        },
        "success": success,
    }
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0 if success else 1


if __name__ == "__main__":
    raise SystemExit(main())
