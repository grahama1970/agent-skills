"""Judge qualification: control pairs prove the judges detect what they claim.

battle.judge_qualification.v1 manifest:
  controls: [{id, judge: security|functional, observations_dir, policy,
              expected_status: PASS|FAIL, expected_finding_substring (optional)}]

Each control points at RETAINED observations (an input corpus and an output
tree); the named judge runs against them directly — no target Docker
execution. Qualification PASSES only if every control's actual judge status
matches its expected status and, when an expected_finding_substring is
declared, that substring appears in the violations.

The receipt binds the judge file sha256s actually executed, the evaluator image,
the qualification-suite digest, and the interpretation configuration, so a
cached qualification is invalid after any judge/configuration change.
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


def _canonical_digest(value: Any) -> str:
    return "sha256:" + hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def qualification_key(
    *,
    evaluator_image: str,
    qualification_suite_sha256: str,
    judge_sha256: dict[str, str],
    interpretation_config: dict[str, Any],
) -> str:
    return _canonical_digest({
        "evaluator_image": evaluator_image,
        "qualification_suite_sha256": qualification_suite_sha256,
        "judge_sha256": judge_sha256,
        "interpretation_config": interpretation_config,
    })


def qualify(
    manifest_path: Path,
    judge_paths: dict[str, str],
    out: Path,
    *,
    evaluator_image: str | None = None,
    interpretation_config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("schema") != SCHEMA:
        raise ValueError(f"qualification manifest schema must be {SCHEMA}")
    suite_sha256 = _sha256(manifest_path)
    evaluator_image = evaluator_image or manifest.get("evaluator_image") or "UNSPECIFIED"
    interpretation_config = interpretation_config if interpretation_config is not None else dict(manifest.get("interpretation_config") or {})
    judge_sha256 = {name: _sha256(Path(p)) for name, p in judge_paths.items()}
    receipt: dict[str, Any] = {
        "schema": f"{SCHEMA}.receipt",
        "manifest": str(manifest_path),
        "manifest_sha256": suite_sha256,
        "qualification_suite_sha256": suite_sha256,
        "evaluator_image": evaluator_image,
        "interpretation_config": interpretation_config,
        "interpretation_config_sha256": _canonical_digest(interpretation_config),
        "judge_sha256": judge_sha256,
        "qualification_key": qualification_key(
            evaluator_image=evaluator_image,
            qualification_suite_sha256=suite_sha256,
            judge_sha256=judge_sha256,
            interpretation_config=interpretation_config,
        ),
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
        finding = control.get("expected_finding_substring")
        judge_error = any(v.startswith("judge error:") or "malformed result" in v for v in result.violations)
        ok = actual == expected and not judge_error
        if ok and finding:
            ok = any(finding in v for v in result.violations)
        if not ok:
            failures += 1
        receipt["controls"].append({
            "id": control["id"], "judge": judge_name,
            "expected_status": expected, "actual_status": actual,
            "expected_finding_substring": finding,
            "violations": result.violations[:8],
            "judge_error_as_witness": judge_error,
            "status": "PASS" if ok else "FAIL",
        })
    receipt["passed"] = failures == 0 and bool(manifest.get("controls"))
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return receipt


def validate_qualification_receipt(
    receipt_path: str | Path,
    *,
    judge_paths: dict[str, str],
    evaluator_image: str,
    qualification_suite_sha256: str,
    interpretation_config: dict[str, Any],
) -> dict[str, Any]:
    """Validate that a receipt qualifies this exact Judge configuration."""
    problems: list[str] = []
    try:
        receipt = json.loads(Path(receipt_path).read_text(encoding="utf-8"))
    except Exception as exc:
        return {"schema": f"{SCHEMA}.validation", "status": "BLOCKED", "problems": [f"qualification-receipt-unreadable:{exc}"]}
    if receipt.get("schema") != f"{SCHEMA}.receipt":
        problems.append("qualification-receipt-schema-invalid")
    if receipt.get("passed") is not True:
        problems.append("qualification-receipt-not-passed")
    expected_judges = {name: _sha256(Path(path)) for name, path in judge_paths.items()}
    if receipt.get("judge_sha256") != expected_judges:
        problems.append("qualification-judge-digest-mismatch")
    if receipt.get("evaluator_image") != evaluator_image:
        problems.append("qualification-evaluator-image-mismatch")
    if receipt.get("qualification_suite_sha256") != qualification_suite_sha256:
        problems.append("qualification-suite-digest-mismatch")
    if receipt.get("interpretation_config") != interpretation_config:
        problems.append("qualification-interpretation-config-mismatch")
    expected_key = qualification_key(
        evaluator_image=evaluator_image,
        qualification_suite_sha256=qualification_suite_sha256,
        judge_sha256=expected_judges,
        interpretation_config=interpretation_config,
    )
    if receipt.get("qualification_key") != expected_key:
        problems.append("qualification-key-mismatch")
    failed_controls = [c.get("id") for c in receipt.get("controls", []) if c.get("status") != "PASS"]
    if failed_controls:
        problems.append(f"qualification-controls-failed:{failed_controls}")
    return {
        "schema": f"{SCHEMA}.validation",
        "status": "PASS" if not problems else "BLOCKED",
        "receipt_path": str(receipt_path),
        "qualification_key": expected_key,
        "evaluator_image": evaluator_image,
        "qualification_suite_sha256": qualification_suite_sha256,
        "interpretation_config_sha256": _canonical_digest(interpretation_config),
        "problems": problems,
    }


def _cli(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="Qualify judges against retained control pairs")
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--security-judge", required=True)
    ap.add_argument("--functional-judge", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--evaluator-image", default=None)
    ap.add_argument("--interpretation-config-json", default=None)
    args = ap.parse_args(argv)
    receipt = qualify(Path(args.manifest),
                      {"security": args.security_judge, "functional": args.functional_judge},
                      Path(args.out),
                      evaluator_image=args.evaluator_image,
                      interpretation_config=(json.loads(args.interpretation_config_json)
                                             if args.interpretation_config_json else None))
    print(json.dumps({"status": "PASS" if receipt["passed"] else "FAIL",
                      "receipt": str(Path(args.out))}, indent=2))
    return 0 if receipt["passed"] else 1


if __name__ == "__main__":
    import sys
    raise SystemExit(_cli(sys.argv[1:]))
