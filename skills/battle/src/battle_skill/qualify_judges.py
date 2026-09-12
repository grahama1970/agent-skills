"""Judge qualification: control pairs prove the judges detect what they claim.

battle.judge_qualification.v1 manifest:
  controls: [{id, judge: security|functional, observations_dir, policy,
              expected_status: PASS|FAIL, expected_finding_substring (optional)}]

Each control points at RETAINED observations (an input corpus and an output
tree); the named judge runs against them directly — no target Docker
execution. Qualification PASSES only if every control's actual judge status
matches its expected status and, when an expected_finding_substring is
declared, that substring appears in the violations.

The receipt binds the judge file sha256s actually executed, so a cached
qualification is invalid after any judge change (compare digests).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import time
from pathlib import Path
from typing import Any

from .invariant_judge import run_judge

SCHEMA = "battle.judge_qualification.v1"


def _sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def qualify(manifest_path: Path, judge_paths: dict[str, str], out: Path) -> dict[str, Any]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("schema") != SCHEMA:
        raise ValueError(f"qualification manifest schema must be {SCHEMA}")
    receipt: dict[str, Any] = {
        "schema": f"{SCHEMA}.receipt",
        "manifest": str(manifest_path),
        "manifest_sha256": _sha256(manifest_path),
        "judge_sha256": {name: _sha256(Path(p)) for name, p in judge_paths.items()},
        "controls": [],
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    failures = 0
    for control in manifest.get("controls", []):
        judge_name = control["judge"]
        judge_path = judge_paths.get(judge_name)
        if judge_path is None:
            receipt["controls"].append({"id": control["id"], "status": "ERROR",
                                        "error": f"no judge path supplied for {judge_name!r}"})
            failures += 1
            continue
        params = dict(control.get("params") or {})
        params.setdefault("policy", str(control["policy"]))
        params.setdefault("input_dir", str(control["observations_dir"]))
        result = run_judge(judge_path, str(control["observations_dir"]), params)
        actual = "PASS" if result.passed else "FAIL"
        expected = control["expected_status"]
        ok = actual == expected
        finding = control.get("expected_finding_substring")
        if ok and finding:
            ok = any(finding in v for v in result.violations)
        if not ok:
            failures += 1
        receipt["controls"].append({
            "id": control["id"], "judge": judge_name,
            "expected_status": expected, "actual_status": actual,
            "expected_finding_substring": finding,
            "violations": result.violations[:8],
            "status": "PASS" if ok else "FAIL",
        })
    receipt["passed"] = failures == 0 and bool(manifest.get("controls"))
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return receipt


def _cli(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="Qualify judges against retained control pairs")
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--security-judge", required=True)
    ap.add_argument("--functional-judge", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)
    receipt = qualify(Path(args.manifest),
                      {"security": args.security_judge, "functional": args.functional_judge},
                      Path(args.out))
    print(json.dumps({"status": "PASS" if receipt["passed"] else "FAIL",
                      "receipt": str(Path(args.out))}, indent=2))
    return 0 if receipt["passed"] else 1


if __name__ == "__main__":
    import sys
    raise SystemExit(_cli(sys.argv[1:]))
