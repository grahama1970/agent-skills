#!/usr/bin/env python3
"""Stress test: multi-round recovery (fail → fix → pass).

Mocks _call_llm to return deterministic responses:
  Round 1: wrong code (DoD fails)
  Round 2: correct code (DoD passes)

Verifies the full self-improvement loop:
  - Round 1: score < 0.5, status=keep (first round always kept)
  - Round 2: score = 1.0, DoD passed, status=keep
  - Git: 2 commits (one per kept round)
  - Hunk review: generated with trajectory table
  - Result: pass, rounds=2, dod_passed=True
  - Experiment log: 2 entries with correct scores/strategies
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent


def setup_repo(tmp: Path) -> Path:
    """Create a git repo with a buggy counter.py."""
    repo = tmp / "repo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@test"], cwd=repo, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=repo, capture_output=True)

    (repo / "counter.py").write_text(
        "class Counter:\n"
        "    def __init__(self):\n"
        "        self.value = 0\n"
        "\n"
        "    def increment(self):\n"
        "        self.value += 1\n"
        "\n"
        "    def decrement(self):\n"
        "        self.value -= 1\n"
        "\n"
        "    def reset(self):\n"
        "        pass  # BUG: doesn't reset\n"
    )
    subprocess.run(["git", "add", "counter.py"], cwd=repo, capture_output=True)
    subprocess.run(["git", "commit", "-m", "initial"], cwd=repo, capture_output=True)
    return repo


# Round 1: "fixes" reset but introduces a NEW bug in decrement (off-by-one)
ROUND_1_RESPONSE = """\
### FILE: counter.py
```python
class Counter:
    def __init__(self):
        self.value = 0

    def increment(self):
        self.value += 1

    def decrement(self):
        self.value -= 2  # BUG: decrements by 2

    def reset(self):
        self.value = 0
```
"""

# Round 2: fixes everything correctly
ROUND_2_RESPONSE = """\
### FILE: counter.py
```python
class Counter:
    def __init__(self):
        self.value = 0

    def increment(self):
        self.value += 1

    def decrement(self):
        self.value -= 1

    def reset(self):
        self.value = 0
```
"""


def run_test() -> bool:
    """Run the stress test. Returns True if all assertions pass."""
    tmp = Path(tempfile.mkdtemp(prefix="cr-stress-"))
    try:
        repo = setup_repo(tmp)
        output_dir = tmp / "output"
        output_dir.mkdir()

        # Write task spec
        spec = {
            "task_id": "stress-recovery",
            "title": "Fix Counter reset and verify all methods",
            "prompt": "Fix counter.py: reset() must set value to 0, increment +1, decrement -1",
            "backend": "test",  # will be intercepted
            "cwd": str(repo),
            "output_dir": str(output_dir),
            "allowlist": ["counter.py"],
            "definition_of_done": {
                "command": (
                    f"cd {repo} && python3 -c \""
                    "from counter import Counter; "
                    "c = Counter(); "
                    "c.increment(); c.increment(); c.increment(); "
                    "assert c.value == 3, f'inc: {c.value}'; "
                    "c.decrement(); "
                    "assert c.value == 2, f'dec: {c.value}'; "
                    "c.reset(); "
                    "assert c.value == 0, f'reset: {c.value}'; "
                    "print('ALL PASSED')"
                    "\""
                ),
                "assertion": "ALL PASSED",
            },
            "max_rounds": 3,
        }
        spec_file = tmp / "spec.json"
        spec_file.write_text(json.dumps(spec))

        # Monkeypatch _call_llm by injecting a test backend
        # We do this by writing round responses to files and using a wrapper
        (tmp / "round_responses.json").write_text(json.dumps({
            "1": ROUND_1_RESPONSE,
            "2": ROUND_2_RESPONSE,
            "3": ROUND_2_RESPONSE,
        }))

        # Run code_runner with patched tool_use._mock_response_fn
        env = {**os.environ, "CR_TEST_RESPONSES": str(tmp / "round_responses.json")}

        # Patch tool_use._mock_response_fn to intercept LLM calls in the tool_use loop.
        test_runner = tmp / "run_stress.py"
        test_runner.write_text(f"""\
import sys, json
sys.path.insert(0, {str(SCRIPT_DIR)!r})

import tool_use
import code_runner

_call_count = [0]
_responses = json.loads(open({str(tmp / 'round_responses.json')!r}).read())

def _mock_response_fn(payload):
    _call_count[0] += 1
    call = _call_count[0]

    # Map call numbers to rounds:
    # Each code-runner round makes 2 LLM calls:
    #   1st call: returns FILE block (tool_calls)
    #   2nd call: returns "Done" (no tool_calls, exits loop)
    # Call 1-2 = Round 1, Call 3-4 = Round 2, Call 5-6 = Round 3
    round_num = (call + 1) // 2  # 1->1, 2->1, 3->2, 4->2, 5->3, 6->3

    # Only return FILE response on ODD calls (first call of each round)
    if call % 2 == 1:
        key = str(round_num)
        if key in _responses:
            return _responses[key]
    return "Done - changes applied successfully"

tool_use._mock_response_fn = _mock_response_fn

code_runner.app(["run", {str(spec_file)!r}, "--max-rounds", "3"])
""")

        proc = subprocess.run(
            [sys.executable, str(test_runner)],
            capture_output=True, text=True, timeout=60,
            cwd=str(repo), env=env,
        )

        # ── Assertions ──────────────────────────────────────────────
        errors: list[str] = []

        # 1. Exit code 0 (DoD passed)
        if proc.returncode != 0:
            errors.append(f"exit code {proc.returncode}, expected 0\nstderr: {proc.stderr[:500]}")

        # 2. Result file exists and has correct structure
        result_file = output_dir / "stress-recovery.result.json"
        if not result_file.exists():
            errors.append("result.json missing")
        else:
            result = json.loads(result_file.read_text())

            if result["status"] != "pass":
                errors.append(f"status={result['status']}, expected pass")

            if not result["dod_passed"]:
                errors.append("dod_passed=False, expected True")

            if result["rounds"] < 2:
                errors.append(f"rounds={result['rounds']}, expected >=2 (multi-round recovery)")

            if result["best_score"] < 0.9:
                errors.append(f"best_score={result['best_score']}, expected >=0.9")

            # Round 1 should have failed DoD
            details = result.get("round_details", [])
            if len(details) >= 2:
                r1 = details[0]
                r2 = details[1]

                if r1.get("dod_passed"):
                    errors.append("round 1 dod_passed=True, expected False (mock returns buggy code)")

                if r1["score"] >= 0.5:
                    errors.append(f"round 1 score={r1['score']}, expected <0.5 (DoD failed)")

                if not r2.get("dod_passed"):
                    errors.append("round 2 dod_passed=False, expected True")

                if r2["score"] < 0.9:
                    errors.append(f"round 2 score={r2['score']}, expected >=0.9")

                if r1["strategy"] != "direct_fix":
                    errors.append(f"round 1 strategy={r1['strategy']}, expected direct_fix")

                if r2["strategy"] not in ("structured_analysis", "different_approach"):
                    errors.append(f"round 2 strategy={r2['strategy']}, expected structured_analysis or different_approach")
            else:
                errors.append(f"only {len(details)} round details, expected >=2")

        # 3. Rounds log has entries
        rounds_file = output_dir / "stress-recovery.rounds.jsonl"
        if not rounds_file.exists():
            errors.append("rounds.jsonl missing")
        else:
            rounds = [json.loads(line) for line in rounds_file.read_text().strip().splitlines()]
            if len(rounds) < 2:
                errors.append(f"rounds.jsonl has {len(rounds)} entries, expected >=2")

        # 4. Hunk review generated
        hunk_file = output_dir / "stress-recovery.hunk.md"
        if not hunk_file.exists():
            errors.append("hunk.md missing")
        else:
            hunk = hunk_file.read_text()
            if "Round Trajectory" not in hunk:
                errors.append("hunk.md missing trajectory table")
            if "diff --git" not in hunk:
                errors.append("hunk.md missing diff")

        # 5. Git history shows code-runner commits
        git_log = subprocess.run(
            ["git", "log", "--oneline"], capture_output=True, text=True, cwd=repo,
        ).stdout
        cr_commits = [l for l in git_log.splitlines() if "code-runner:" in l]
        if len(cr_commits) < 1:
            errors.append(f"expected >=1 code-runner commits, got {len(cr_commits)}")

        # 6. Final counter.py is correct
        final_code = (repo / "counter.py").read_text()
        if "self.value -= 2" in final_code:
            errors.append("final counter.py still has the round-1 bug (decrement by 2)")
        if "pass  # BUG" in final_code:
            errors.append("final counter.py still has original reset bug")

        return errors

    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    print("=== /code-runner stress test: multi-round recovery ===")
    errors = run_test()
    if errors:
        for e in errors:
            print(f"  FAIL: {e}")
        print(f"=== FAILED ({len(errors)} errors) ===")
        sys.exit(1)
    else:
        print("  PASS: round 1 fails DoD (buggy mock response)")
        print("  PASS: round 2 passes DoD (correct mock response)")
        print("  PASS: strategy escalation (direct_fix → structured_analysis)")
        print("  PASS: result.json correct (pass, >=2 rounds, dod_passed)")
        print("  PASS: hunk.md has trajectory + diff")
        print("  PASS: git history has code-runner commits")
        print("  PASS: final code is correct (no round-1 bug)")
        print("=== ALL PASSED ===")
