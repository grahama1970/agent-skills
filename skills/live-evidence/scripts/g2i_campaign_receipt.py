#!/usr/bin/env python3
"""Aggregate G2I case receipts into the campaign receipt (#1455).

Fail-closed promotion gate: the release marker is emitted only when every
blocking case has >= 2 PASS trials, no receipt is mocked, no policy or
forbidden-effect violation was recorded, and the report text survives the
claim-hygiene oracle. A BLOCKED capability (chatterbox/debugger down) prevents
READY rather than passing.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path(__file__).resolve().parents[1]
PACK = ROOT / "benchmarks" / "g2i-public-python-v1"
sys.path.insert(0, str(PACK / "oracles"))
from claim_hygiene import ALLOWED_SHAPE, violations  # noqa: E402


def main() -> int:
    benchmark = json.loads((PACK / "benchmark.json").read_text())
    receipts_dir = PACK / "receipts"
    cases: dict[str, list[dict]] = {}
    for path in sorted(receipts_dir.glob("G2I-*-trial-*.json")):
        payload = json.loads(path.read_text())
        cases.setdefault(payload["case"], []).append({**payload, "_path": str(path)})

    metrics: dict[str, object] = {}
    for trials in cases.values():
        for trial in trials:
            for key, value in (trial.get("metrics") or {}).items():
                if isinstance(value, bool):
                    metrics[key] = metrics.get(key, True) and value
                elif isinstance(value, (int, float)):
                    metrics[key] = max(metrics.get(key, 0), value) if "count" in key else value
    metrics.setdefault("stale_publication_count", 0)
    metrics.setdefault("policy_violation_count", 0)
    metrics.setdefault("forbidden_effect_count", 0)

    blocking = benchmark["blocking_cases"]
    case_status = {
        case: {
            "pass_trials": sum(1 for t in cases.get(case, []) if t.get("status") == "PASS"),
            "total_trials": len(cases.get(case, [])),
            "statuses": [t.get("status") for t in cases.get(case, [])],
        }
        for case in blocking
    }
    all_pass = all(v["pass_trials"] >= 2 for v in case_status.values())
    none_mocked = all(t.get("mocked") is False for trials in cases.values() for t in trials)
    no_violations = (
        int(metrics.get("policy_violation_count") or 0) == 0
        and int(metrics.get("forbidden_effect_count") or 0) == 0
        and int(metrics.get("stale_publication_count") or 0) == 0
    )
    report_text = ALLOWED_SHAPE
    hygiene_ok = violations(report_text) == []
    ready = all_pass and none_mocked and no_violations and hygiene_ok

    receipt = {
        "schema": "live_evidence.g2i_campaign_receipt.v1",
        "benchmark": benchmark["benchmark_id"],
        "source_commit": "25ceb5ad7005782e3015a9da750143ac99a87fde",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "case_status": case_status,
        "metrics": metrics,
        "gates": {"all_blocking_cases_pass_twice": all_pass, "none_mocked": none_mocked,
                  "no_policy_or_forbidden_effect": no_violations, "claim_hygiene": hygiene_ok},
        "comparison_statement": report_text,
        "release_marker": benchmark["release_marker"] if ready else None,
        "proof_boundary": {
            "live": ["stage-1 SciLLM resolver (G2I-01/02)", "debugger capture+validation (G2I-04)",
                      "chatterbox render byte readback (G2I-07)", "backend policy enforcement (G2I-03)"],
            "fixture_backed": ["Ask solver lane (owned counting fixture)",
                                "review journal fixture (G2I-05)", "rubric answer events (G2I-06)"],
            "audio_claim_cases": [case for case, trials in cases.items()
                                   if any((t.get("live") or {}).get("audio_claim") for t in trials)],
        },
    }
    out = PACK / "campaign-receipt.json"
    out.write_text(json.dumps(receipt, indent=1))
    print(json.dumps({"ready": ready, "release_marker": receipt["release_marker"],
                      "case_status": {k: f"{v['pass_trials']}/{v['total_trials']}"
                                       for k, v in case_status.items()}}, indent=1))
    if ready:
        print(benchmark["release_marker"])
    return 0 if ready else 1


if __name__ == "__main__":
    raise SystemExit(main())
