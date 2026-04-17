#!/usr/bin/env python3
"""
GRPO Training Watchdog

Monitors training progress, detects stalls, and updates task-monitor.
Based on task-monitor's Agent Watchdog Pattern.
"""

import json
import re
import sys
import time
from datetime import datetime
from pathlib import Path

import httpx
from loguru import logger

# Configuration
LOG_FILE = Path("/tmp/grpo_training.log")
STATE_FILE = Path("/tmp/grpo_watchdog_state.json")
TASK_MONITOR_API = "http://localhost:8765"
TASK_NAME = "grpo-intent-mapper"
TOTAL_STEPS = 2000

# Thresholds
STALL_THRESHOLD_SECONDS = 600  # 10 minutes without progress = stall
ERROR_THRESHOLD = 10  # Stop if more than 10 parse errors in a row
CHECK_INTERVAL = 30  # Check every 30 seconds


def parse_training_log() -> dict:
    """Parse the training log for current progress and metrics."""
    if not LOG_FILE.exists():
        return {"step": 0, "progress_pct": 0, "status": "not_started"}

    try:
        content = LOG_FILE.read_text()
        lines = content.strip().split("\n")

        # Find last progress line (e.g., " 30%|███       | 600/2000")
        step = 0
        progress_pct = 0
        step_time = 0
        reward = 0
        loss = 0
        errors = 0

        for line in reversed(lines[-100:]):  # Check last 100 lines
            # Progress bar pattern
            progress_match = re.search(r'(\d+)%\|[█▏▎▍▌▋▊▉ ]+\|\s*(\d+)/(\d+)', line)
            if progress_match and step == 0:
                progress_pct = int(progress_match.group(1))
                step = int(progress_match.group(2))

            # Metrics pattern
            if "'reward':" in line:
                reward_match = re.search(r"'reward':\s*'?([\d.]+)", line)
                if reward_match:
                    reward = float(reward_match.group(1))

            if "'loss':" in line:
                loss_match = re.search(r"'loss':\s*'?([-\d.e]+)", line)
                if loss_match:
                    try:
                        loss = float(loss_match.group(1))
                    except Exception as e:
                        logger.debug("matching failed: {}", e)

            if "'step_time':" in line:
                time_match = re.search(r"'step_time':\s*'?([\d.]+)", line)
                if time_match:
                    step_time = float(time_match.group(1))

            # Error patterns
            if "Failed to parse QuerySpec" in line:
                errors += 1

        # Calculate ETA
        remaining_steps = TOTAL_STEPS - step
        eta_seconds = remaining_steps * step_time if step_time > 0 else 0
        eta_hours = eta_seconds / 3600

        return {
            "step": step,
            "total": TOTAL_STEPS,
            "progress_pct": progress_pct,
            "reward": reward,
            "loss": loss,
            "step_time": step_time,
            "eta_hours": round(eta_hours, 1),
            "errors": errors,
            "status": "running" if step > 0 else "starting",
            "timestamp": datetime.now().isoformat(),
        }
    except Exception as e:
        logger.error(f"Failed to parse log: {e}")
        return {"step": 0, "progress_pct": 0, "status": "error", "error": str(e)}


def load_state() -> dict:
    """Load previous watchdog state."""
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {"last_step": 0, "last_progress_time": datetime.now().isoformat(), "consecutive_errors": 0}


def save_state(state: dict):
    """Save watchdog state."""
    STATE_FILE.write_text(json.dumps(state, indent=2))


def update_task_monitor(metrics: dict):
    """Push metrics to task-monitor API."""
    try:
        # Try API first
        response = httpx.post(
            f"{TASK_MONITOR_API}/tasks/{TASK_NAME}/state",
            json={
                "completed": metrics["step"],
                "total": metrics["total"],
                "rate": 1 / metrics["step_time"] if metrics.get("step_time", 0) > 0 else 0,
                "message": f"reward={metrics.get('reward', 0):.2f}, loss={metrics.get('loss', 0):.4f}",
            },
            timeout=5,
        )
        if response.status_code == 200:
            logger.debug("Updated task-monitor via API")
            return True
    except Exception as e:
        logger.debug(f"API update failed (expected if server not running): {e}")

    # Fallback: write to local state file
    state_path = Path.home() / ".pi" / "task-monitor" / f"{TASK_NAME}.json"
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps({
        "name": TASK_NAME,
        "completed": metrics["step"],
        "total": metrics["total"],
        "status": metrics["status"],
        "updated": metrics["timestamp"],
        "extra": {
            "reward": metrics.get("reward"),
            "loss": metrics.get("loss"),
            "eta_hours": metrics.get("eta_hours"),
        }
    }, indent=2))
    logger.debug("Updated local state file")
    return True


def check_for_stall(metrics: dict, state: dict) -> bool:
    """Check if training has stalled."""
    current_step = metrics["step"]
    last_step = state.get("last_step", 0)

    if current_step > last_step:
        # Progress made, update state
        state["last_step"] = current_step
        state["last_progress_time"] = datetime.now().isoformat()
        state["consecutive_errors"] = 0
        return False

    # No progress - check how long
    last_progress = datetime.fromisoformat(state.get("last_progress_time", datetime.now().isoformat()))
    stall_duration = (datetime.now() - last_progress).total_seconds()

    if stall_duration > STALL_THRESHOLD_SECONDS:
        logger.warning(f"STALL DETECTED: No progress for {stall_duration/60:.1f} minutes")
        return True

    return False


def check_process_running() -> bool:
    """Check if the training process is still running."""
    import subprocess
    result = subprocess.run(
        ["pgrep", "-f", "train_grpo.py"],
        capture_output=True,
        text=True
    )
    return result.returncode == 0


def alert(message: str, level: str = "warning"):
    """Send alert (log for now, could integrate with Discord)."""
    if level == "error":
        logger.error(f"🚨 ALERT: {message}")
    else:
        logger.warning(f"⚠️ ALERT: {message}")

    # TODO: Integrate with Discord via task-monitor discord_publisher
    # For now, just write to a notification file
    alert_file = Path("/tmp/grpo_alerts.log")
    with open(alert_file, "a") as f:
        f.write(f"{datetime.now().isoformat()} [{level.upper()}] {message}\n")


def run_watchdog():
    """Main watchdog loop."""
    logger.info(f"Starting GRPO Training Watchdog")
    logger.info(f"Log file: {LOG_FILE}")
    logger.info(f"Check interval: {CHECK_INTERVAL}s")
    logger.info(f"Stall threshold: {STALL_THRESHOLD_SECONDS}s")

    state = load_state()

    while True:
        try:
            # Check if process is running
            if not check_process_running():
                logger.info("Training process not running - checking if completed")
                metrics = parse_training_log()
                if metrics["step"] >= TOTAL_STEPS - 10:  # Allow some tolerance
                    logger.success(f"🎉 Training COMPLETED at step {metrics['step']}")
                    alert(f"Training completed! Final step: {metrics['step']}", "info")
                    break
                else:
                    alert(f"Training process stopped at step {metrics['step']}/{TOTAL_STEPS}", "error")
                    break

            # Parse current progress
            metrics = parse_training_log()
            logger.info(
                f"Step {metrics['step']}/{metrics['total']} ({metrics['progress_pct']}%) | "
                f"reward={metrics.get('reward', 0):.2f} | "
                f"ETA: {metrics.get('eta_hours', '?')}h"
            )

            # Update task-monitor
            update_task_monitor(metrics)

            # Check for stall
            if check_for_stall(metrics, state):
                alert(f"Training stalled at step {metrics['step']}", "error")
                # Don't exit - training might resume

            # Check error rate
            if metrics.get("errors", 0) > ERROR_THRESHOLD:
                state["consecutive_errors"] = state.get("consecutive_errors", 0) + 1
                if state["consecutive_errors"] > 3:
                    alert(f"High error rate: {metrics['errors']} parse failures", "warning")
            else:
                state["consecutive_errors"] = 0

            # Save state
            save_state(state)

            # Sleep
            time.sleep(CHECK_INTERVAL)

        except KeyboardInterrupt:
            logger.info("Watchdog stopped by user")
            break
        except Exception as e:
            logger.error(f"Watchdog error: {e}")
            time.sleep(CHECK_INTERVAL)

    logger.info("Watchdog exiting")


if __name__ == "__main__":
    # Configure logger
    logger.remove()
    logger.add(
        sys.stderr,
        format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | {message}",
        level="INFO"
    )
    logger.add(
        "/tmp/grpo_watchdog.log",
        rotation="10 MB",
        level="DEBUG"
    )

    run_watchdog()
