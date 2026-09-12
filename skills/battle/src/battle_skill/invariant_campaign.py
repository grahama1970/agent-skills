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

import importlib.util
import json
import shlex
import subprocess
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterator

from .invariant_judge import run_judge

PROFILE_SCHEMA = "battle.campaign_profile.v1"


def load_profile(path: str) -> dict[str, Any]:
    """Load and shape-validate a campaign profile (battle.campaign_profile.v1).

    A profile is the consumer-owned acceptance contract: it resolves permitted
    (MAY_REJECT) choices to a definite expectation, freezes the required-case
    inventory, and binds the spec it derives from. It may never downgrade a
    generator-declared MUST_ACCEPT/MUST_REJECT (the spec floor).
    """
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if data.get("schema") != PROFILE_SCHEMA:
        raise ValueError(f"profile schema must be {PROFILE_SCHEMA}")
    if not data.get("profile_id"):
        raise ValueError("profile must declare profile_id")
    overrides = data.get("expectation_overrides") or {}
    if not isinstance(overrides, dict):
        raise ValueError("expectation_overrides must be an object")
    for case_id, value in overrides.items():
        if str(value).upper() not in ("MUST_ACCEPT", "MUST_REJECT"):
            raise ValueError(f"override for {case_id!r} must be MUST_ACCEPT or MUST_REJECT, got {value!r}")
    required = data.get("required_case_ids") or []
    if not isinstance(required, list) or len(set(required)) != len(required):
        raise ValueError("required_case_ids must be a duplicate-free list")
    return data


@dataclass
class CampaignResult:
    schema: str = "battle.invariant_campaign_result.v1"
    passed: bool = False
    cases_total: int = 0
    cases_passed: int = 0
    failures: list[dict[str, Any]] = field(default_factory=list)
    case_log: list[dict[str, Any]] = field(default_factory=list)
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


def run_campaign(generator: str, target_run_cmd: str, judge: str,
                 gen_params: dict[str, Any] | None = None,
                 judge_params: dict[str, Any] | None = None,
                 output_subdir: str = "corpus",
                 profile: dict[str, Any] | None = None,
                 functional_judge: str | None = None) -> CampaignResult:
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
    work = Path(tempfile.mkdtemp(prefix="invariant-campaign-"))
    # The approved contract determines the required judge set: omitting a
    # required judge must fail BEFORE any target execution (WebGPT review).
    if "functional" in required_judges and not functional_judge:
        result.failures.append({"case": None, "judged": False, "passed": False,
                                "violations": ["required-judge-missing:functional:contract requires it and no --functional-judge was supplied"]})
        result.passed = False
        return result
    try:
        gen: Iterator[tuple] = _load_generator(generator)(str(work / "gen"), gen_params)
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
            if name in profile_overrides:
                resolved = str(profile_overrides[name]).upper()
                if expectation != "MAY_REJECT":
                    result.failures.append({"case": name, "judged": False, "passed": False,
                                            "violations": [f"profile-illegal-expectation-override:{name}:generator declared {expectation}; a profile may only resolve MAY_REJECT choices"]})
                else:
                    expectation = resolved
                    expectation_source = "profile"
            seen_cases.add(name)
            if expectation == "MUST_ACCEPT":
                result.must_accept_count += 1
            elif expectation == "MUST_REJECT":
                result.must_reject_count += 1
            else:
                result.may_reject_count += 1
            out_dir = work / "out" / name
            out_dir.mkdir(parents=True, exist_ok=True)
            cmd = target_run_cmd.format(input=shlex.quote(str(input_dir)),
                                        output=shlex.quote(str(out_dir)))
            run = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=600)
            # A fail-closed target that produces no output is not a leak; the
            # invariant holds vacuously for that version -- unless the case was
            # declared MUST_ACCEPT, where safe rejection is a coverage failure.
            produced = (out_dir / output_subdir).exists() and any((out_dir / output_subdir).rglob("*"))
            verdict = {"case": name, "expectation": expectation, "expectation_source": expectation_source, "judged": False, "passed": True,
                       "note": "target fail-closed (no released output)"}
            if run.returncode != 0 or not produced:
                result.rejected_count += 1
                if expectation == "MUST_ACCEPT":
                    verdict["passed"] = False
                    verdict["violations"] = ["required-accept-case-rejected (vacuous-pass blocker)"]
                    result.failures.append(verdict)
                else:
                    result.cases_passed += 1
            else:
                result.accepted_count += 1
                jp = dict(judge_params)
                # let the generator pass a per-case policy path via a sentinel file
                policy_sentinel = Path(input_dir) / "policy.json"
                if policy_sentinel.exists() and "policy" not in jp:
                    jp["policy"] = str(policy_sentinel)
                jp.setdefault("input_dir", str(input_dir))
                jr = run_judge(judge, str(out_dir), jp)
                verdict = {"case": name, "expectation": expectation, "expectation_source": expectation_source, "judged": True, "passed": jr.passed,
                           "violations": jr.violations}
                functional = {"status": "PASS", "violations": []}  # no functional gate configured
                if functional_judge is not None:
                    fr = run_judge(functional_judge, str(out_dir), jp)
                    functional = {"status": "PASS" if fr.passed else "FAIL", "violations": fr.violations}
                    verdict["functional"] = functional
                if jr.passed and functional["status"] == "PASS":
                    result.cases_passed += 1
                    if expectation == "MUST_REJECT":
                        verdict["passed"] = False
                        verdict["violations"] = ["required-reject-case-accepted (out-of-domain input was not safely rejected)"]
                        result.failures.append(verdict)
                else:
                    result.failures.append(verdict)
                    if expectation == "MUST_REJECT":
                        result.failures.append({"case": name, "expectation": expectation,
                                                "judged": True, "passed": False,
                                                "violations": ["required-reject-case-accepted (out-of-domain input was not safely rejected)"]})
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
        result.passed = not result.failures and result.cases_total > 0
        return result
    finally:
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
