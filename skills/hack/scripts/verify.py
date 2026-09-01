#!/usr/bin/env python3
"""Non-destructive verifier for the Hack skill's safety gates."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SKILL_DIR = Path(__file__).resolve().parents[1]
HACK = [str(SKILL_DIR / "run.sh")]


def run_step(name: str, argv: list[str], expect_code: int | None = 0) -> dict[str, Any]:
    started = datetime.now(timezone.utc).isoformat()
    try:
        proc = subprocess.run(argv, cwd=SKILL_DIR, text=True, capture_output=True, timeout=30)
        returncode = proc.returncode
        stdout = proc.stdout
        stderr = proc.stderr
    except subprocess.TimeoutExpired as exc:
        returncode = -1
        stdout = exc.stdout or ""
        stderr = (exc.stderr or "") + "\nTIMEOUT after 30s"
    ok = returncode == expect_code if expect_code is not None else returncode != 0
    return {
        "name": name,
        "argv": argv,
        "expected_returncode": expect_code,
        "returncode": returncode,
        "ok": ok,
        "started_at": started,
        "stdout_tail": stdout[-2000:],
        "stderr_tail": stderr[-2000:],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args(argv)

    artifact_root = args.out or Path("/mnt/storage12tb/artifacts/agent-skills/hack/verify") / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    artifact_root.mkdir(parents=True, exist_ok=True)

    steps = [
        run_step(
            "authorization-valid",
            HACK + [
                "authorization-preflight",
                "--authorization-manifest", "fixtures/authorization/valid-local.json",
                "--target", "fixture-target@sha256:fixture",
                "--action", "session-audit",
                "--receipt-out", str(artifact_root / "authorization-valid.json"),
            ],
            0,
        ),
        run_step(
            "authorization-wrong-target-fails-closed",
            HACK + [
                "authorization-preflight",
                "--authorization-manifest", "fixtures/authorization/valid-local.json",
                "--target", "wrong-target",
                "--action", "session-audit",
                "--receipt-out", str(artifact_root / "authorization-wrong-target.json"),
            ],
            2,
        ),
        run_step(
            "scan-request-valid",
            HACK + [
                "validate-scan-request", "fixtures/hack-scan-request/valid.json",
                "--expected-target", "fixture-target@sha256:fixture",
                "--receipt-out", str(artifact_root / "scan-request-valid.json"),
            ],
            0,
        ),
        run_step(
            "compose-policy-safe",
            HACK + [
                "compose-policy", "fixtures/compose-policy/safe/docker-compose.yml",
                "--authorization-manifest", "fixtures/authorization/valid-local.json",
                "--out", str(artifact_root / "compose-safe.yml"),
                "--receipt-out", str(artifact_root / "compose-policy-safe.json"),
            ],
            0,
        ),
        run_step(
            "compose-policy-privileged-fails-closed",
            HACK + [
                "compose-policy", "fixtures/compose-policy/malicious/privileged.yml",
                "--authorization-manifest", "fixtures/authorization/valid-local.json",
                "--out", str(artifact_root / "compose-privileged.yml"),
                "--receipt-out", str(artifact_root / "compose-policy-privileged.json"),
            ],
            1,
        ),
    ]
    status = "PASS" if all(step["ok"] for step in steps) else "FAIL"
    receipt = {
        "schema": "hack.verify_receipt.v1",
        "status": status,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "artifact_root": str(artifact_root),
        "live": "docker_compose_config",
        "mocked": False,
        "non_claims": [
            "does_not_run_network_scans",
            "does_not_start_target_runtime",
            "does_not_confirm_exploitability",
        ],
        "steps": steps,
    }
    receipt_path = artifact_root / "verify-receipt.json"
    receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True))
    print(json.dumps({"schema": "hack.verify_summary.v1", "status": status, "receipt": str(receipt_path)}))
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
