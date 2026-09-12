"""Invariant campaign: Red generates many input 'versions', runs the target on
each, and an independent Judge scores every output.

This is the brief-complete adversarial loop. Instead of judging one static
output, Red materializes a MATRIX of inputs -- every format x every
representation the target's spec admits, its documented edge cases, PLUS random
fuzz -- runs the real target on each, and the Judge (not self-report) decides
whether the invariant held for that version. Any FAIL is a concrete, reproducible
vulnerability with the exact input.

Pieces (all pluggable, all independent of the target's own code):
- a GENERATOR module: yields (case_name, input_dir) corpora. It encodes the
  brief matrix + fuzz.
- a TARGET RUN command template with {input} and {output} placeholders (how to
  run the target on one input dir producing one output dir); commonly a
  `docker run` line.
- a JUDGE module (battle.invariant_result.v1) scoring the output dir.

Verdict: campaign PASSES only if every version's Judge passed. A single failing
version is a Red win (invariant violated) and is reported with a repro.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import re
import shlex
import shutil
import stat
import subprocess
import tempfile
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterator

from .invariant_judge import run_judge
from .strict_json import finite_json_values, load_path

PROFILE_SCHEMA = "battle.campaign_profile.v1"


def load_profile(path: str) -> dict[str, Any]:
    """Load and shape-validate a campaign profile (battle.campaign_profile.v1).

    A profile is the consumer-owned acceptance contract: it resolves permitted
    (MAY_REJECT) choices to a definite expectation, freezes the required-case
    inventory, and binds the spec it derives from. It may never downgrade a
    generator-declared MUST_ACCEPT/MUST_REJECT (the spec floor).
    """
    data = load_path(path)
    if not isinstance(data, dict):
        raise ValueError("profile must be a JSON object")
    allowed = {"schema", "profile_id", "required_judges", "expectation_overrides", "required_case_ids"}
    extra = sorted(set(data) - allowed)
    if extra:
        raise ValueError(f"profile contains unknown fields: {extra}")
    if not finite_json_values(data):
        raise ValueError("profile contains non-finite numeric value")
    if data.get("schema") != PROFILE_SCHEMA:
        raise ValueError(f"profile schema must be {PROFILE_SCHEMA}")
    if not isinstance(data.get("profile_id"), str) or not data["profile_id"].strip():
        raise ValueError("profile must declare non-empty profile_id")
    judges = data.get("required_judges") or []
    if not isinstance(judges, list) or any(not isinstance(item, str) or not item.strip() for item in judges) or len(set(judges)) != len(judges):
        raise ValueError("required_judges must be a duplicate-free list of non-empty strings")
    overrides = data.get("expectation_overrides") or {}
    if not isinstance(overrides, dict):
        raise ValueError("expectation_overrides must be an object")
    for case_id, value in overrides.items():
        if not isinstance(case_id, str) or not case_id.strip():
            raise ValueError("expectation override IDs must be non-empty strings")
        if not isinstance(value, str) or value.upper() not in ("MUST_ACCEPT", "MUST_REJECT"):
            raise ValueError(f"override for {case_id!r} must be MUST_ACCEPT or MUST_REJECT, got {value!r}")
    required = data.get("required_case_ids") or []
    if not isinstance(required, list) or any(not isinstance(item, str) or not item.strip() for item in required) or len(set(required)) != len(required):
        raise ValueError("required_case_ids must be a duplicate-free list of non-empty strings")
    return data


@dataclass
class CampaignResult:
    schema: str = "battle.invariant_campaign_result.v1"
    passed: bool = False
    cases_total: int = 0
    cases_passed: int = 0
    failures: list[dict[str, Any]] = field(default_factory=list)
    case_log: list[dict[str, Any]] = field(default_factory=list)
    case_receipts: list[dict[str, Any]] = field(default_factory=list)
    aggregation: dict[str, Any] = field(default_factory=dict)
    # Two-axis (non-vacuous) coverage: generators may declare per-case
    # expectations. MUST_ACCEPT cases must be accepted, processed, and judged
    # clean; MUST_REJECT cases must be safely rejected (fail-closed); a target
    # that rejects everything now FAILS instead of passing vacuously.
    declares_expectations: bool = False
    must_accept_count: int = 0
    must_reject_count: int = 0
    may_reject_count: int = 0
    accepted_count: int = 0
    rejected_count: int = 0
    profile_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _load_generator(path: str):
    p = Path(path).resolve()
    spec = importlib.util.spec_from_file_location("battle_invariant_generator", p)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load generator: {p}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    if not hasattr(mod, "generate") or not callable(mod.generate):
        raise AttributeError(f"generator {p} must define generate(work_dir, params) -> iterator of (name, input_dir)")
    return mod.generate


VALID_EXPECTATIONS = {"MUST_ACCEPT", "MUST_REJECT", "MAY_REJECT"}
_SAFE_CASE_ID = re.compile(r"[A-Za-z0-9_.-]{1,128}\Z")


def _safe_case_id(raw: Any) -> str:
    name = str(raw)
    if not _SAFE_CASE_ID.fullmatch(name) or name in {".", ".."}:
        raise ValueError(f"unsafe case id: {name!r}")
    return name


def _require_under(path: Path, root: Path, label: str) -> Path:
    resolved = path.resolve()
    try:
        resolved.relative_to(root.resolve())
    except ValueError as exc:
        raise ValueError(f"{label} escapes owned root: {path}") from exc
    return resolved


def _regular_files(root: Path) -> list[Path]:
    if not root.exists():
        return []
    if root.is_symlink() or not root.is_dir():
        raise ValueError(f"artifact root is not a real directory: {root}")
    files: list[Path] = []
    for path in sorted(root.rglob("*")):
        mode = path.lstat().st_mode
        if stat.S_ISLNK(mode):
            raise ValueError(f"artifact path is a symlink: {path}")
        if stat.S_ISDIR(mode):
            continue
        if not stat.S_ISREG(mode):
            raise ValueError(f"artifact path is not a regular file: {path}")
        files.append(path)
    return files


def _materialize_case_snapshot(name: str, source: Path, owned_root: Path, dest_root: Path) -> Path:
    case_id = _safe_case_id(name)
    src = _require_under(source, owned_root, "case input")
    dest = dest_root / case_id
    shutil.rmtree(dest, ignore_errors=True)
    for file_path in _regular_files(src):
        rel = file_path.resolve().relative_to(src)
        target = dest / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(file_path.read_bytes())
    return dest


def _sha256_bytes(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _tree_manifest(root: Path) -> list[dict[str, Any]]:
    if not root.exists():
        return []
    return [
        {"path": str(path.relative_to(root)), "sha256": _sha256_bytes(path.read_bytes()), "bytes": path.stat().st_size}
        for path in _regular_files(root)
    ]


def _manifest_sha256(root: Path) -> str:
    payload = json.dumps(_tree_manifest(root), sort_keys=True).encode()
    return _sha256_bytes(payload)


def _policy_path(input_dir: Path) -> Path | None:
    policy = input_dir / "policy.json"
    return policy if policy.exists() else None


def _fixture_precheck(input_dir: Path, judge_path: str, judge_params: dict[str, Any], expectation: str) -> dict[str, Any]:
    policy = _policy_path(input_dir)
    corpus = input_dir / "corpus"
    if not corpus.exists() or not any(corpus.rglob("*")):
        return {"status": "FAIL", "evidence_sha256": _manifest_sha256(input_dir), "violations": ["fixture_precheck:missing_or_empty_corpus"]}
    if policy is None:
        return {"status": "PASS", "evidence_sha256": _manifest_sha256(input_dir), "violations": [], "note": "no policy sentinel; corpus-only precheck"}
    params = dict(judge_params)
    params["policy"] = str(policy)
    params.setdefault("input_dir", str(input_dir))
    params.setdefault("output_subdir", "corpus")
    witness = run_judge(judge_path, str(input_dir), params)
    if not witness.passed:
        return {"status": "PASS", "evidence_sha256": _manifest_sha256(input_dir), "violations": [], "witness": witness.violations[:8]}
    if expectation == "MUST_REJECT":
        return {"status": "PASS", "evidence_sha256": _manifest_sha256(input_dir), "violations": [], "note": "generator-declared MUST_REJECT; policy witness not required"}
    return {"status": "FAIL", "evidence_sha256": _manifest_sha256(input_dir), "violations": ["fixture_precheck:no_policy_value_witness"]}


def _execution_kind(run_returncode: int, produced: bool) -> str:
    if run_returncode == 0 and produced:
        return "ACCEPT"
    return "REJECT"


def _rejection_code(run: subprocess.CompletedProcess[str], produced: bool) -> str | None:
    if run.returncode == 0 and produced:
        return None
    text = (run.stderr or run.stdout or "").strip().splitlines()
    return text[-1][-160:] if text else "no_output"


def _case_receipt(name: str, input_dir: Path, expectation: str, expectation_source: str,
                  fixture_precheck: dict[str, Any], execution: dict[str, Any] | None,
                  produced: bool, verdict: dict[str, Any], security: dict[str, Any] | None,
                  functional: dict[str, Any] | None, run: subprocess.CompletedProcess[str] | None) -> dict[str, Any]:
    passed = bool(verdict.get("passed")) and fixture_precheck.get("status") == "PASS"
    return {
        "schema": "battle.case_receipt.v1",
        "case_id": name,
        "requirement_ids": [],
        "family_ids": [],
        "expectation": expectation,
        "expectation_source": expectation_source,
        "input_manifest_sha256": _manifest_sha256(input_dir),
        "fixture_precheck": fixture_precheck,
        "execution": execution or {"kind": "NOT_RUN", "exit_code": None, "signal": None, "timed_out": False, "oom_killed": False, "duration_ms": 0},
        "rejection": {
            "code": _rejection_code(run, produced) if run is not None else "fixture_precheck_failed",
            "permitted": expectation in ("MUST_REJECT", "MAY_REJECT") if run is not None and not produced else None,
            "predicate_verified": fixture_precheck.get("status") == "PASS" if run is not None and not produced else None,
        },
        "capture_complete": execution is not None,
        "security_judge": security or {"status": "NOT_RUN", "violations": []},
        "functional_judge": functional or {"status": "NOT_APPLICABLE", "violations": []},
        "violations": list(verdict.get("violations") or []) + list(fixture_precheck.get("violations") or []),
        "verdict": "PASS" if passed else "FAIL",
    }


def _aggregate(case_receipts: list[dict[str, Any]]) -> dict[str, Any]:
    accepted = [c for c in case_receipts if c["execution"]["kind"] == "ACCEPT"]
    rejected = [c for c in case_receipts if c["execution"]["kind"] == "REJECT"]
    return {
        "schema": "battle.campaign_aggregate.v1",
        "planned_count": len(case_receipts),
        "executed_count": sum(1 for c in case_receipts if c["execution"]["kind"] != "NOT_RUN"),
        "accepted_count": len(accepted),
        "accepted_judged_pass_count": sum(1 for c in accepted if c["verdict"] == "PASS"),
        "safe_rejected_count": sum(1 for c in rejected if c["verdict"] == "PASS"),
        "unexpected_rejected_count": sum(1 for c in rejected if c["expectation"] == "MUST_ACCEPT"),
        "unsafe_rejected_count": sum(1 for c in rejected if c["security_judge"]["status"] == "FAIL"),
        "target_error_count": sum(1 for c in case_receipts if c["execution"].get("exit_code") not in (0, None) and c["expectation"] == "MUST_ACCEPT"),
        "judge_error_count": sum(1 for c in case_receipts if any("judge error:" in v for v in c.get("violations", []))),
        "incomplete_count": sum(1 for c in case_receipts if not c.get("capture_complete")),
        "failed_count": sum(1 for c in case_receipts if c["verdict"] != "PASS"),
        "required_case_failures": [c["case_id"] for c in case_receipts if c["expectation"] == "MUST_ACCEPT" and c["verdict"] != "PASS"],
    }


def run_campaign(generator: str, target_run_cmd: str, judge: str,
                 gen_params: dict[str, Any] | None = None,
                 judge_params: dict[str, Any] | None = None,
                 output_subdir: str = "corpus",
                 profile: dict[str, Any] | None = None,
                 functional_judge: str | None = None,
                 work_root: Path | None = None,
                 frozen_cases: list[dict[str, Any]] | None = None) -> CampaignResult:
    gen_params = gen_params or {}
    judge_params = dict(judge_params or {})
    result = CampaignResult()
    if profile is not None:
        result.profile_id = profile.get("profile_id")
        result.declares_expectations = True
    profile_overrides = (profile or {}).get("expectation_overrides") or {}
    required_case_ids = (profile or {}).get("required_case_ids") or []
    required_judges = (profile or {}).get("required_judges") or []
    seen_cases: set[str] = set()
    retained = work_root is not None
    if retained:
        work = Path(work_root)
        work.mkdir(parents=True, exist_ok=True)
    else:
        work = Path(tempfile.mkdtemp(prefix="invariant-campaign-"))
    gen_root = work / "gen"
    # The approved contract determines the required judge set: omitting a
    # required judge must fail BEFORE any target execution (WebGPT review).
    if "functional" in required_judges and not functional_judge:
        result.failures.append({"case": None, "judged": False, "passed": False,
                                "violations": ["required-judge-missing:functional:contract requires it and no --functional-judge was supplied"]})
        result.aggregation = _aggregate(result.case_receipts)
        result.passed = False
        return result
    try:
        if frozen_cases is None:
            gen: Iterator[tuple] = _load_generator(generator)(str(gen_root), gen_params)
        else:
            def _frozen_iter() -> Iterator[tuple]:
                for item in frozen_cases:
                    yield (item["id"], item["input_dir"], item["declared_expectation"])
            gen = _frozen_iter()
        for case in gen:
            if len(case) == 3:
                name, input_dir, expectation = case
                expectation = str(expectation).upper()
                if expectation not in VALID_EXPECTATIONS:
                    raise ValueError(f"case {name!r} declares invalid expectation {expectation!r}; expected one of {sorted(VALID_EXPECTATIONS)}")
                result.declares_expectations = True
            else:
                name, input_dir = case
                expectation = "MAY_REJECT"
            expectation_source = "generator"
            if frozen_cases is not None:
                frozen = next(item for item in frozen_cases if item["id"] == name)
                expectation = frozen.get("effective_expectation", expectation)
                expectation_source = frozen.get("expectation_source", expectation_source)
            elif name in profile_overrides:
                resolved = str(profile_overrides[name]).upper()
                if expectation != "MAY_REJECT":
                    result.failures.append({"case": name, "judged": False, "passed": False,
                                            "violations": [f"profile-illegal-expectation-override:{name}:generator declared {expectation}; a profile may only resolve MAY_REJECT choices"]})
                else:
                    expectation = resolved
                    expectation_source = "profile"
            name = _safe_case_id(name)
            seen_cases.add(name)
            if expectation == "MUST_ACCEPT":
                result.must_accept_count += 1
            elif expectation == "MUST_REJECT":
                result.must_reject_count += 1
            else:
                result.may_reject_count += 1
            input_path = Path(input_dir)
            if frozen_cases is None:
                input_path = _materialize_case_snapshot(name, input_path, gen_root, work / "snapshots")
            else:
                _require_under(input_path, work, "frozen case input")
                _regular_files(input_path)
            out_dir = work / "out" / name
            out_dir.mkdir(parents=True, exist_ok=True)
            jp = dict(judge_params)
            policy_sentinel = _policy_path(input_path)
            if policy_sentinel is not None and "policy" not in jp:
                jp["policy"] = str(policy_sentinel)
            jp.setdefault("input_dir", str(input_path))
            fixture_precheck = _fixture_precheck(input_path, judge, jp, expectation)
            if fixture_precheck["status"] != "PASS":
                verdict = {"case": name, "expectation": expectation, "expectation_source": expectation_source,
                           "judged": False, "passed": False, "violations": fixture_precheck["violations"],
                           "note": "fixture precheck failed before target execution"}
                result.failures.append(verdict)
                result.cases_total += 1
                result.case_log.append(verdict)
                result.case_receipts.append(_case_receipt(name, input_path, expectation, expectation_source,
                                                          fixture_precheck, None, False, verdict, None, None, None))
                continue

            cmd = target_run_cmd.format(input=shlex.quote(str(input_path)),
                                        output=shlex.quote(str(out_dir)))
            started = time.monotonic()
            run = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=600)
            duration_ms = int((time.monotonic() - started) * 1000)
            produced = (out_dir / output_subdir).exists() and any((out_dir / output_subdir).rglob("*"))
            execution_observation = {"kind": _execution_kind(run.returncode, produced), "exit_code": run.returncode,
                                     "signal": None, "timed_out": False, "oom_killed": False,
                                     "duration_ms": duration_ms, "stdout_tail": run.stdout[-2000:],
                                     "stderr_tail": run.stderr[-2000:]}
            execution_dir = out_dir / ".battle-execution"
            execution_dir.mkdir(parents=True, exist_ok=True)
            (execution_dir / "stdout.txt").write_text(run.stdout, encoding="utf-8", errors="replace")
            (execution_dir / "stderr.txt").write_text(run.stderr, encoding="utf-8", errors="replace")
            # A fail-closed target that produces no output is not a leak; the
            # invariant holds for MAY_REJECT/MUST_REJECT only after the Judge
            # also scans stdout/stderr. MUST_ACCEPT rejection is a release gate
            # failure because useful processing was not proven.
            if run.returncode != 0 or not produced:
                result.rejected_count += 1
                jr = run_judge(judge, str(out_dir), jp)
                security = {"status": "PASS" if jr.passed else "FAIL", "violations": jr.violations}
                verdict = {"case": name, "expectation": expectation, "expectation_source": expectation_source,
                           "judged": True, "passed": jr.passed,
                           "violations": jr.violations, "note": "target fail-closed (no released output)",
                           "execution": execution_observation}
                if expectation == "MUST_ACCEPT":
                    verdict["passed"] = False
                    verdict["violations"] = ["required-accept-case-rejected (vacuous-pass blocker)", *jr.violations]
                    result.failures.append(verdict)
                elif jr.passed:
                    result.cases_passed += 1
                else:
                    result.failures.append(verdict)
                result.case_receipts.append(_case_receipt(name, input_path, expectation, expectation_source,
                                                          fixture_precheck, execution_observation, produced,
                                                          verdict, security, None, run))
            else:
                result.accepted_count += 1
                jr = run_judge(judge, str(out_dir), jp)
                security = {"status": "PASS" if jr.passed else "FAIL", "violations": jr.violations}
                verdict = {"case": name, "expectation": expectation, "expectation_source": expectation_source, "judged": True, "passed": jr.passed,
                           "violations": jr.violations, "execution": execution_observation}
                functional = {"status": "PASS", "violations": []}  # no functional gate configured
                if functional_judge is not None:
                    fr = run_judge(functional_judge, str(out_dir), jp)
                    functional = {"status": "PASS" if fr.passed else "FAIL", "violations": fr.violations}
                    verdict["functional"] = functional
                if jr.passed and functional["status"] == "PASS" and expectation != "MUST_REJECT":
                    result.cases_passed += 1
                else:
                    verdict["passed"] = False
                    if expectation == "MUST_REJECT" and jr.passed and functional["status"] == "PASS":
                        verdict["violations"] = ["required-reject-case-accepted (out-of-domain input was not safely rejected)"]
                    result.failures.append(verdict)
                result.case_receipts.append(_case_receipt(name, input_path, expectation, expectation_source,
                                                          fixture_precheck, execution_observation, produced,
                                                          verdict, security, functional, run))
            result.cases_total += 1
            result.case_log.append(verdict)
        for case_id in profile_overrides:
            if case_id not in seen_cases:
                result.failures.append({"case": case_id, "judged": False, "passed": False,
                                        "violations": [f"profile-unknown-case-override:{case_id}:not yielded by this generator"]})
        for case_id in required_case_ids:
            if case_id not in seen_cases:
                result.failures.append({"case": case_id, "judged": False, "passed": False,
                                        "violations": [f"profile-required-case-missing:{case_id}"]})
        if result.declares_expectations and result.must_accept_count == 0:
            result.failures.append({"case": None, "judged": False, "passed": False,
                                    "violations": ["vacuous_campaign_no_required_accept_cases"]})
        result.aggregation = _aggregate(result.case_receipts)
        result.passed = not result.failures and result.cases_total > 0 and result.aggregation.get("failed_count") == 0
        return result
    finally:
        if not retained:
            subprocess.run(["docker", "run", "--rm", "-v", f"{work}:/w", "--entrypoint", "rm",
                            "anonymization-trial", "-rf", "/w"], capture_output=True, text=True)
            subprocess.run(["rm", "-rf", str(work)], capture_output=True, text=True)


def _cli(argv: list[str]) -> int:
    import argparse
    ap = argparse.ArgumentParser(description="Run a Battle invariant campaign (brief matrix + fuzz).")
    ap.add_argument("--generator", required=True)
    ap.add_argument("--target-run-cmd", required=True,
                    help="Shell template with {input} and {output}, e.g. a docker run line.")
    ap.add_argument("--judge", required=True)
    ap.add_argument("--gen-params", default="{}")
    ap.add_argument("--judge-params", default="{}")
    ap.add_argument("--output-subdir", default="corpus")
    ap.add_argument("--profile", default=None,
                    help="Path to a battle.campaign_profile.v1 consumer contract (expectation overrides + required-case inventory).")
    ap.add_argument("--functional-judge", default=None,
                    help="Optional second judge run on every accepted case; an accepted case must pass BOTH judges (accept-and-destroy guard).")
    args = ap.parse_args(argv)
    profile = load_profile(args.profile) if args.profile else None
    r = run_campaign(args.generator, args.target_run_cmd, args.judge,
                     json.loads(args.gen_params), json.loads(args.judge_params), args.output_subdir,
                     profile=profile, functional_judge=args.functional_judge)
    print(json.dumps(r.to_dict(), indent=2))
    print(f"\nCAMPAIGN: {'PASS' if r.passed else 'FAIL'} "
          f"({r.cases_passed}/{r.cases_total} versions clean)")
    return 0 if r.passed else 1


if __name__ == "__main__":
    import sys
    raise SystemExit(_cli(sys.argv[1:]))
