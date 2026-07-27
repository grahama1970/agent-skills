#!/usr/bin/env python3
"""Live Dogpile E2E sanity harness.

This is intentionally non-mocked. It runs Dogpile through run.sh, then inspects
the durable partial-results receipt instead of trusting terminal output alone.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import time
from pathlib import Path
from typing import Any


SKILL_DIR = Path(__file__).resolve().parents[1]
DEFAULT_QUERY = "retrieval augmented generation large language models"
CORE_PROVIDERS = ("brave", "brave_questions", "github", "arxiv", "youtube")
DEFAULT_OFF_PROVIDERS = ("perplexity", "readarr", "wayback")


def _utc_stamp() -> str:
    return time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())


def _result_error(result: Any) -> str | None:
    if isinstance(result, str) and result.startswith("Error:"):
        return result[:300]
    if isinstance(result, dict):
        if result.get("error"):
            return str(result["error"])[:300]
        if result.get("skipped"):
            return f"skipped: {result['skipped']}"[:300]
    if isinstance(result, list) and result:
        first = result[0]
        if isinstance(first, dict) and str(first.get("title", "")).startswith("Error "):
            return str(first.get("title", ""))[:300]
        if isinstance(first, dict) and first.get("error"):
            return str(first["error"])[:300]
    return None


def _positive_count(provider: str, result: Any) -> int:
    if provider == "brave" and isinstance(result, dict):
        return len(result.get("web", {}).get("results", []) or result.get("results", []) or [])
    if provider == "brave_questions" and isinstance(result, dict):
        return int(result.get("succeeded") or 0)
    if provider == "github" and isinstance(result, dict):
        return len(result.get("repos", []) or []) + len(result.get("issues", []) or [])
    if provider == "arxiv" and isinstance(result, dict):
        return len(result.get("items", []) or [])
    if provider == "youtube" and isinstance(result, list):
        return sum(1 for item in result if isinstance(item, dict) and item.get("id"))
    return 0


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False))


def main() -> int:
    parser = argparse.ArgumentParser(description="Run live Dogpile E2E sanity checks")
    parser.add_argument("--query", default=DEFAULT_QUERY)
    parser.add_argument("--timeout-s", type=int, default=300)
    parser.add_argument("--out-dir", type=Path, default=SKILL_DIR / "reports" / f"live-e2e-{_utc_stamp()}")
    args = parser.parse_args()

    out_dir = args.out_dir.resolve()
    command = [
        str(SKILL_DIR / "run.sh"),
        "search",
        args.query,
        "--no-interactive",
        "--no-tailor",
    ]

    started = time.time()
    try:
        completed = subprocess.run(
            command,
            cwd=SKILL_DIR,
            text=True,
            capture_output=True,
            timeout=args.timeout_s,
            check=False,
        )
        timed_out = False
    except subprocess.TimeoutExpired as e:
        completed = subprocess.CompletedProcess(command, 124, e.stdout or "", e.stderr or "")
        timed_out = True

    stdout_path = out_dir / "stdout.md"
    stderr_path = out_dir / "stderr.log"
    out_dir.mkdir(parents=True, exist_ok=True)
    stdout_path.write_text(completed.stdout or "")
    stderr_path.write_text(completed.stderr or "")

    partial_path = SKILL_DIR / "dogpile_partial_results.json"
    checks: list[dict[str, Any]] = []
    partial: dict[str, Any] = {}
    if partial_path.exists():
        try:
            partial = json.loads(partial_path.read_text())
            checks.append({"name": "partial_results_json", "status": "passed", "path": str(partial_path)})
        except Exception as e:
            checks.append({"name": "partial_results_json", "status": "failed", "error": str(e), "path": str(partial_path)})
    else:
        checks.append({"name": "partial_results_json", "status": "failed", "error": "missing", "path": str(partial_path)})

    final_report = partial.get("final_report") if isinstance(partial, dict) else None
    checks.append({
        "name": "command_returned",
        "status": "failed" if completed.returncode != 0 or timed_out else "passed",
        "returncode": completed.returncode,
        "timed_out": timed_out,
    })
    checks.append({
        "name": "final_report_present",
        "status": "passed" if isinstance(final_report, str) and "Dogpile Report" in final_report else "failed",
    })
    checks.append({
        "name": "evidence_synthesis_present",
        "status": "passed" if isinstance(final_report, str) and "## Evidence Synthesis" in final_report else "failed",
    })

    stage1 = partial.get("results", {}).get("stage1", {}) if isinstance(partial, dict) else {}
    for provider in CORE_PROVIDERS:
        result = stage1.get(provider)
        err = _result_error(result)
        count = _positive_count(provider, result)
        status = "passed" if result is not None and err is None and count > 0 else "failed"
        checks.append({
            "name": f"provider_{provider}",
            "status": status,
            "positive_count": count,
            "error": err,
        })

    for provider in DEFAULT_OFF_PROVIDERS:
        result = stage1.get(provider)
        skipped = isinstance(result, dict) and bool(result.get("skipped"))
        checks.append({
            "name": f"default_off_{provider}",
            "status": "passed" if skipped else "failed",
            "skipped": result.get("skipped") if isinstance(result, dict) else None,
        })

    failed = [check for check in checks if check["status"] == "failed"]
    receipt = {
        "schema": "dogpile.live_e2e_sanity.v1",
        "mocked": False,
        "live": True,
        "query": args.query,
        "command": command,
        "duration_s": round(time.time() - started, 2),
        "stdout_path": str(stdout_path),
        "stderr_path": str(stderr_path),
        "partial_results_path": str(partial_path),
        "checks": checks,
        "status": "failed" if failed else "passed",
    }
    receipt_path = out_dir / "receipt.json"
    _write_json(receipt_path, receipt)

    print(json.dumps({
        "status": receipt["status"],
        "receipt_path": str(receipt_path),
        "failed": failed,
    }, indent=2))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
