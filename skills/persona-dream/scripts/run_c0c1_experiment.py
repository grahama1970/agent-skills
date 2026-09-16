#!/usr/bin/env python3
"""Run the preregistered C0/C1 matched experiment end-to-end.

Executes each frozen arm (c0, c1, c1_null, c1_inert) through the landed
machinery — seed -> recall -> admit -> fold — enforces the contract's PASS
conditions per arm, and writes one hash-bound experiment receipt.

Contract: skills/persona-dream/contracts/c0c1_matched_experiment.v1.md
Baseline: skills/persona-dream/contracts/c0c1_baseline.json (digest-frozen
via scripts/c0c1_frozen.py — admission and fold already verify it).

No LLM. Deterministic orchestration only; every step's own receipt is the
evidence, this script only sequences and binds. Exit nonzero if ANY arm
violates its PASS condition (a null result is recorded, not hidden).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
SKILL = SCRIPTS.parent
RUN = SKILL / "run.sh"
BASELINE = SKILL / "contracts" / "c0c1_baseline.json"
CONTRACT = SKILL / "contracts" / "c0c1_matched_experiment.v1.md"
FROZEN = SCRIPTS / "c0c1_frozen.py"

PERSONA = "embry-eval"
USER = "eval-user"
AXIS = "warmth"
QUERY = ("What remembered experiences carry emotion for embry-eval "
         "and could shape how she responds later?")


def _sha(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _step(args: list[str], out_dir: Path, name: str) -> dict:
    """Run one run.sh subcommand; its --receipt file is the evidence."""
    receipt = out_dir / f"{name}.json"
    cmd = [str(RUN), *args, "--receipt", str(receipt)]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=300,
                          cwd=SCRIPTS.parent)
    if not receipt.is_file():
        raise SystemExit(f"EXPERIMENT_INFRA_FAILED {name}: rc={proc.returncode} "
                         f"stderr={proc.stderr[-400:]}")
    return json.loads(receipt.read_text())


def _fold(out_dir: Path, arm: str) -> dict:
    out = out_dir / f"fold_{arm}.json"
    receipt = out_dir / f"fold_{arm}.receipt.json"
    proc = subprocess.run(
        [str(RUN), "fold-persona-state", "--persona", PERSONA, "--user", USER,
         "--arm", arm, "--baseline", str(BASELINE), "--output", str(out),
         "--receipt", str(receipt), "--json"],
        capture_output=True, text=True, timeout=300, cwd=SKILL)
    if not receipt.is_file():
        raise SystemExit(f"EXPERIMENT_INFRA_FAILED fold_{arm}: {proc.stderr[-300:]}")
    return json.loads(receipt.read_text())


def run_arm(arm: str, out_dir: Path) -> dict:
    seed = _step(["seed-c0c1-eval-memory", "--arm", arm, "--reset",
                  "--json"], out_dir, f"seed_{arm}")
    recall = _step(["recall-emotional-triggers", "--persona", PERSONA,
                    "--user", USER, "--query", QUERY, "--k", "12", "--limit", "12",
                    "--output", str(out_dir / f"packet_{arm}.json"), "--json"],
                   out_dir, f"recall_{arm}")
    admit = _step(["admit-persona-state-delta", "--persona", PERSONA,
                   "--axis", AXIS, "--user", USER, "--arm", arm,
                   "--packet", str(out_dir / f"packet_{arm}.json"),
                   "--baseline", str(BASELINE),
                   "--output", str(out_dir / f"admit_out_{arm}.json"), "--json"],
                  out_dir, f"admit_{arm}")
    fold = _fold(out_dir, arm)
    return {"arm": arm, "seed": seed, "recall": recall, "admit": admit,
            "fold": fold}


def check_arm(result: dict) -> list[str]:
    """Enforce the frozen contract's PASS conditions. Returns violations."""
    arm = result["arm"]
    admit, fold = result["admit"], result["fold"]
    v: list[str] = []
    baseline_state = json.loads(BASELINE.read_text())["baseline_state"]
    b = float(baseline_state[AXIS])

    def deltas():  # accepted deltas cited by the fold (delta_citations)
        return fold.get("delta_citations") or fold.get("deltas") or []

    if arm == "c0":
        if admit.get("disposition") != "REJECTED" or admit.get("reason") != "insufficient_distinct_events":
            v.append(f"c0: disposition={admit.get('disposition')}/{admit.get('reason')} != REJECTED/insufficient_distinct_events")
        if admit.get("zero_write_proof", {}).get("no_new_keys") is not True:
            v.append("c0: zero-write not proven")
        if abs(float((fold.get("current_state") or fold.get("state") or {}).get(AXIS, b)) - b) > 1e-9:
            v.append("c0: fold != baseline")
    elif arm == "c1":
        if admit.get("disposition") == "ALREADY_APPLIED":
            # Amendment v1.1 item 3 (replay semantics): valid only when the
            # fold validates the existing delta (cited, bounded, consistent).
            if len(deltas()) != 1:
                v.append(f"c1: replay cites {len(deltas())} deltas, expected 1")
            else:
                d = deltas()[0]
                if abs(float(d.get("delta", 0))) > 0.10 + 1e-9:
                    v.append("c1: replayed |delta| > 0.10")
                after = float((fold.get("current_state") or fold.get("state") or {}).get(AXIS, b))
                if abs(after - (b + float(d.get("delta", 0)))) > 1e-6:
                    v.append("c1: replay fold != baseline + cited delta")
        elif admit.get("disposition") != "ACCEPTED":
            v.append(f"c1: disposition={admit.get('disposition')} reason={admit.get('reason')}")
        else:
            d = abs(float(admit["delta"]))
            if d > 0.10 + 1e-9:
                v.append(f"c1: |delta| {d} > 0.10")
            if admit.get("exact_reread") is not True:
                v.append("c1: accepted delta not exact-reread")
            after = float((fold.get("current_state") or fold.get("state") or {}).get(AXIS, b))
            expected = b + float(admit["delta"])
            if abs(after - expected) > 1e-6:
                v.append(f"c1: fold {after} != baseline+delta {expected}")
            if len(deltas()) != 1:
                v.append(f"c1: fold cites {len(deltas())} deltas, expected 1")
    elif arm == "c1_null":
        if admit.get("disposition") != "REJECTED" or admit.get("reason") != "unknown_intensity_scale":
            v.append(f"c1_null: {admit.get('disposition')}/{admit.get('reason')} != REJECTED/unknown_intensity_scale")
        if admit.get("zero_write_proof", {}).get("no_new_keys") is not True:
            v.append("c1_null: zero-write not proven")
    elif arm == "c1_inert":
        # Amendment v1.1: same bounded ACCEPT as C1 with interpretation_note;
        # replay semantics per v1.1 item 3.
        disp = admit.get("disposition")
        if disp == "ALREADY_APPLIED":
            if len(deltas()) != 1:
                v.append(f"c1_inert: replay cites {len(deltas())} deltas, expected 1")
        elif disp != "ACCEPTED":
            v.append(f"c1_inert: disposition={disp} reason={admit.get('reason')} (v1.1 expects ACCEPTED)")
        elif not admit.get("interpretation_note"):
            v.append("c1_inert: interpretation_note missing")
    return v


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-dir", required=True)
    args = ap.parse_args()
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    sys.path.insert(0, str(SCRIPTS))
    import c0c1_frozen  # noqa: PLC0415 — verifies the capsule digest itself

    results, violations = {}, []
    for arm in ("c0", "c1", "c1_null", "c1_inert"):
        results[arm] = run_arm(arm, out_dir)
        violations += check_arm(results[arm])

    receipt = {
        "schema": "persona_dream.c0c1_experiment_receipt.v1",
        "executed_at": datetime.now(timezone.utc).isoformat(),
        "contract_sha256": _sha(CONTRACT),
        "baseline_sha256": _sha(BASELINE),
        "frozen_baseline_digest": c0c1_frozen.FROZEN_BASELINE_SHA256,
        "arms": {
            arm: {
                "seed_status": r["seed"].get("status"),
                "recall_status": r["recall"].get("status"),
                "admit_disposition": r["admit"].get("disposition"),
                "accept_path": ("fresh_accept" if r["admit"].get("disposition") == "ACCEPTED"
                                else "replay_persisted" if r["admit"].get("disposition") == "ALREADY_APPLIED"
                                else None),
                "admit_reason": r["admit"].get("reason"),
                "admit_delta": r["admit"].get("delta"),
                "fold_state": r["fold"].get("current_state") or r["fold"].get("state"),
                "fold_delta_count": len(r["fold"].get("delta_citations") or r["fold"].get("deltas") or []),
                "receipt_hashes": {
                    n: _sha(out_dir / f"{n}_{arm}.json")
                    for n in ("seed", "recall", "admit")
                },
                "fold_receipt_sha256": _sha(out_dir / f"fold_{arm}.receipt.json"),
            }
            for arm, r in results.items()
        },
        "violations": violations,
        "result": "PASS" if not violations else "FAIL",
    }
    dest = out_dir / "EXPERIMENT_RECEIPT.json"
    dest.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"result": receipt["result"],
                      "violations": violations,
                      "receipt": str(dest)}))
    return 0 if not violations else 1


if __name__ == "__main__":
    raise SystemExit(main())
