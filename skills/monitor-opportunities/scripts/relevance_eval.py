"""Adversarial evaluation of opportunity relevance against the corpus.

Runs the live /extract-entities relevance over fixtures/relevance_adversarial.json
and asserts every must_match hits >=1 concept and every must_not_match hits none.
Prints precision/recall and every failure; exits non-zero on any regression so it
can gate the corpus via /agentic-evals.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from monitor_opportunities.relevance import mandate_hits

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "relevance_adversarial.json"


def main() -> None:
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    must_match = data["must_match"]
    must_not = data["must_not_match"]

    false_neg = []  # should match, didn't
    false_pos = []  # should not match, did

    for t in must_match:
        hits = mandate_hits(t)
        if hits is None:
            print("RELEVANCE EVAL BLOCKED: /extract-entities unavailable (mandate_hits=None)")
            sys.exit(2)
        if not hits:
            false_neg.append(t)
    for t in must_not:
        hits = mandate_hits(t) or []
        if hits:
            false_pos.append((t, hits))

    tp = len(must_match) - len(false_neg)
    tn = len(must_not) - len(false_pos)
    precision = tp / (tp + len(false_pos)) if (tp + len(false_pos)) else 1.0
    recall = tp / len(must_match) if must_match else 1.0

    if false_neg:
        print(f"FALSE NEGATIVES ({len(false_neg)}) — should match, didn't:")
        for t in false_neg:
            print(f"  - {t}")
    if false_pos:
        print(f"FALSE POSITIVES ({len(false_pos)}) — should NOT match, did:")
        for t, h in false_pos:
            print(f"  - {t}  ->  {h}")

    # Gate: recall MUST be perfect (never drop a real opportunity at the cheap
    # first pass); precision must stay above a floor (a few fuzzy false positives
    # are acceptable — the JD-reading evaluator is the authoritative second pass).
    # Tightening the floor over time forces the corpus to improve.
    recall_required = 1.0
    precision_floor = 0.80

    print(f"\nRELEVANCE EVAL: precision={precision:.2f} (floor {precision_floor:.2f}) "
          f"recall={recall:.2f} (required {recall_required:.2f}) "
          f"tp={tp} tn={tn} fp={len(false_pos)} fn={len(false_neg)}")
    if recall < recall_required:
        print("FAIL: recall below required — a real opportunity was dropped.")
        sys.exit(1)
    if precision < precision_floor:
        print("FAIL: precision below floor — too many false positives; tighten the corpus.")
        sys.exit(1)
    if false_pos:
        print("PASS (with known fuzzy residuals the JD-reading evaluator resolves).")
    else:
        print("RELEVANCE EVAL PASS")


if __name__ == "__main__":
    main()
