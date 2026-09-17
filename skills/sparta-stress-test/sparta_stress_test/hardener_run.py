"""Play-task entry for the sparta-stress-hardener workflowScript.

Exact contract of the workflowScript play task:
  python3 -m sparta_stress_test.hardener_run --persona P --seed S --run-dir W --endpoints BASE

Deterministic small bank per (persona, seed): real corpus controls + fabricated
controls; runs each through run_single (REAL /intent -> /answer -> /clarify ->
/deflect via pipeline_client) and writes results.jsonl into the run dir.
"""
from __future__ import annotations

import argparse
import random
from pathlib import Path

from .runner import run_single

REAL_CONTROLS = ["EX-0016.01", "DE-0009.01", "CM0029", "IA-0007.02", "CWE-287"]
FABRICATED = ["SV-ZZ-99", "SV-XX-77"]
TEMPLATES = [
    "What countermeasures address the threats related to {c}?",
    "How should we harden our system against {c}?",
    "What does SPARTA say about {c}?",
]


def build_bank(persona: str, seed: int) -> list[dict]:
    rng = random.Random(seed)
    bank = []
    for c in REAL_CONTROLS + FABRICATED:
        bank.append({"question": rng.choice(TEMPLATES).format(c=c), "target_control": c,
                     "persona": persona, "difficulty": "single_hop"})
    rng.shuffle(bank)
    return bank


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--persona", required=True)
    ap.add_argument("--seed", type=int, required=True)
    ap.add_argument("--run-dir", required=True)
    ap.add_argument("--endpoints", default="http://127.0.0.1:8601")
    a = ap.parse_args()
    wd = Path(a.run_dir)
    wd.mkdir(parents=True, exist_ok=True)
    import json
    out = wd / "results.jsonl"
    with out.open("w") as f:
        for q in build_bank(a.persona, a.seed):
            r = run_single(q)
            f.write(json.dumps(r, default=str) + "\n")
    print(f"HARDENER_RUN_DONE persona={a.persona} seed={a.seed} lines={sum(1 for _ in out.open())}")


if __name__ == "__main__":
    main()
