"""Status reporting for ask knowledge counts and task-monitor learning progress."""

#!/usr/bin/env python3
"""
/ask status — Show learning progress for a scope.

Queries memory to show what's been learned and from what sources.
Also shows task-monitor state if available.
"""

import typer
import json
import os
import subprocess
import sys
from pathlib import Path

from loguru import logger as log

app = typer.Typer(help="/ask status - Show learning progress")

SKILL_ROOT = Path(__file__).resolve().parents[2]
SKILLS_DIR = SKILL_ROOT.parent
AGENT_SKILLS_DIR = SKILLS_DIR.parent / ".agent" / "skills"
STATE_FILE = SKILL_ROOT / "ask_task_state.json"

def run_memory_recall(query: str, scope: str, k: int = 5, timeout: int = 15) -> dict:
    """Run memory recall through the memory skill."""
    return run_skill("memory", ["recall", "--q", query, "--scope", scope, "--k", str(k)], timeout=timeout)


def run_skill(name: str, args: list[str], timeout: int = 30) -> dict:
    """Run a skill via its run.sh and capture output."""
    candidates = [
        SKILLS_DIR / name / "run.sh",
        AGENT_SKILLS_DIR / name / "run.sh",
    ]

    script = None
    for c in candidates:
        if c.exists():
            script = c
            break

    if not script:
        log.warning("Skill '%s' not found", name)
        return {"returncode": -1, "stdout": "", "stderr": f"Skill {name} not found", "skipped": True}

    try:
        result = subprocess.run(
            [str(script)] + args,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(script.parent),
            env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
        )
        return {
            "returncode": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "skipped": False,
        }
    except subprocess.TimeoutExpired:
        log.error("Skill '%s' timed out", name)
        return {"returncode": -2, "stdout": "", "stderr": f"Skill {name} timed out", "skipped": False}
    except Exception as e:
        log.error("Skill '%s' failed: %s", name, e)
        return {"returncode": -3, "stdout": "", "stderr": str(e), "skipped": False}


def parse_memory_output(stdout: str) -> list[dict]:
    """Parse memory recall output into structured items.

    Handles pretty-printed JSON (multi-line), offset JSON, and JSONL.
    """
    stdout = stdout.strip()
    if not stdout:
        return []

    # First, try parsing the entire output as a single JSON document
    try:
        data = json.loads(stdout)
        if isinstance(data, dict) and "items" in data:
            return data["items"]
        if isinstance(data, dict) and ("problem" in data or "solution" in data):
            return [data]
    except json.JSONDecodeError:
        pass

    # Fallback: try to find JSON starting from first '{'
    json_start = stdout.find("{")
    if json_start >= 0:
        try:
            data = json.loads(stdout[json_start:])
            if isinstance(data, dict) and "items" in data:
                return data["items"]
        except json.JSONDecodeError:
            pass

    # Last resort: line-by-line (for JSONL)
    items = []
    for line in stdout.split("\n"):
        line = line.strip()
        if line.startswith("{"):
            try:
                data = json.loads(line)
                if "items" in data:
                    return data["items"]
                elif "problem" in data or "solution" in data:
                    items.append(data)
            except json.JSONDecodeError:
                continue

    return items


def show_status(scope: str = "ask", as_json: bool = False):
    """Show what has been learned in a given scope."""
    # Query memory for everything in scope
    queries = [
        "What has been learned?",
        "books discovered topics",
        "YouTube lectures transcripts",
        "behavioral psychology neuroscience",
    ]

    all_items = []
    seen_problems = set()

    for q in queries:
        result = run_memory_recall(q, scope, k=20, timeout=15)

        if result["returncode"] == 0:
            items = parse_memory_output(result["stdout"])
            for item in items:
                problem = item.get("problem", "")
                if problem and problem not in seen_problems:
                    all_items.append(item)
                    seen_problems.add(problem)

    # Categorize items
    categories = {
        "learning_sessions": [],
        "qra_pairs": [],
        "other": [],
    }

    for item in all_items:
        problem = item.get("problem", "").lower()
        if "what has been learned" in problem or "learning session" in problem:
            categories["learning_sessions"].append(item)
        elif "?" in problem:
            categories["qra_pairs"].append(item)
        else:
            categories["other"].append(item)

    status = {
        "scope": scope,
        "total_items": len(all_items),
        "learning_sessions": len(categories["learning_sessions"]),
        "qra_pairs": len(categories["qra_pairs"]),
        "other": len(categories["other"]),
    }

    # Check task-monitor state
    monitor_state = None
    if STATE_FILE.exists():
        try:
            monitor_state = json.loads(STATE_FILE.read_text())
            status["monitor"] = {
                "status": monitor_state.get("status", "unknown"),
                "progress_pct": monitor_state.get("progress_pct", 0),
                "elapsed_seconds": monitor_state.get("elapsed_seconds", 0),
                "last_updated": monitor_state.get("last_updated", ""),
                "step_status": monitor_state.get("step_status", {}),
                "stats": monitor_state.get("stats", {}),
            }
        except (json.JSONDecodeError, OSError):
            pass

    if as_json:
        status["items"] = all_items
        print(json.dumps(status, indent=2, default=str))
        return

    print(f"\n── /ask status: scope={scope} ──\n")
    print(f"  Total knowledge items: {status['total_items']}")
    print(f"  Learning sessions:     {status['learning_sessions']}")
    print(f"  Q-R-A pairs:           {status['qra_pairs']}")
    print(f"  Other items:           {status['other']}")

    if categories["learning_sessions"]:
        print(f"\n  Learning Sessions:")
        for item in categories["learning_sessions"][:5]:
            solution = item.get("solution", "")[:100]
            print(f"    - {solution}")

    if categories["qra_pairs"]:
        print(f"\n  Recent Questions Learned:")
        for item in categories["qra_pairs"][:10]:
            problem = item.get("problem", "")[:70]
            print(f"    - {problem}")

    # Show task-monitor state
    if monitor_state:
        print(f"\n  Last Task Monitor:")
        print(f"    Status:   {monitor_state.get('status', 'unknown')}")
        print(f"    Topic:    {monitor_state.get('topic', 'unknown')}")
        print(f"    Progress: {monitor_state.get('progress_pct', 0):.0f}%")
        print(f"    Elapsed:  {monitor_state.get('elapsed_seconds', 0):.1f}s")
        steps = monitor_state.get("step_status", {})
        if steps:
            step_line = " | ".join(f"{k}:{v}" for k, v in steps.items())
            print(f"    Steps:    {step_line}")
        stats = monitor_state.get("stats", {})
        if stats:
            stats_line = " | ".join(f"{k}={v}" for k, v in stats.items())
            print(f"    Stats:    {stats_line}")

    if not all_items:
        print(f"\n  No knowledge found in scope '{scope}'.")
        print(f"  Start learning: ./run.sh learn \"topic\" --scope {scope}")
        print(f"  Or auto-learn:  ./run.sh ask \"question\" --scope {scope} --auto-learn")

    print()


@app.command()
def main(
    scope: str = typer.Option(os.environ.get("ASK_DEFAULT_SCOPE", "ask"), help="Memory scope to check (default: ask)"),
    as_json: bool = typer.Option(False, "--json", help="JSON output"),
    debug: bool = typer.Option(False, help="Enable debug logging"),
):
    if debug:
        log.enable("")

    show_status(scope=scope, as_json=as_json)


if __name__ == "__main__":
    app()
