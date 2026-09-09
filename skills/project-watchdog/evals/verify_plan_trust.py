#!/usr/bin/env python3
"""Adversarial VERIFY_PLAN admission eval for #1637's plan-binding half.

Deterministic, fault-injected (mocked=true). Expectations frozen before run:
every forged/incomplete/creator-substituted plan must raise; only the exact
reviewer-owned complete plan is admitted.
"""
import json, os, sys
from pathlib import Path

WATCHDOG = Path(os.environ.get("WATCHDOG_SCRIPTS",
    str(Path(__file__).resolve().parents[1] / "scripts")))
sys.path.insert(0, str(WATCHDOG))
from watchdog import handlers  # noqa: E402

BODY = """## Required proof

Run the check with --output /tmp/vp-proof/result.json and read it back.
"""

def plan_line(artifacts, coverage=None):
    return "VERIFY_PLAN: " + json.dumps({
        "schema": "agent_skills.project_watchdog.verification_plan.v1",
        "commands": ["python3 -m json.tool /tmp/vp-proof/result.json"],
        "artifacts": artifacts,
        "coverage": coverage or {"all required clauses": "readback of the named output artifact"},
    })

GOOD = f"VERDICT: PASS\nPROOF_ARTIFACT: /tmp/vp-proof/result.json\n{plan_line(['/tmp/vp-proof/result.json'])}\n"

def expect_raises(name, review, must_mention, checks):
    try:
        handlers.validated_verification_plan(review, BODY, Path("/tmp"))
        checks.append({"name": name, "passed": False, "observed": "admitted"})
    except (ValueError, Exception) as exc:  # pydantic ValidationError included
        ok = must_mention is None or must_mention in str(exc)
        checks.append({"name": name, "passed": ok, "observed": str(exc)[:200]})

def main():
    checks = []
    # POSITIVE: complete reviewer plan admitted.
    try:
        plan = handlers.validated_verification_plan(GOOD, BODY, Path("/tmp"))
        checks.append({"name": "complete_reviewer_plan_admitted", "passed": bool(plan.commands)})
    except Exception as exc:
        checks.append({"name": "complete_reviewer_plan_admitted", "passed": False, "observed": str(exc)[:200]})
    # NEGATIVE: no reviewer PASS (creator cannot substitute authority).
    expect_raises("no_pass_verdict_rejected", GOOD.replace("VERDICT: PASS", "VERDICT: NEEDS_ATTENTION"),
                  "independent reviewer PASS", checks)
    # NEGATIVE: zero plan lines (the truncated-reviewer shape).
    expect_raises("missing_plan_rejected", "VERDICT: PASS\nPROOF_ARTIFACT: /tmp/vp-proof/result.json\n",
                  "exactly one native verification plan", checks)
    # NEGATIVE: two plan lines (ambiguous authority).
    expect_raises("duplicate_plan_rejected", GOOD + plan_line(["/tmp/vp-proof/result.json"]) + "\n",
                  "exactly one native verification plan", checks)
    # NEGATIVE: truncated JSON plan line (mid-string cut, finish_reason=length shape).
    expect_raises("truncated_plan_json_rejected",
                  "VERDICT: PASS\nVERIFY_PLAN: {\"schema\": \"agent_skills.project_watchdog.verification_plan.v1\", \"commands\": [\"python3 -m json.t",
                  None, checks)
    # NEGATIVE: plan omits the ticket's mandatory --output artifact (the #1628
    # wrong-artifact fallback shape: names -deterministic-verify.json instead).
    expect_raises("wrong_artifact_binding_rejected",
                  f"VERDICT: PASS\nPROOF_ARTIFACT: /tmp/vp-proof/other-deterministic-verify.json\n{plan_line(['/tmp/vp-proof/other-deterministic-verify.json'])}\n",
                  "omits mandatory result artifacts", checks)
    # NEGATIVE: empty coverage value (rubber-stamp coverage).
    expect_raises("blank_coverage_rejected",
                  f"VERDICT: PASS\nPROOF_ARTIFACT: /tmp/vp-proof/result.json\n{plan_line(['/tmp/vp-proof/result.json'], {'all required clauses': '  '})}\n",
                  "coverage must name nonempty clauses", checks)
    # NEGATIVE: multiline/injection command shape.
    bad = json.dumps({"schema": "agent_skills.project_watchdog.verification_plan.v1",
                      "commands": ["echo a\necho b"], "artifacts": ["/tmp/vp-proof/result.json"],
                      "coverage": {"all required clauses": "x"}})
    expect_raises("multiline_command_rejected", f"VERDICT: PASS\nVERIFY_PLAN: {bad}\n", None, checks)

    passed = all(c["passed"] for c in checks)
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("/tmp/watchdog-verify-plan-result.json")
    out.write_text(json.dumps({"schema": "project_watchdog.verify_plan_eval.v1", "mocked": True,
                               "live": False, "passed": passed, "checks": checks}, indent=2) + "\n")
    print(json.dumps({"passed": passed, "failing": [c["name"] for c in checks if not c["passed"]]}, indent=2))
    return 0 if passed else 1

if __name__ == "__main__":
    raise SystemExit(main())
