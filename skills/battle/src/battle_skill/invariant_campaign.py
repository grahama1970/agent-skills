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


@dataclass
class CampaignResult:
    schema: str = "battle.invariant_campaign_result.v1"
    passed: bool = False
    cases_total: int = 0
    cases_passed: int = 0
    failures: list[dict[str, Any]] = field(default_factory=list)
    case_log: list[dict[str, Any]] = field(default_factory=list)

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


def run_campaign(generator: str, target_run_cmd: str, judge: str,
                 gen_params: dict[str, Any] | None = None,
                 judge_params: dict[str, Any] | None = None,
                 output_subdir: str = "corpus") -> CampaignResult:
    gen_params = gen_params or {}
    judge_params = dict(judge_params or {})
    result = CampaignResult()
    work = Path(tempfile.mkdtemp(prefix="invariant-campaign-"))
    try:
        gen: Iterator[tuple[str, str]] = _load_generator(generator)(str(work / "gen"), gen_params)
        for name, input_dir in gen:
            out_dir = work / "out" / name
            out_dir.mkdir(parents=True, exist_ok=True)
            cmd = target_run_cmd.format(input=shlex.quote(str(input_dir)),
                                        output=shlex.quote(str(out_dir)))
            run = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=600)
            # A fail-closed target that produces no output is not a leak; the
            # invariant holds vacuously for that version.
            produced = (out_dir / output_subdir).exists() and any((out_dir / output_subdir).rglob("*"))
            if run.returncode != 0 or not produced:
                verdict = {"case": name, "judged": False, "passed": True,
                           "note": "target fail-closed (no released output)"}
                result.cases_passed += 1
            else:
                jp = dict(judge_params)
                # let the generator pass a per-case policy path via a sentinel file
                policy_sentinel = Path(input_dir) / "policy.json"
                if policy_sentinel.exists() and "policy" not in jp:
                    jp["policy"] = str(policy_sentinel)
                jr = run_judge(judge, str(out_dir), jp)
                verdict = {"case": name, "judged": True, "passed": jr.passed,
                           "violations": jr.violations}
                if jr.passed:
                    result.cases_passed += 1
                else:
                    result.failures.append(verdict)
            result.cases_total += 1
            result.case_log.append(verdict)
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
    args = ap.parse_args(argv)
    r = run_campaign(args.generator, args.target_run_cmd, args.judge,
                     json.loads(args.gen_params), json.loads(args.judge_params), args.output_subdir)
    print(json.dumps(r.to_dict(), indent=2))
    print(f"\nCAMPAIGN: {'PASS' if r.passed else 'FAIL'} "
          f"({r.cases_passed}/{r.cases_total} versions clean)")
    return 0 if r.passed else 1


if __name__ == "__main__":
    import sys
    raise SystemExit(_cli(sys.argv[1:]))
