"""Batch-learn chart design examples into /memory for /create-architecture skill."""

import subprocess
import sys

from chart_examples_bad import BAD
from chart_examples_good import GOOD

SCOPE = "pi-mono"
BASE_TAGS = ["chart-design", "create-architecture", "excalidraw"]


def learn(problem: str, solution: str, tags: list[str]):
    """Call memory-agent learn with the given problem/solution."""
    cmd = [
        sys.executable, "-m", "graph_memory.agent_cli", "learn",
        "-p", problem,
        "-s", solution,
        "--scope", SCOPE,
    ]
    for t in BASE_TAGS + tags:
        cmd.extend(["-t", t])
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    status = "OK" if result.returncode == 0 else "FAIL"
    print(f"  [{status}] {problem[:80]}...")
    if result.returncode != 0:
        print(f"    stderr: {result.stderr[:200]}")


def main():
    print(f"Learning {len(GOOD)} good examples + {len(BAD)} bad examples...")
    print()

    print("=== GOOD EXAMPLES ===")
    for i, ex in enumerate(GOOD, 1):
        print(f"[{i}/{len(GOOD)}]", end=" ")
        learn(ex["problem"], ex["solution"], ex["tags"])

    print()
    print("=== BAD EXAMPLES ===")
    for i, ex in enumerate(BAD, 1):
        print(f"[{i}/{len(BAD)}]", end=" ")
        learn(ex["problem"], ex["solution"], ex["tags"])

    print()
    print(f"Done. {len(GOOD)} good + {len(BAD)} bad = {len(GOOD) + len(BAD)} total examples learned.")


if __name__ == "__main__":
    main()
