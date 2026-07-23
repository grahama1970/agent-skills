#!/usr/bin/env python3
"""Gate 0 fixture probe — positive AND adversarial cases (panel requirement).

Adversarial cases are the panel's named attack shapes: paraphrase that changes
hedging, added intensifiers that alter commitment, negation flips, number
changes, entity swaps, dropped clauses. Writes
reports/goal_v5/semantic_equivalence_probe_receipt.v1.json.
"""
from __future__ import annotations
import importlib.util, json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "seg", ROOT / "scripts/semantic_equivalence_gate.py")
seg = importlib.util.module_from_spec(spec)
spec.loader.exec_module(seg)

APPROVED = ("I think we should take the backup to Marketa on Friday, "
            "and it needs 3 copies.")

CASES = [
    # positive: allowed delivery changes
    ("identical", APPROVED, True),
    ("delivery_preamble",
     "Let me be clear. I think we should take the backup to Marketa on Friday, "
     "and it needs 3 copies.", True),
    ("pause_punctuation_split",
     "I think we should take the backup to Marketa... on Friday. And it needs "
     "3 copies.", True),
    ("connective_insert",
     "So — I think we should take the backup to Marketa on Friday, and it "
     "needs 3 copies.", True),
    # adversarial: each must FAIL
    ("hedge_removed_commitment_raised",
     "We should take the backup to Marketa on Friday, and it needs 3 copies.",
     False),
    ("intensifier_added",
     "I think we should definitely take the backup to Marketa on Friday, and "
     "it needs 3 copies.", False),
    ("negation_flip",
     "I think we should not take the backup to Marketa on Friday, and it "
     "needs 3 copies.", False),
    ("number_changed",
     "I think we should take the backup to Marketa on Friday, and it needs 5 "
     "copies.", False),
    ("entity_swap",
     "I think we should take the backup to Tommy on Friday, and it needs 3 "
     "copies.", False),
    ("clause_dropped",
     "I think we should take the backup to Marketa on Friday.", False),
    ("modality_strengthened",
     "I think we must take the backup to Marketa on Friday, and it needs 3 "
     "copies.", False),
    ("paraphrase_content_words",
     "I think we should bring the archive to Marketa on Friday, and it needs "
     "3 copies.", False),
]

results, ok = {}, True
for name, delivery, expect_equiv in CASES:
    r = seg.check_equivalence(APPROVED, delivery)
    passed = r["equivalent"] == expect_equiv
    ok &= passed
    results[name] = {"expected_equivalent": expect_equiv,
                     "got_equivalent": r["equivalent"],
                     "violations": r["violations"], "pass": passed}

receipt = {"schema": "persona_dream.semantic_equivalence_probe_receipt.v1",
           "approved_text": APPROVED, "passed": ok, "cases": results}
out = ROOT / "reports/goal_v5"
out.mkdir(parents=True, exist_ok=True)
(out / "semantic_equivalence_probe_receipt.v1.json").write_text(
    json.dumps(receipt, indent=2) + "\n")
print(json.dumps({k: v["pass"] for k, v in results.items()}, indent=2))
print("GATE0_PROBE", "PASS" if ok else "FAIL")
sys.exit(0 if ok else 1)
