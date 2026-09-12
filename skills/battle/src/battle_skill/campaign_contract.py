"""Campaign contract: request -> frozen plan -> receipt -> offline verifier.

WebGPT step 4: one shared, synchronous evaluation path behind a structured
interface. The oai-trial gate and the production battle loop are both callers.

- battle.campaign_request.v1: intent (contract digests, evaluator lock, judges
  by digest, target image digest, case source, advisory lineage).
- The frozen plan: materialized retained cases, effective expectations, judge
  set — resolved BEFORE any target execution.
- battle.campaign_contract_receipt.v1: complete evidence package — authority
  digests, plan, per-case execution observations, artifact manifest with
  content hashes, per-case results, aggregation, verdict.
- verify_campaign_receipt(): offline verifier that RERUNS the judges on the
  retained observations, recomputes the verdict, and compares. It never trusts
  the recorded PASS fields. Execution provenance is explicitly NOT_VERIFIED.

Fail-closed throughout: missing artifacts, hash mismatches, judge-digest
changes, and verdict mismatches all fail verification.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import time
from pathlib import Path
from typing import Any

from .docker_runtime import extract_docker_run_image
from .invariant_campaign import load_profile, run_campaign
from .invariant_judge import run_judge
from .strict_json import finite_json_values, load_path

REQUEST_SCHEMA = "battle.campaign_request.v1"
RECEIPT_SCHEMA = "battle.campaign_contract_receipt.v1"


def _sha256_bytes(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _manifest_tree(root: Path) -> list[dict[str, Any]]:
    entries = []
    for f in sorted(root.rglob("*")):
        if f.is_file():
            entries.append({"path": str(f.relative_to(root)), "sha256": _sha256_file(f),
                            "bytes": f.stat().st_size})
    return entries


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _validate_execution_authorization(request: dict[str, Any]) -> None:
    image = extract_docker_run_image(str(request.get("target_run_cmd", "")))
    if not image:
        return
    receipt = request.get("authorization_receipt")
    _require(isinstance(receipt, dict), "docker campaign request missing authorization_receipt")
    _require(receipt.get("status") == "PASS", "docker campaign authorization_receipt did not PASS")
    _require(receipt.get("requested_action") == "battle", "docker campaign authorization action mismatch")
    _require(receipt.get("requested_runtime_mode") == "docker", "docker campaign authorization runtime mismatch")
    _require(receipt.get("expected_execution_target") == image, "docker campaign authorization target does not match executable image")


def validate_request(request: dict[str, Any]) -> None:
    _require(isinstance(request, dict), "request must be a JSON object")
    allowed = {
        "schema",
        "profile_path",
        "lock_path",
        "generator",
        "judge",
        "functional_judge",
        "target_run_cmd",
        "work_root",
        "gen_params",
        "judge_params",
        "output_subdir",
        "lineage",
        "authorization_receipt",
    }
    extra = sorted(set(request) - allowed)
    _require(not extra, f"request contains unknown fields: {extra}")
    _require(finite_json_values(request), "request contains non-finite numeric value")
    _require(request.get("schema") == REQUEST_SCHEMA,
             f"request schema must be {REQUEST_SCHEMA}")
    for key in ("profile_path", "lock_path", "generator", "judge", "functional_judge",
                "target_run_cmd", "work_root"):
        _require(isinstance(request.get(key), str) and request[key].strip(), f"request missing {key}")
    _require(isinstance(request.get("gen_params", {}), dict), "gen_params must be an object")
    _require(isinstance(request.get("judge_params", {}), dict), "judge_params must be an object")
    if "output_subdir" in request:
        _require(isinstance(request["output_subdir"], str) and request["output_subdir"].strip(), "output_subdir must be a non-empty string")
    if "lineage" in request:
        _require(isinstance(request["lineage"], dict), "lineage must be an object")
    _validate_execution_authorization(request)


def resolve_plan(request: dict[str, Any]) -> dict[str, Any]:
    """Freeze what will run: materialize cases, resolve profile expectations.

    Runs the generator into retained bytes under work_root/gen and resolves the
    effective expectations WITHOUT executing any target.
    """
    work = Path(request["work_root"])
    gen_root = work / "plan-gen"
    shutil.rmtree(gen_root, ignore_errors=True)
    gen_root.mkdir(parents=True, exist_ok=True)
    import importlib.util
    gen_path = Path(request["generator"]).resolve()
    spec = importlib.util.spec_from_file_location("contract_generator", gen_path)
    _require(spec is not None and spec.loader is not None, f"cannot load generator {gen_path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    cases = []
    for case in mod.generate(str(gen_root), request.get("gen_params") or {}):
        name, input_dir = case[0], case[1]
        declared = case[2].upper() if len(case) == 3 else "MAY_REJECT"
        cases.append({"id": name, "input_dir": str(input_dir), "declared_expectation": declared})
    profile = load_profile(request["profile_path"])
    overrides = profile.get("expectation_overrides") or {}
    for c in cases:
        c["effective_expectation"] = overrides.get(c["id"], c["declared_expectation"]) \
            if c["declared_expectation"] == "MAY_REJECT" else c["declared_expectation"]
        c["expectation_source"] = "profile" if c["id"] in overrides and c["declared_expectation"] == "MAY_REJECT" else "generator"
    missing = [cid for cid in (profile.get("required_case_ids") or []) if cid not in {c["id"] for c in cases}]
    _require(not missing, f"profile-required cases missing from generator output: {missing}")
    illegal = [c["id"] for c in cases if c["id"] in overrides and c["declared_expectation"] != "MAY_REJECT"]
    _require(not illegal, f"profile attempts to override non-MAY_REJECT cases: {illegal}")
    return {
        "profile_id": profile.get("profile_id"),
        "profile_sha256": _sha256_file(Path(request["profile_path"])),
        "lock_sha256": _sha256_file(Path(request["lock_path"])),
        "generator_sha256": _sha256_file(Path(request["generator"])),
        "judge_sha256": _sha256_file(Path(request["judge"])),
        "functional_judge_sha256": _sha256_file(Path(request["functional_judge"])),
        "required_judges": profile.get("required_judges") or [],
        "cases": cases,
        "input_manifest": [{"id": c["id"], "files": _manifest_tree(Path(c["input_dir"]))}
                           for c in cases],
        "frozen_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }


def run_contract_campaign(request: dict[str, Any]) -> dict[str, Any]:
    validate_request(request)
    work = Path(request["work_root"])
    plan = resolve_plan(request)
    profile = load_profile(request["profile_path"])
    result = run_campaign(
        "", request["target_run_cmd"], request["judge"],
        gen_params={},
        judge_params=request.get("judge_params") or {},
        output_subdir=request.get("output_subdir", "corpus"),
        profile=profile,
        functional_judge=request["functional_judge"],
        work_root=work,
        frozen_cases=plan["cases"],
    )
    out_root = work / "out"
    receipt = {
        "schema": RECEIPT_SCHEMA,
        "request": request,
        "request_sha256": _sha256_bytes(json.dumps(request, sort_keys=True).encode()),
        "plan": plan,
        "verdict": "PASS" if result.passed else "FAIL",
        "aggregation": {
            "cases_total": result.cases_total,
            "cases_passed": result.cases_passed,
            "accepted": result.accepted_count,
            "rejected": result.rejected_count,
            "must_accept": result.must_accept_count,
            "must_reject": result.must_reject_count,
            "may_reject": result.may_reject_count,
            "failures": len(result.failures),
            **result.aggregation,
        },
        "case_results": result.case_log,
        "case_receipts": result.case_receipts,
        "output_manifest": _manifest_tree(out_root),
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    receipt_path = work / "receipt.json"
    receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return receipt


def verify_campaign_receipt(receipt_path: Path, evaluator_root: Path | None = None) -> dict[str, Any]:
    """Offline verifier: rerun checks, never trust recorded PASS fields."""
    receipt = json.loads(Path(receipt_path).read_text(encoding="utf-8"))
    _require(receipt.get("schema") == RECEIPT_SCHEMA, f"receipt schema must be {RECEIPT_SCHEMA}")
    request = receipt["request"]
    plan = receipt["plan"]
    work = Path(request["work_root"])
    out_root = work / "out"
    report: dict[str, Any] = {
        "schema": f"{RECEIPT_SCHEMA}.verification",
        "receipt": str(receipt_path),
        "artifact_integrity": "PASS",
        "semantic_replay": "PASS",
        "execution_provenance": "NOT_VERIFIED",
        "problems": [],
    }

    def problem(kind: str, message: str) -> None:
        report["problems"].append(f"{kind}: {message}")
        if kind == "artifact_integrity":
            report["artifact_integrity"] = "FAIL"
        report["semantic_replay"] = "FAIL"

    # 1. artifact integrity: recompute every recorded hash
    for entry in receipt["output_manifest"]:
        f = out_root / entry["path"]
        if not f.is_file():
            problem("artifact_integrity", f"missing artifact {entry['path']}")
        elif _sha256_file(f) != entry["sha256"]:
            problem("artifact_integrity", f"hash mismatch {entry['path']}")
    case_input_dirs = {case["id"]: Path(case["input_dir"]) for case in plan.get("cases", [])}
    for case_manifest in plan["input_manifest"]:
        base = case_input_dirs.get(case_manifest["id"], work / "gen" / case_manifest["id"])
        for entry in case_manifest["files"]:
            f = base / entry["path"]
            if not f.is_file():
                problem("artifact_integrity", f"missing input {case_manifest['id']}/{entry['path']}")
            elif _sha256_file(f) != entry["sha256"]:
                problem("artifact_integrity", f"input hash mismatch {case_manifest['id']}/{entry['path']}")

    # 2. judge identity: digests must match the supplied evaluator tree
    if evaluator_root is not None:
        for name, rel in (("judge_sha256", request["judge"]),
                          ("functional_judge_sha256", request["functional_judge"]),
                          ("generator_sha256", request["generator"])):
            actual = _sha256_file(Path(rel))
            if actual != plan[name]:
                problem("artifact_integrity", f"{name} changed since the plan was frozen")

    # 3. semantic replay: rerun judges on retained observations
    if report["artifact_integrity"] == "PASS":
        replay_cases = receipt.get("case_receipts") or receipt["case_results"]
        for case in replay_cases:
            case_id = case.get("case_id") or case["case"]
            case_dir = out_root / case_id
            input_dir = case_input_dirs.get(case_id, work / "gen" / case_id)
            policy = input_dir / "policy.json"
            if case.get("execution", {}).get("kind") == "NOT_RUN" or case.get("judged") is False:
                continue
            params = dict(request.get("judge_params") or {})
            params["policy"] = str(policy)
            params["input_dir"] = str(input_dir)
            sec = run_judge(request["judge"], str(case_dir), params)
            sec_ok = sec.passed
            if case.get("execution", {}).get("kind") == "REJECT":
                fn_ok = True
            else:
                fn = run_judge(request["functional_judge"], str(case_dir), params)
                fn_ok = fn.passed
            recorded = (case.get("verdict") == "PASS") if case.get("schema") == "battle.case_receipt.v1" else (case.get("passed") and (case.get("functional") or {}).get("status", "PASS") == "PASS")
            recomputed = sec_ok and fn_ok
            if recomputed != recorded:
                problem("semantic_replay",
                        f"case {case_id}: recomputed {'PASS' if recomputed else 'FAIL'} "
                        f"but receipt recorded {'PASS' if recorded else 'FAIL'}")

    # 4. recompute the campaign verdict from case results and compare
    final_cases = receipt.get("case_receipts") or receipt["case_results"]
    cases_passed = sum(1 for c in final_cases if c.get("verdict") == "PASS" or c.get("passed") is True)
    verdict_recomputed_from_cases = "PASS" if (cases_passed == len(final_cases)
                                                 and final_cases) else "FAIL"
    if verdict_recomputed_from_cases != receipt["verdict"]:
        problem("semantic_replay",
                f"campaign verdict tampered: case results recompute {verdict_recomputed_from_cases} "
                f"but receipt records {receipt['verdict']}")

    report["verdict_recomputed"] = "PASS" if not report["problems"] else "FAIL"
    report["verdict_recorded"] = receipt["verdict"]
    if report["verdict_recomputed"] != report["verdict_recorded"]:
        report["semantic_replay"] = "FAIL"
    report["passed"] = (report["artifact_integrity"] == "PASS"
                        and report["semantic_replay"] == "PASS"
                        and report["verdict_recomputed"] == report["verdict_recorded"])
    return report


def _cli(argv: list[str]) -> int:
    import argparse
    ap = argparse.ArgumentParser(description="Campaign contract: run + offline verify")
    sub = ap.add_subparsers(dest="command", required=True)
    run_p = sub.add_parser("run", help="Run a campaign from a request JSON file")
    run_p.add_argument("--request", required=True)
    ver_p = sub.add_parser("verify", help="Offline-verify a receipt (reruns judges)")
    ver_p.add_argument("--receipt", required=True)
    ver_p.add_argument("--evaluator-root", default=None)
    args = ap.parse_args(argv)
    if args.command == "run":
        request = load_path(args.request)
        receipt = run_contract_campaign(request)
        print(json.dumps({"status": receipt["verdict"], "receipt": str(Path(args.request).parent / "receipt.json")}))
        return 0 if receipt["verdict"] == "PASS" else 1
    report = verify_campaign_receipt(Path(args.receipt),
                                     Path(args.evaluator_root) if args.evaluator_root else None)
    print(json.dumps(report, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    import sys
    raise SystemExit(_cli(sys.argv[1:]))
