#!/usr/bin/env python3
"""Regression guard for scheduler-worktree latest publication readback."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any


SKILL_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = SKILL_DIR.parents[1]


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("/tmp/monitor-opportunities-status-scheduler-latest-proof.json"),
    )
    args = parser.parse_args()

    with TemporaryDirectory(prefix="monitor-opportunities-scheduler-status-") as tmp:
        root = Path(tmp)
        scheduler_data = root / "scheduler"
        cron_repo = root / "cron-worktree"
        latest = cron_repo / "skills" / "monitor-opportunities" / "local" / "nightly" / "latest"
        latest.mkdir(parents=True)
        (latest / "report").mkdir()
        _write_json(
            scheduler_data / "receipts" / "monitor-opportunities-nightly-receipt.json",
            {
                "schema": "monitor_opportunities.scheduler_receipt.v1",
                "status": "PASS",
                "mode": "PROMOTED_STAGE_0",
                "cron": "0 2 * * *",
                "workdir": str(cron_repo),
                "readback": {
                    "name": "monitor-opportunities-nightly",
                    "cron": "0 2 * * *",
                    "workdir": str(cron_repo),
                    "enabled": True,
                },
            },
        )
        _write_json(
            latest / "nightly-receipt.json",
            {
                "schema": "monitor_opportunities.nightly_receipt.v1",
                "status": "PASS",
                "mode": "PROMOTED_STAGE_0",
                "mocked": False,
                "live": True,
                "external_effects": False,
                "report_acceptance_status": "PASS",
                "receipt_consistency_status": "PASS",
            },
        )
        _write_json(
            latest / "run-receipt.json",
            {
                "schema": "monitor_opportunities.run_receipt.v1",
                "run_id": "mo_eval_scheduler_latest",
                "terminal_state": "AWAITING_HUMAN",
                "completed_at": "2026-08-26T06:06:50Z",
            },
        )
        (latest / "report" / "index.html").write_text("<h1>report</h1>\n", encoding="utf-8")

        env = {**os.environ, "SCHEDULER_DATA_DIR": str(scheduler_data)}
        result = subprocess.run(
            [str(SKILL_DIR / "run.sh"), "status", "--json"],
            cwd=REPO_ROOT,
            env=env,
            check=False,
            text=True,
            capture_output=True,
        )
        if result.returncode != 0:
            sys.stderr.write(result.stderr)
            return result.returncode
        payload = json.loads(result.stdout)
        latest_payload = payload["scheduler_latest"]
        assert latest_payload["status"] == "PASS", latest_payload
        assert latest_payload["run_id"] == "mo_eval_scheduler_latest", latest_payload
        assert latest_payload["terminal_state"] == "AWAITING_HUMAN", latest_payload
        assert latest_payload["latest_path"] == str(latest), latest_payload
        assert latest_payload["nightly_receipt"] == str(latest / "nightly-receipt.json"), latest_payload
        assert latest_payload["report_html"] == str(latest / "report" / "index.html"), latest_payload
        proof = {
            "schema": "monitor_opportunities.scheduler_latest_status_eval.v1",
            "status": "PASS",
            "run_id": latest_payload["run_id"],
            "terminal_state": latest_payload["terminal_state"],
            "scheduler_latest_status": latest_payload["status"],
            "live": latest_payload["live"],
            "mocked": latest_payload["mocked"],
            "external_effects": latest_payload["external_effects"],
            "latest_path": latest_payload["latest_path"],
            "nightly_receipt": latest_payload["nightly_receipt"],
            "report_html": latest_payload["report_html"],
        }
        _write_json(args.out, proof)
    print(f"SCHEDULER_LATEST_STATUS_OK proof={args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
