"""Evaluate employer ATS parser-limit receipts against live nightly artifacts."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

CANONICAL_LIVE_RUN = Path(
    "/home/graham/workspace/experiments/agent-skills/"
    "skills/monitor-opportunities/local/nightly/latest"
)
NAMED_TARGETS = {
    "sierra": "ashby",
    "harvey": "ashby",
    "elevenlabs": "ashby",
    "decagon": "ashby",
    "onetrust": "greenhouse",
}


def _default_run() -> Path:
    env = os.environ.get("MONITOR_OPPORTUNITIES_LIVE_RUN")
    if env:
        return Path(env)
    local_latest = Path(__file__).resolve().parents[1] / "local" / "nightly" / "latest"
    if (local_latest / "discovery" / "source-receipts.jsonl").exists():
        return local_latest
    return CANONICAL_LIVE_RUN


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _is_size_only_failure(receipt: dict[str, Any]) -> bool:
    limitations = " | ".join(str(item) for item in receipt.get("limitations") or [])
    return (
        receipt.get("result_status") == "INVALID_RESPONSE"
        and (
            receipt.get("parser_result") == "SIZE_LIMIT"
            or "Response exceeded bounded parser limit" in limitations
        )
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", type=Path, default=_default_run())
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    receipts_path = args.run / "discovery" / "source-receipts.jsonl"
    receipts = _read_jsonl(receipts_path)
    named: dict[str, dict[str, Any]] = {}
    for receipt in receipts:
        target = str(receipt.get("target") or "").strip().lower()
        provider = str(receipt.get("provider") or "").strip().lower()
        expected_provider = NAMED_TARGETS.get(target)
        if expected_provider and provider == expected_provider:
            named[target] = receipt

    missing = sorted(set(NAMED_TARGETS) - set(named))
    size_only_failures = [
        target for target, receipt in sorted(named.items())
        if _is_size_only_failure(receipt)
    ]
    readbacks = {
        target: {
            "provider": receipt.get("provider"),
            "target": receipt.get("target"),
            "result_status": receipt.get("result_status"),
            "parser_result": receipt.get("parser_result"),
            "response_status": receipt.get("response_status"),
            "response_bytes": receipt.get("response_bytes"),
            "receipt_id": receipt.get("receipt_id"),
            "limitations": receipt.get("limitations"),
        }
        for target, receipt in sorted(named.items())
    }
    invariant_pass = not missing and not size_only_failures
    result = {
        "schema": "monitor_opportunities.eval.employer_ats_parser_limit.v1",
        "live": True,
        "mocked": False,
        "source_run": str(args.run),
        "receipt_artifact": str(receipts_path),
        "named_target_count": len(named),
        "missing_targets": missing,
        "size_only_failures": size_only_failures,
        "readbacks": readbacks,
        "invariant_pass": invariant_pass,
    }

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n",
                               encoding="utf-8")

    if not invariant_pass:
        print(json.dumps(result, indent=2, sort_keys=True))
        return 1

    print(
        "EMPLOYER_ATS_PARSER_LIMIT_OK "
        f"named={len(named)} "
        f"size_only_failures={len(size_only_failures)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
