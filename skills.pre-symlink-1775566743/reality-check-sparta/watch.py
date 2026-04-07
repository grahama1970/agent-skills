#!/usr/bin/env python3
"""SPARTA QRA Batch Checkpoint Monitor.

Watches a running QRA batch and triggers reality-check-sparta at regular
checkpoint intervals (e.g., every 10K QRAs).

Design Decisions:
- Uses LOG PARSING instead of DB queries to avoid lock contention
- Only counts entries AFTER the latest "RESUME:" line (current run only)
- Triggers full reality check at each checkpoint
- Stores results to /memory for progression tracking
- Stops batch on FAIL, continues on PASS/WARN

Usage:
    python watch.py --run-id run-recovery-verify --checkpoint 10000

Integration with reality-check-sparta:
    ./run.sh watch --run-id run-recovery-verify --checkpoint 10000
"""

import typer
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple
from loguru import logger

# Paths
SPARTA_DIR = Path(os.environ.get("SPARTA_DIR", str(Path.home() / "workspace/experiments/sparta")))
SCRIPT_DIR = Path(__file__).parent
CHECK_SCRIPT = SCRIPT_DIR / "check.py"


def log(message: str) -> None:
    """Log with timestamp."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] {message}", flush=True)


def get_log_path(run_id: str) -> Path:
    """Get the log path for a run."""
    return SPARTA_DIR / "data" / "runs" / run_id / "logs" / "12_qra.log"


def get_resume_line(log_path: Path) -> int:
    """Find the line number of the last RESUME entry."""
    if not log_path.exists():
        return 1

    try:
        result = subprocess.run(
            ["grep", "-n", "RESUME: Found", str(log_path)],
            capture_output=True,
            text=True,
            env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
        )
        if result.stdout:
            lines = result.stdout.strip().split("\n")
            last_line = lines[-1]
            return int(last_line.split(":")[0])
    except Exception as e:
        logger.debug("value lookup failed: {}", e)
    return 1


def get_baseline_count(log_path: Path) -> int:
    """Parse baseline QRA count from RESUME line."""
    if not log_path.exists():
        return 0

    try:
        result = subprocess.run(
            ["grep", "-o", "RESUME: Found [0-9]* existing QRAs", str(log_path)],
            capture_output=True,
            text=True,
            env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
        )
        if result.stdout:
            lines = result.stdout.strip().split("\n")
            last_line = lines[-1]
            match = re.search(r"(\d+)", last_line)
            if match:
                return int(match.group(1))
    except Exception as e:
        logger.debug("matching failed: {}", e)
    return 0


def get_current_qra_count(log_path: Path, baseline: int) -> int:
    """Parse current QRA count from log (entries after RESUME line only)."""
    resume_line = get_resume_line(log_path)

    try:
        # Get lines after RESUME
        result = subprocess.run(
            ["tail", "-n", f"+{resume_line}", str(log_path)],
            capture_output=True,
            text=True,
            env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
        )
        content = result.stdout

        # Sum all "Phase X complete: Y QRAs" entries
        matches = re.findall(r"Phase \d+ complete: (\d+) QRAs", content)
        phase_total = sum(int(m) for m in matches)

        return baseline + phase_total
    except Exception:
        return baseline


def get_progress_rate(log_path: Path) -> str:
    """Calculate QRAs per minute from log timestamps."""
    resume_line = get_resume_line(log_path)

    try:
        result = subprocess.run(
            ["tail", "-n", f"+{resume_line}", str(log_path)],
            capture_output=True,
            text=True,
            env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
        )
        content = result.stdout

        # Find Phase complete entries with timestamps
        pattern = r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}).*Phase \d+ complete: (\d+) QRAs"
        matches = re.findall(pattern, content)

        if len(matches) >= 2:
            first_ts = datetime.strptime(matches[0][0], "%Y-%m-%d %H:%M:%S")
            last_ts = datetime.strptime(matches[-1][0], "%Y-%m-%d %H:%M:%S")
            elapsed = (last_ts - first_ts).total_seconds()

            if elapsed > 0:
                total_qras = sum(int(m[1]) for m in matches)
                rate = total_qras * 60 / elapsed
                return f"{rate:.1f} QRAs/min"
    except Exception as e:
        logger.debug("value lookup failed: {}", e)

    return "calculating..."


def is_batch_running(run_id: str) -> bool:
    """Check if the batch process is still running."""
    try:
        result = subprocess.run(
            ["pgrep", "-f", "12_qra"],
            capture_output=True,
            text=True,
            env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
        )
        return result.returncode == 0
    except Exception:
        return False


def run_reality_check(run_id: str, samples: int, store: bool = True) -> Tuple[bool, dict]:
    """Run reality-check-sparta and return (passed, results)."""
    log("Running reality-check-sparta (Brandon review)...")

    cmd = [
        "uv", "run", "python", str(CHECK_SCRIPT),
        "--db", str(SPARTA_DIR / "data" / "runs" / run_id / "sparta.duckdb"),
        "--run-id", run_id,
        "--samples", str(samples),
        "--json",
        "--suggest-fixes",
    ]
    if store:
        cmd.append("--store")

    try:
        os.chdir(SPARTA_DIR)
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300,
            env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
        )

        # Parse JSON output
        output = result.stdout

        # Find JSON in output (may have other text before it)
        json_start = output.find("{")
        if json_start >= 0:
            json_str = output[json_start:]
            # Find matching closing brace
            brace_count = 0
            json_end = 0
            for i, c in enumerate(json_str):
                if c == "{":
                    brace_count += 1
                elif c == "}":
                    brace_count -= 1
                    if brace_count == 0:
                        json_end = i + 1
                        break

            if json_end > 0:
                results = json.loads(json_str[:json_end])
                overall_status = results.get("overall_status", "UNKNOWN")
                passed = overall_status in ("PASS", "WARN")
                return passed, results

        # If we can't parse JSON, check return code
        passed = result.returncode == 0
        return passed, {"raw_output": output, "returncode": result.returncode}

    except subprocess.TimeoutExpired:
        log("Reality check timed out after 5 minutes")
        return False, {"error": "timeout"}
    except Exception as e:
        log(f"Reality check error: {e}")
        return False, {"error": str(e)}


def watch_batch(
    run_id: str,
    checkpoint: int = 10000,
    samples: int = 30,
    check_interval: int = 60,
    store: bool = True,
) -> int:
    """
    Watch a running batch and trigger reality checks at checkpoints.

    Returns:
        0 if batch completes successfully
        1 if reality check fails
        2 if batch crashes/stalls
    """
    log("=" * 60)
    log("SPARTA QRA BATCH CHECKPOINT MONITOR")
    log("=" * 60)

    log_path = get_log_path(run_id)
    if not log_path.exists():
        log(f"ERROR: Log file not found: {log_path}")
        return 2

    baseline = get_baseline_count(log_path)
    log(f"Run ID: {run_id}")
    log(f"Log: {log_path}")
    log(f"Baseline QRA count: {baseline}")
    log(f"Checkpoint interval: every {checkpoint} QRAs")
    log(f"Check interval: {check_interval}s")
    log(f"Samples per check: {samples}")
    log("")

    next_checkpoint = baseline + checkpoint
    phase = 1
    last_count = baseline
    first_progress_seen = False
    stall_checks = 0
    max_stall_checks = 10  # 10 minutes of no progress before considering stalled

    while True:
        current_count = get_current_qra_count(log_path, baseline)
        rate = get_progress_rate(log_path)
        new_qras = current_count - last_count

        log(f"QRAs: {current_count} (+{new_qras} since last) | Rate: {rate} | Next checkpoint: {next_checkpoint}")

        # Wait for first progress before considering checkpoints
        if current_count == baseline and not first_progress_seen:
            log("Waiting for first progress entries...")
            last_count = current_count
            time.sleep(check_interval)
            continue

        first_progress_seen = True

        # Check if we've hit a checkpoint
        if current_count >= next_checkpoint:
            log("")
            log("=" * 60)
            log(f"CHECKPOINT REACHED: {current_count} QRAs (Phase {phase})")
            log("=" * 60)

            passed, results = run_reality_check(run_id, samples, store)

            if passed:
                status = results.get("overall_status", "UNKNOWN")
                log(f"Phase {phase} validation {status} - continuing...")
                phase += 1
                next_checkpoint = current_count + checkpoint
                last_count = current_count
                stall_checks = 0
            else:
                status = results.get("overall_status", "FAIL")
                log(f"Phase {phase} validation FAILED ({status})")
                log("Stopping batch - investigate issues before resuming.")

                # Show issues
                issues = results.get("all_issues", [])
                if issues:
                    log("")
                    log("Issues found:")
                    for issue in issues[:10]:
                        log(f"  - {issue}")
                    if len(issues) > 10:
                        log(f"  ... and {len(issues) - 10} more")

                return 1

        # Check for stall (no new QRAs)
        if new_qras == 0:
            stall_checks += 1

            # Check if batch process is still running
            if not is_batch_running(run_id):
                log("")
                log("Batch process not running - may have completed or crashed")
                log(f"Final count: {current_count} QRAs")

                # Run final reality check
                log("Running final reality check...")
                passed, results = run_reality_check(run_id, samples, store)

                if passed:
                    log("Final validation PASSED")
                    return 0
                else:
                    log("Final validation FAILED")
                    return 1

            if stall_checks >= max_stall_checks:
                log(f"WARNING: No progress for {max_stall_checks * check_interval}s - batch may be stalled")
                stall_checks = 0  # Reset and keep watching
        else:
            stall_checks = 0

        last_count = current_count
        time.sleep(check_interval)


app = typer.Typer(help="Watch SPARTA QRA batch and trigger reality checks at checkpoints")


@app.command()
def main(
    run_id: str = typer.Option(..., help="Pipeline run ID"),
    checkpoint: int = typer.Option(10000, help=""),
    samples: int = typer.Option(30, help=""),
    interval: int = typer.Option(60, help=""),
    no_store: bool = typer.Option(False, help="Don"),
):
    exit_code = watch_batch(
        run_id=run_id,
        checkpoint=checkpoint,
        samples=samples,
        check_interval=interval,
        store=not no_store,
    )

    sys.exit(exit_code)


if __name__ == "__main__":
    app()
