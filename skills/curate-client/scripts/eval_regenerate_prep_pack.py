#!/usr/bin/env python3
"""Prove curate-client can regenerate a missing Live Evidence prep pack.

This runs the real curate-client CLI with a missing configured prep-pack path,
then validates and loads the generated pack through Live Evidence's own commands.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

CHECKS: dict[str, bool] = {}
DETAILS: dict[str, Any] = {}
FAILURES: list[str] = []


def check(name: str, ok: bool, detail: Any = None) -> None:
    CHECKS[name] = bool(ok)
    DETAILS[name] = detail
    print(f"{name}: {'PASS' if ok else 'FAIL'}{f' ({detail})' if detail is not None else ''}")
    if not ok:
        FAILURES.append(name)


def clean_env() -> dict[str, str]:
    env = dict(os.environ)
    env.pop("UV_PROJECT_ENVIRONMENT", None)
    env.pop("VIRTUAL_ENV", None)
    if env.get("MEMORY_SERVICE_URL", "").startswith("unix://"):
        env["MEMORY_SERVICE_URL"] = "http://127.0.0.1:8601"
    return env


def parse_json(stdout: str) -> dict[str, Any]:
    start = stdout.find("{")
    if start < 0:
        raise ValueError("stdout did not contain JSON")
    return json.loads(stdout[start:])


def run(argv: list[str], *, cwd: Path, timeout_s: int) -> tuple[subprocess.CompletedProcess[str], dict[str, Any] | None]:
    proc = subprocess.run(argv, cwd=cwd, env=clean_env(), capture_output=True, text=True, timeout=timeout_s)
    payload = None
    if proc.stdout.strip():
        try:
            payload = parse_json(proc.stdout)
        except Exception:
            payload = None
    return proc, payload


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="/tmp/curate-client-regenerate-current.json")
    parser.add_argument("--memory-url", default="http://127.0.0.1:8601")
    args = parser.parse_args()

    skill_root = Path(__file__).resolve().parents[1]
    repo_root = skill_root.parents[1]
    live_root = repo_root / "skills" / "live-evidence"
    output = Path(args.output).expanduser().resolve()
    memory_url = args.memory_url if args.memory_url.startswith(("http://", "https://")) else "http://127.0.0.1:8601"

    with tempfile.TemporaryDirectory(prefix="curate-client-regenerate-") as tmp:
        tmpdir = Path(tmp)
        pack_path = tmpdir / "generated-drivewealth-prep-pack.json"
        config_path = tmpdir / "drivewealth-regenerate.yaml"
        config_path.write_text(
            "\n".join([
                "client: drivewealth",
                "kb_root: /home/graham/workspace/experiments/dw-openapi",
                "openapi_specs:",
                "  - /home/graham/workspace/experiments/dw-openapi/dist/InvestingAPI.yaml",
                "terraform_repos:",
                "  - /home/graham/workspace/experiments/dwt-terraform-aws-helm-release",
                "probes:",
                "  - what fields does an order object have",
                "  - deposits endpoints",
                f"memory_daemon: {memory_url}",
                f"live_evidence_prep_pack: {pack_path}",
                "anchor_terms:",
                "  - receipts",
                "  - orchestration",
                "  - observability",
                "  - evals",
                "  - compliance",
                "  - retrieval",
                "  - fail-closed",
                "",
            ]),
            encoding="utf-8",
        )

        prep_proc, prep_json = run(
            [str(skill_root / "run.sh"), "prep-pack", "--config", str(config_path)],
            cwd=skill_root,
            timeout_s=180,
        )
        validate_path = tmpdir / "validate.json"
        validate_proc, validate_json = run(
            [str(live_root / "run.sh"), "eval-prep-pack", "--pack", str(pack_path), "--output", str(validate_path)],
            cwd=live_root,
            timeout_s=180,
        )
        if validate_path.exists():
            validate_json = json.loads(validate_path.read_text(encoding="utf-8"))
        load_path = tmpdir / "load.json"
        load_proc, load_json = run(
            [
                str(live_root / "run.sh"),
                "load-prep-pack",
                "--pack",
                str(pack_path),
                "--skip-briefing",
                "--memory-url",
                memory_url,
                "--output",
                str(load_path),
            ],
            cwd=live_root,
            timeout_s=180,
        )
        if load_path.exists():
            load_json = json.loads(load_path.read_text(encoding="utf-8"))

        pack = json.loads(pack_path.read_text(encoding="utf-8")) if pack_path.exists() else {}
        receipt: dict[str, Any] = {
            "schema": "curate_client.regenerate_prep_pack_eval.v1",
            "status": "PASS",
            "created_at": datetime.now(UTC).isoformat(),
            "mocked": False,
            "live": True,
            "config_path": str(config_path),
            "generated_pack_path": str(pack_path),
            "commands": {
                "prep_pack": {"exit_code": prep_proc.returncode, "stdout_tail": prep_proc.stdout[-2000:], "stderr_tail": prep_proc.stderr[-2000:], "json": prep_json},
                "validate": {"exit_code": validate_proc.returncode, "stdout_tail": validate_proc.stdout[-2000:], "stderr_tail": validate_proc.stderr[-2000:], "json": validate_json},
                "load": {"exit_code": load_proc.returncode, "stdout_tail": load_proc.stdout[-2000:], "stderr_tail": load_proc.stderr[-2000:], "json": load_json},
            },
            "pack_summary": {
                "schema": pack.get("schema"),
                "pack_id": pack.get("pack_id"),
                "producer": pack.get("producer"),
                "question_oracle_count": len(pack.get("question_oracles") or []),
                "briefing_point_count": len((pack.get("briefing_pack") or {}).get("points") or []),
            },
            "checks": CHECKS,
            "details": DETAILS,
        }
        check("missing prep-pack path regenerated", prep_proc.returncode == 0 and bool(prep_json and prep_json.get("generated") is True) and pack_path.is_file(), {"exit_code": prep_proc.returncode, "generated": (prep_json or {}).get("generated")})
        check("generated prep pack has live-evidence schema", pack.get("schema") == "live_evidence.prep_pack.v1", pack.get("schema"))
        check("generated prep pack has producer metadata", bool((pack.get("producer") or {}).get("generated") is True), pack.get("producer"))
        check("generated prep pack validates through live-evidence", validate_proc.returncode == 0 and bool(validate_json and validate_json.get("status") == "PASS"), validate_json)
        check("generated prep pack oracle recall loads", load_proc.returncode == 0 and bool(load_json and load_json.get("status") == "PASS" and load_json.get("oracle_recall", {}).get("ok") is True), load_json)
        check("generated prep pack carries at least two question oracles", len(pack.get("question_oracles") or []) >= 2, len(pack.get("question_oracles") or []))

        receipt["checks"] = CHECKS
        receipt["details"] = DETAILS
        receipt["failures"] = list(FAILURES)
        receipt["status"] = "PASS" if not FAILURES else "FAIL"
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(f"curate-client regenerate receipt: {output}")
        print(f"curate-client regenerate prep-pack: {receipt['status']}")
        return 0 if receipt["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
