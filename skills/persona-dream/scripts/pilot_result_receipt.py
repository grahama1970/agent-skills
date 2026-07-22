#!/usr/bin/env python3
"""Assemble the C-vs-F pilot result receipt under the frozen decision rule.

Inputs (all must exist; fail closed otherwise):
- verified run manifest (pilot_run_manifest.py --verify exits 0 beforehand;
  its sha is embedded)
- per-run metrics receipts (pilot_metrics.py) for R1-C, R1-F, R2-F, R2-C
- per-pair human judgment files + unsealed order mappings
  (pilot_m5_presentation.py unseal must have verified the commitments)
- per-run producer-blinding receipts

Frozen decision rule (protocol v3, unchanged from v2): F wins iff no
regression on M1-M4 AND the operator prefers F on the primary M5 question
("states the central conflict more precisely") in BOTH pairs. Ties or splits
-> NULL. Any invalid run -> INVALID. A NULL result is a valid completion.

The operator's judgment files must be human-authored ("author": "human");
this tool never fabricates or edits them — it only reads and applies the rule.
Output: contracts/pilot_c_vs_f_result_receipt.v1.json.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROTOCOL_V3 = ROOT / "contracts/pilot_c_vs_f_frozen_protocol.v3.md"
# final v3-with-addendum hash, frozen at the pre-run freeze commit
PROTOCOL_V3_FINAL_SHA256 = "483fb1706141c738aca1d57daa65a107df943eb5219a6bd7d0f0fb1d7d0ee0a6"
RUNS = ["R1-C", "R1-F", "R2-F", "R2-C"]
PRIMARY_M5 = "states_central_conflict_more_precisely"


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path: Path, what: str) -> dict:
    if not path.exists():
        print(f"BLOCKED_PILOT_RESULT_MISSING_{what}: {path}", file=sys.stderr)
        raise SystemExit(2)
    return json.loads(path.read_text())


def regression_check(c: dict, f: dict) -> dict:
    """Per-pair M1-M4 no-regression evaluation (F vs its pair's C)."""
    checks = {}
    c_rank, f_rank = c["m1_recall"]["mean_rank_found"], f["m1_recall"]["mean_rank_found"]
    # lower rank better; absent (None) on both = no regression; F absent while
    # C found = regression.
    if f_rank is None and c_rank is not None:
        checks["m1"] = False
    elif f_rank is not None and c_rank is not None:
        checks["m1"] = f_rank <= c_rank
    else:
        checks["m1"] = True
    checks["m1_negative_control"] = f["m1_recall"]["n1_negative_control_pass"]
    checks["m2"] = f["m2_grounding"]["fraction_resolved"] >= c["m2_grounding"]["fraction_resolved"]
    checks["m3"] = bool(f["m3_distinction"]["passed"])
    checks["m4"] = bool(f["m4_identity"]["passed"])
    checks["no_regression"] = all(checks.values())
    return checks


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--metrics-dir", type=Path, required=True,
                        help="dir holding metrics_<RUN>.json for each of R1-C R1-F R2-F R2-C")
    parser.add_argument("--m5-dir", type=Path, required=True,
                        help="dir holding judgment_<pair>.json + unsealed order pair_<pair>_order.json")
    parser.add_argument("--blinding-dir", type=Path, required=True,
                        help="dir holding blinding_<RUN>.json receipts")
    parser.add_argument("--manifest", type=Path,
                        default=ROOT / "contracts/pilot_run_manifest.v2.json")
    parser.add_argument("--m5-waived", action="store_true",
                        help="GOAL_V2_AMENDMENT_1: M5 waived by goal owner; "
                             "no judgment files; result from M1-M4 under the "
                             "frozen rule (F cannot win without M5)")
    parser.add_argument("--scope-notes", type=Path, default=None,
                        help="optional JSON with declared scope notes (e.g. F render boundary)")
    parser.add_argument("--out", type=Path,
                        default=ROOT / "contracts/pilot_c_vs_f_result_receipt.v1.json")
    args = parser.parse_args()

    manifest = load(args.manifest, "RUN_MANIFEST")
    live_v3_sha = sha256_file(PROTOCOL_V3)
    if live_v3_sha != PROTOCOL_V3_FINAL_SHA256:
        print("BLOCKED_PILOT_RESULT_PROTOCOL_V3_DRIFT", file=sys.stderr)
        return 2

    metrics = {}
    invalid = []
    for run in RUNS:
        m = load(args.metrics_dir / f"metrics_{run}.json", f"METRICS_{run}")
        metrics[run] = m
        if m.get("run_invalid"):
            invalid.append(run)

    blinding = {}
    for run in RUNS:
        b = load(args.blinding_dir / f"blinding_{run}.json", f"BLINDING_{run}")
        if b.get("verdict") != "BLINDED":
            print(f"BLOCKED_PILOT_RESULT_BLINDING_NOT_CLEAN: {run}", file=sys.stderr)
            return 2
        blinding[run] = {"sha256": sha256_file(args.blinding_dir / f"blinding_{run}.json"),
                         "shown_concat_sha256": b["shown_concat_sha256"]}

    pairs = {}
    for pair in ("r1", "r2"):
        if args.m5_waived:
            c_run, f_run = f"{pair.upper()}-C", f"{pair.upper()}-F"
            pairs[pair] = {
                "m5_primary_preferred_arm": "WAIVED_BY_GOAL_OWNER",
                "m5_waiver": "GOAL_V2_AMENDMENT_1",
                "sealed_presentation_preserved_unopened": True,
                "regression": regression_check(metrics[c_run], metrics[f_run]),
            }
            continue
        judgment = load(args.m5_dir / f"judgment_{pair}.json", f"JUDGMENT_{pair.upper()}")
        if judgment.get("author") != "human":
            print(f"BLOCKED_PILOT_RESULT_M5_NOT_HUMAN: {pair}", file=sys.stderr)
            return 2
        order = load(args.m5_dir / "sealed" / f"pair_{pair}_order.json", f"ORDER_{pair.upper()}")
        preferred_label = judgment.get(PRIMARY_M5)
        if preferred_label not in ("X", "Y"):
            print(f"BLOCKED_PILOT_RESULT_M5_PRIMARY_ANSWER_INVALID: {pair}", file=sys.stderr)
            return 2
        preferred_arm = order["mapping"][preferred_label]
        c_run, f_run = f"{pair.upper()}-C", f"{pair.upper()}-F"
        pairs[pair] = {
            "m5_primary_preferred_arm": preferred_arm,
            "m5_judgment_sha256": sha256_file(args.m5_dir / f"judgment_{pair}.json"),
            "m5_secondary": {k: judgment.get(k) for k in
                             ("reveals_something_other_does_not", "over_interprets")},
            "regression": regression_check(metrics[c_run], metrics[f_run]),
        }

    if invalid:
        result = "INVALID"
    else:
        # Under the frozen rule F wins only with an M5 preference in BOTH
        # pairs; a goal-owner waiver of M5 therefore makes POSITIVE
        # impossible — the result is NULL (a valid completion).
        f_wins = (not args.m5_waived
                  and all(p["regression"]["no_regression"] for p in pairs.values())
                  and all(p["m5_primary_preferred_arm"] == "F" for p in pairs.values()))
        result = "POSITIVE" if f_wins else "NULL"

    receipt = {
        "schema": "persona_dream.pilot_c_vs_f_result_receipt.v1",
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "published_under": "pilot_c_vs_f_frozen_protocol.v3",
        "protocol_v3_final_sha256": live_v3_sha,
        "post_run_measurement_amendment": "contracts/pilot_post_run_measurement_amendment.v1.md",
        "supersession_lineage": {
            "v1": "superseded pre-run by v2 (tau-dag creator-reviewer review)",
            "v2": "superseded pre-run by v3 (webgpt assess ruling, "
                  "local/webgpt-bundles/pilot-selection-review-assess-response.md)",
        },
        "run_manifest_sha256": manifest["manifest_sha256"],
        "decision_rule": "F wins iff no regression on M1-M4 AND operator prefers F "
                         "on the primary M5 question in BOTH pairs; ties/splits -> NULL",
        "result": result,
        "invalid_runs": invalid,
        "pairs": pairs,
        "per_run_metrics_sha256": {run: sha256_file(args.metrics_dir / f"metrics_{run}.json")
                                   for run in RUNS},
        "producer_blinding": blinding,
        "m5_read_author": ("WAIVED_BY_GOAL_OWNER" if args.m5_waived else "human"),
        "m5_waiver": ("GOAL_V2_AMENDMENT_1" if args.m5_waived else None),
        "scope_notes": (json.loads(args.scope_notes.read_text())
                        if args.scope_notes and args.scope_notes.exists() else None),
    }
    args.out.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"result": result, "out": str(args.out),
                      "pairs": {k: {"m5_primary": v["m5_primary_preferred_arm"],
                                    "no_regression": v["regression"]["no_regression"]}
                                for k, v in pairs.items()}}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
