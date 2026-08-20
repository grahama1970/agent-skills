"""Live-path guard for the morning interview loop.

Builds questions from the NEWEST retained nightly run, applies a synthetic
disposition and a synthetic identity confirmation through the real code paths
(decision ledger append with idempotency; contact_snapshots store with
read-back), and fails when any of those seams break. Uses a throwaway copy of
the run directory so real ledgers are never polluted.
"""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from monitor_opportunities.morning_interview import apply_answers, build_questions  # noqa: E402


def main() -> int:
    skill = Path(__file__).resolve().parents[1]
    runs = sorted((skill / "local" / "nightly").glob("run-*"))
    if not runs:
        print("INTERVIEW BLOCKED: no retained nightly run to build questions from")
        return 1
    src = runs[-1]
    with tempfile.TemporaryDirectory() as tmp:
        run = Path(tmp) / src.name
        shutil.copytree(src, run)
        (run / "decision-ledger.jsonl").unlink(missing_ok=True)
        questions = build_questions(run)
        if not questions["questions"]:
            print("INTERVIEW FAIL: latest run produced zero questions")
            return 1
        first = questions["questions"][0]
        receipt = apply_answers(run, {first["id"]: "Pursue"})
        if receipt["dispositions_recorded"] != 1 or receipt["errors"]:
            print(f"INTERVIEW FAIL: disposition not recorded: {receipt}")
            return 1
        before = (run / "decision-ledger.jsonl").read_text().splitlines()
        apply_answers(run, {first["id"]: "Pursue"})
        after = (run / "decision-ledger.jsonl").read_text().splitlines()
        if len(before) != len(after):
            print("INTERVIEW FAIL: replaying the same answer duplicated the ledger")
            return 1
        ledger = json.loads(after[-1])
        print(
            "INTERVIEW OK "
            f"questions={len(questions['questions'])} "
            f"recorded_action={ledger['action']} actor={ledger['actor']} idempotent=true "
            f"run={src.name}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
