#!/usr/bin/env python3
"""Adversarial proof-trust eval for project-watchdog's repair proof gate (#1637).

Deterministic and fault-injected (mocked=true): builds synthetic ask-run
directories and proof artifacts, then asserts the gate REJECTS forged or
non-independent evidence and ACCEPTS only structurally valid typed proof.
Expected outcomes were frozen before running against the candidate.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent
WATCHDOG = Path(os.environ.get(
    "WATCHDOG_SCRIPTS",
    str(Path(__file__).resolve().parents[1] / "scripts"),
))
sys.path.insert(0, str(WATCHDOG))
from watchdog import handlers  # noqa: E402

ISSUE_BODY = """## Required proof

Run the check with --output /PROOF_DIR/result.json and read it back.
"""


def _mkrun(root: Path, reviewer_md: str | None, *, creator_md: str = "did the work",
           runs: int = 1) -> Path:
    ask = root / "ask-run"
    for i in range(runs):
        node = ask / f"run-{i}" / "node-artifacts" / "handler-claude-fable-low"
        node.mkdir(parents=True)
        (node / "response.md").write_text(creator_md)
        node2 = ask / f"run-{i}" / "node-artifacts" / "handler-claude-fable-low-2"
        node2.mkdir(parents=True)
        if reviewer_md is not None:
            (node2 / "response.md").write_text(reviewer_md)
    return ask


def _reviewer(proof: Path, verdict: str = "PASS") -> str:
    return (f"Reviewed the change.\nVERDICT: {verdict}\n"
            f"REVIEW_COMMIT: {'a' * 40}\nPROOF_ARTIFACT: {proof}\n")


def _gate(tmp: Path, reviewer_md: str | None, artifact_payload, *, runs: int = 1,
          not_before: float | None = None, artifact_mtime: float | None = None):
    proof = tmp / "result.json"
    if artifact_payload is not None:
        proof.write_text(json.dumps(artifact_payload))
        if artifact_mtime is not None:
            os.utime(proof, (artifact_mtime, artifact_mtime))
    body = ISSUE_BODY.replace("/PROOF_DIR", str(tmp))
    ask = _mkrun(tmp, reviewer_md, runs=runs)
    return handlers.evaluate_repair_proof(
        ask_run_dir=ask, issue_body=body, creator="claude-fable-low",
        reviewer="claude-fable-low", repair_worktree=tmp,
        not_before=not_before if not_before is not None else time.time() - 60,
        reviewed_commit="b" * 40,
    )


def valid_v2_report(readiness: str, outcome: str) -> dict:
    return {
        "schema": "agentic_evals.report.v2",
        "readiness": readiness,
        "outcome_counts": {"PASS": 1 if outcome == "PASS" else 0,
                           "FAIL": 1 if outcome == "FAIL" else 0,
                           "BLOCKED": 0, "NOT_TESTED": 0},
        "cases": [{"name": "case", "outcome": outcome,
                   "trials": [{"outcome": outcome}]}],
    }


def main() -> int:
    checks: list[dict] = []

    def check(name: str, gate: dict, expect_ok: bool, must_mention: str | None = None):
        ok = gate["ok"] is expect_ok
        if ok and not expect_ok and must_mention:
            ok = any(must_mention in r for r in gate["reasons"])
        checks.append({"name": name, "expected_ok": expect_ok, "observed_ok": gate["ok"],
                       "reasons": gate["reasons"], "passed": ok})

    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)

        # NEGATIVE: fabricated fresh bare {"passed": true, "live": true} JSON.
        # The ticket's core control: bare boolean assertions with no domain
        # outcome value must NOT satisfy the proof gate.
        d = tmp / "n1"; d.mkdir()
        gate = _gate(d, _reviewer(d / "result.json"), {"passed": True, "live": True})
        check("fabricated_bare_passed_true_rejected", gate, False)

        # NEGATIVE: generic PASS plus live:true is still not a bound live proof.
        d = tmp / "n1b"; d.mkdir()
        gate = _gate(d, _reviewer(d / "result.json"),
                     {"status": "PASS", "passed": True, "live": True, "mocked": False})
        check("fabricated_generic_live_pass_rejected", gate, False, "lacks command/artifact/run binding")

        # POSITIVE: untyped domain payload {"readiness": "READY"} remains
        # accepted — the retained contract from #1499-era tests must not break.
        d = tmp / "p2"; d.mkdir()
        gate = _gate(d, _reviewer(d / "result.json"), {"readiness": "READY"})
        check("untyped_domain_ready_still_accepted", gate, True)

        # NEGATIVE: stale artifact predating dispatch (freshness).
        d = tmp / "n2"; d.mkdir()
        gate = _gate(d, _reviewer(d / "result.json"), valid_v2_report("READY", "PASS"),
                     artifact_mtime=time.time() - 3600, not_before=time.time() - 60)
        check("stale_artifact_rejected", gate, False, "predates")

        # NEGATIVE: missing Judge (no reviewer response at all).
        d = tmp / "n3"; d.mkdir()
        gate = _gate(d, None, valid_v2_report("READY", "PASS"))
        check("missing_reviewer_rejected", gate, False, "wrote no response")

        # NEGATIVE: ambiguous cross-run reviewer artifacts (two run dirs).
        d = tmp / "n4"; d.mkdir()
        gate = _gate(d, _reviewer(d / "result.json"), valid_v2_report("READY", "PASS"), runs=2)
        check("cross_run_ambiguity_rejected", gate, False)

        # NEGATIVE: expected-negative NOT_READY report must not read as a pass.
        d = tmp / "n5"; d.mkdir()
        gate = _gate(d, _reviewer(d / "result.json"), valid_v2_report("NOT_READY", "FAIL"))
        check("not_ready_report_rejected", gate, False)

        # NEGATIVE: v2 report whose outcome counts contradict its cases.
        d = tmp / "n6"; d.mkdir()
        bad = valid_v2_report("READY", "PASS")
        bad["outcome_counts"] = {"PASS": 3, "FAIL": 0, "BLOCKED": 0, "NOT_TESTED": 0}
        gate = _gate(d, _reviewer(d / "result.json"), bad)
        check("count_contradiction_rejected", gate, False, "disagree")

        # NEGATIVE: fabricated typed replay proof with self-consistent booleans
        # but invalid identity hashes must fail the typed validator.
        d = tmp / "n7"; d.mkdir()
        gate = _gate(d, _reviewer(d / "result.json"),
                     {"schema": "agentic_evals.issue1631.live_e2e_result.v1",
                      "passed": True, "live": True, "mocked": False, "steps": {}})
        check("forged_typed_replay_rejected", gate, False)

        # NEGATIVE: reviewer declares no verdict at all.
        d = tmp / "n8"; d.mkdir()
        gate = _gate(d, f"looks good\nPROOF_ARTIFACT: {d/'result.json'}\nREVIEW_COMMIT: {'a'*40}\n",
                     valid_v2_report("READY", "PASS"))
        check("verdictless_reviewer_rejected", gate, False, "no VERDICT")

        # POSITIVE control: structurally valid fresh typed READY report,
        # unambiguous reviewer PASS, reviewed commit present.
        d = tmp / "p1"; d.mkdir()
        gate = _gate(d, _reviewer(d / "result.json"), valid_v2_report("READY", "PASS"))
        check("valid_typed_proof_accepted", gate, True)

    passed = all(c["passed"] for c in checks)
    result = {"schema": "project_watchdog.proof_trust_eval.v1", "mocked": True,
              "live": False, "passed": passed, "checks": checks}
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("/tmp/watchdog-proof-trust-result.json")
    out.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({"passed": passed,
                      "failing": [c["name"] for c in checks if not c["passed"]]}, indent=2))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
