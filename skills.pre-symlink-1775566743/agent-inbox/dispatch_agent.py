"""
Agent-Inbox Dispatcher - Agent spawning, verification, completion, and daemon loop.

Contains spawn_agent, verify_fix, complete_fix, dispatch_loop, daemon_status,
stop_daemon, and supporting functions.
"""

import json
import os
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple

from dispatch_core import (
    MODEL_COMMANDS,
    INBOX_DIR,
    LOG_DIR,
    get_project_path,
    recall_from_memory,
    _learn_solution,
    build_prompt,
)
from loguru import logger


PID_FILE = INBOX_DIR / "dispatcher.pid"
_running = True  # Global flag for graceful shutdown


def spawn_agent(
    message: dict,
    project_path: Optional[Path] = None,
    dry_run: bool = False,
) -> Tuple[Optional[int], Optional[str]]:
    """Spawn a detached headless agent to process a message.

    Args:
        message: Message dict with dispatch config
        project_path: Path to run the agent in (defaults to lookup from registry)
        dry_run: If True, print command but don't execute

    Returns:
        (Process ID, log_file) if spawned, (None, None) if dry_run or error
    """
    msg_id = message.get("id", "unknown")
    to_project = message.get("to", "unknown")
    dispatch = message.get("dispatch", {})
    model = dispatch.get("model", "sonnet")
    timeout_minutes = dispatch.get("timeout_minutes", 30)

    if model not in MODEL_COMMANDS:
        print(f"[dispatcher] Error: Unknown model '{model}'")
        return None, None

    cmd_base = MODEL_COMMANDS[model].copy()

    if project_path is None:
        project_path = get_project_path(to_project)
        if project_path is None:
            print(f"[dispatcher] Error: Project '{to_project}' not registered")
            print(f"[dispatcher] Register with: agent-inbox register {to_project} /path/to/project")
            return None, None

    # PRE-HOOK: Query memory for similar bugs and solutions
    print(f"[dispatcher] Querying memory for similar issues...")
    bug_description = message.get("message", "")
    memory_context = recall_from_memory(bug_description, project_path)

    prompt = build_prompt(message, memory_context=memory_context)

    cmd = cmd_base + ["--no-session", "-p", prompt]

    if dry_run:
        print(f"[dispatcher] Would run in {project_path}:")
        print(f"[dispatcher] {' '.join(cmd[:5])}... (prompt truncated)")
        return None, None

    LOG_DIR.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    log_file = LOG_DIR / f"{msg_id}_{timestamp}.log"

    print(f"[dispatcher] Spawning {model} agent for {msg_id}")
    print(f"[dispatcher] Working directory: {project_path}")
    print(f"[dispatcher] Log file: {log_file}")

    try:
        with open(log_file, "w") as log_f:
            log_f.write(f"# Dispatch log for {msg_id}\n")
            log_f.write(f"# Model: {model}\n")
            log_f.write(f"# Project: {to_project}\n")
            log_f.write(f"# Started: {datetime.now(timezone.utc).isoformat()}\n")
            log_f.write(f"# Command: {' '.join(cmd[:5])}...\n")
            log_f.write("\n--- Prompt ---\n")
            log_f.write(prompt)
            log_f.write("\n\n--- Output ---\n")
            log_f.flush()

            process = subprocess.Popen(
                cmd,
                cwd=project_path,
                stdout=log_f,
                stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
                start_new_session=True,
            )

            print(f"[dispatcher] Started process {process.pid}")

            try:
                from . import inbox
            except ImportError:
                import inbox
            inbox.update_status(msg_id, "dispatched", note=f"PID: {process.pid}")

            return process.pid, str(log_file)

    except Exception as e:
        print(f"[dispatcher] Error spawning agent: {e}")
        return None, None


def get_dispatch_log(msg_id: str) -> Optional[str]:
    """Get the most recent dispatch log for a message.

    Args:
        msg_id: Message ID

    Returns:
        Log file content, or None if not found
    """
    if not LOG_DIR.exists():
        return None

    logs = sorted(LOG_DIR.glob(f"{msg_id}_*.log"), reverse=True)
    if logs:
        return logs[0].read_text()
    return None


def verify_fix(message: dict, project_path: Optional[Path] = None) -> tuple:
    """Run verification command to check if fix is successful.

    If dispatch.test_command is set, runs it in the project directory.
    On success, allows auto-ack. On failure, sets status to needs_verification.

    Args:
        message: Message dict with dispatch.test_command
        project_path: Path to run command in (defaults to lookup from registry)

    Returns:
        (success, output) - True if verification passed, False otherwise
    """
    msg_id = message.get("id", "unknown")
    dispatch = message.get("dispatch", {})
    test_command = dispatch.get("test_command")

    if not test_command:
        return True, "No verification command specified"

    if project_path is None:
        to_project = message.get("to", "unknown")
        project_path = get_project_path(to_project)
        if project_path is None:
            return False, f"Project '{to_project}' not registered"

    print(f"[dispatcher] Running verification: {test_command}")

    try:
        result = subprocess.run(
            test_command,
            shell=True,
            cwd=project_path,
            capture_output=True,
            text=True,
            timeout=300,
        )

        output = result.stdout + result.stderr
        success = result.returncode == 0

        if success:
            print(f"[dispatcher] Verification PASSED for {msg_id}")
        else:
            print(f"[dispatcher] Verification FAILED for {msg_id} (exit {result.returncode})")

        # Update task-monitor with quality metrics
        try:
            from . import task_monitor_client as tmc
        except ImportError:
            try:
                import task_monitor_client as tmc
            except ImportError:
                tmc = None

        if tmc:
            task_name = f"bug-fix-{msg_id}"
            details = {
                "current_item": "Verification " + ("passed" if success else "failed"),
                "stats": {
                    "test_command": test_command,
                    "exit_code": result.returncode,
                    "verified": success,
                }
            }
            if success:
                tmc.complete_task(task_name, success=True, note=f"Verified: {test_command}")
            else:
                tmc.update_task_progress(task_name, "needs_verification", details)

        # Update inbox message status
        try:
            from . import inbox
        except ImportError:
            import inbox

        if success:
            inbox.update_status(msg_id, "done", note=f"Verified: {test_command}")
        else:
            # SUPERVISOR LOOP: Check retries
            MAX_RETRIES = 3
            current_retries = message.get("dispatch", {}).get("retry_count", 0)

            if current_retries < MAX_RETRIES:
                print(f"[dispatcher] Verification failed. Retrying ({current_retries + 1}/{MAX_RETRIES})...")

                retry_note = f"Attempt {current_retries + 1} failed. Output:\n{output[-2000:]}"

                updated_msg = message.copy()
                updated_msg["status"] = "pending"
                updated_msg["dispatch"]["retry_count"] = current_retries + 1

                original_msg = updated_msg.get("message", "")
                timestamp_str = datetime.now().strftime("%H:%M:%S")
                updated_msg["message"] = f"{original_msg}\n\n[System {timestamp_str}] Verification Failed:\n```\n{output[-1000:]}\n```\nPlease analyze the error and try again."

                inbox.save_message(updated_msg)
                print(f"[dispatcher] Re-queued {msg_id} for retry")
            else:
                inbox.update_status(msg_id, "needs_verification",
                                   note=f"Test failed {MAX_RETRIES} times. Last error: {output[:200]}")
                print(f"[dispatcher] Max retries reached for {msg_id}")

        return success, output

    except subprocess.TimeoutExpired:
        msg = "Verification timed out after 5 minutes"
        print(f"[dispatcher] {msg}")
        return False, msg
    except Exception as e:
        msg = f"Verification error: {e}"
        print(f"[dispatcher] {msg}")
        return False, msg


def complete_fix(message: dict, success: bool = True, note: str = "") -> bool:
    """Complete a bug-fix and trigger auto-ack if verification passes.

    This function:
    1. Runs verification if test_command is specified
    2. If verification passes (or no verification), acks the inbox message
    3. Updates task-monitor with completion
    4. Moves message from pending/ to done/

    Args:
        message: Message dict
        success: Whether the fix was successful
        note: Completion note (e.g., commit hash, fix summary)

    Returns:
        True if completed and acked
    """
    msg_id = message.get("id", "unknown")
    dispatch = message.get("dispatch", {})
    test_command = dispatch.get("test_command")
    from_project = message.get("from", "unknown")

    try:
        from . import inbox
    except ImportError:
        import inbox

    if test_command:
        verified, output = verify_fix(message)
        if not verified:
            print(f"[dispatcher] Fix not verified for {msg_id}")
            return False
        ack_note = f"Fix verified. Test: {test_command}"
    else:
        ack_note = note or "Completed"

    if note:
        ack_note = f"{ack_note}. {note}"

    inbox.ack_message(msg_id, note=ack_note)

    try:
        from . import task_monitor_client as tmc
    except ImportError:
        try:
            import task_monitor_client as tmc
        except ImportError:
            tmc = None

    if tmc:
        task_name = f"bug-fix-{msg_id}"
        tmc.complete_task(task_name, success=True, note=ack_note)

    # POST-HOOK: Learn solution in memory for future agents
    if success:
        _learn_solution(message, ack_note)

    print(f"[dispatcher] Fix completed and acked for {msg_id}")
    print(f"[dispatcher] Ack note: {ack_note}")
    return True


# ============================================================================
# Dispatcher Daemon Functions
# ============================================================================


def should_dispatch(message: dict) -> bool:
    """Check if a message should be dispatched.

    A message should be dispatched if:
    - It has dispatch config
    - auto_spawn is True
    - Status is "pending" (not already dispatched)
    - Target project is registered

    Args:
        message: Message dict

    Returns:
        True if message should be dispatched
    """
    dispatch = message.get("dispatch")
    if not dispatch:
        return False

    if not dispatch.get("auto_spawn", True):
        return False

    if message.get("status") != "pending":
        return False

    to_project = message.get("to")
    if not get_project_path(to_project):
        return False

    return True


def watch_inbox(poll_interval: int = 5) -> List[dict]:
    """Poll the inbox for new messages that need dispatch.

    Args:
        poll_interval: Seconds between polls (not used in single poll)

    Returns:
        List of messages ready for dispatch
    """
    pending_dir = INBOX_DIR / "pending"
    if not pending_dir.exists():
        return []

    ready = []
    for f in pending_dir.glob("*.json"):
        try:
            msg = json.loads(f.read_text())
            if should_dispatch(msg):
                ready.append(msg)
        except Exception as e:
            print(f"[dispatcher] Error reading {f.name}: {e}")

    return ready


def dispatch_loop(poll_interval: int = 5, max_concurrent: int = 3, dry_run: bool = False):
    """Main dispatcher daemon loop.

    Continuously polls the inbox for pending messages and spawns agents.

    Args:
        poll_interval: Seconds between polls
        max_concurrent: Maximum concurrent agent processes
        dry_run: If True, show what would be dispatched without spawning
    """
    global _running

    # Track active processes: msg_id -> (pid, spawn_time, timeout_minutes)
    active_processes: Dict[str, tuple] = {}

    def cleanup_finished():
        """Remove finished processes and kill timed-out ones."""
        finished = []
        now = time.time()

        for msg_id, (pid, spawn_time, timeout_min) in active_processes.items():
            try:
                os.kill(pid, 0)
            except OSError:
                finished.append(msg_id)
                continue

            elapsed_min = (now - spawn_time) / 60
            if timeout_min and elapsed_min > timeout_min:
                print(f"[dispatcher] Agent for {msg_id} exceeded timeout ({timeout_min}m), killing PID {pid}")
                try:
                    os.kill(pid, signal.SIGTERM)
                    time.sleep(2)
                    try:
                        os.kill(pid, 0)
                        os.kill(pid, signal.SIGKILL)
                    except OSError:
                        pass
                except OSError:
                    pass
                finished.append(msg_id)

                try:
                    try:
                        from . import inbox as _inbox
                    except ImportError:
                        import inbox as _inbox
                    _inbox.update_status(msg_id, "needs_verification",
                                        note=f"Timed out after {timeout_min}m")
                except Exception as e:
                    logger.debug("import failed: {}", e)

        for msg_id in finished:
            del active_processes[msg_id]
            print(f"[dispatcher] Agent for {msg_id} finished")

            # Check verification / retry logic
            try:
                try:
                    from . import inbox as _inbox
                except ImportError:
                    import inbox as _inbox

                msg = _inbox.read_message(msg_id)
                if msg and msg.get("status") == "dispatched":
                    # WORKFLOW LOGIC: Check for next step
                    workflow = msg.get("workflow")
                    if workflow:
                        steps = workflow.get("steps", [])
                        current_idx = workflow.get("current_step_index", 0)

                        if steps and current_idx < len(steps) - 1:
                            next_idx = current_idx + 1
                            next_step = steps[next_idx]
                            print(f"[dispatcher] Workflow {msg_id}: Transitioning to step {next_idx} ({next_step.get('name')})")

                            workflow["current_step_index"] = next_idx
                            msg["workflow"] = workflow

                            dispatch = msg.get("dispatch", {})
                            if "model" in next_step:
                                dispatch["model"] = next_step["model"]
                            if "timeout_minutes" in next_step:
                                dispatch["timeout_minutes"] = next_step["timeout_minutes"]
                            if "test_command" in next_step:
                                dispatch["test_command"] = next_step["test_command"]
                            msg["dispatch"] = dispatch

                            original_msg = msg.get("message_original", msg.get("message", ""))
                            if "message_original" not in msg:
                                msg["message_original"] = original_msg

                            prev_log = msg.get("last_log_file", "unknown")

                            instruction = next_step.get("instruction", "")
                            msg["message"] = f"{original_msg}\n\n[System] Completed Step {current_idx}. See output at {prev_log}.\n\n[System] Proceeding to Step {next_idx}: {next_step.get('name')}\nInstruction: {instruction}"

                            msg["status"] = "pending"
                            msg["dispatch"]["retry_count"] = 0
                            _inbox.save_message(msg)
                            continue

                    print(f"[dispatcher] Running post-agent verification for {msg_id}")
                    verify_fix(msg, project_path=get_project_path(msg.get("to")))
            except Exception as e:
                print(f"[dispatcher] Error in post-agent verification: {e}")

    def handle_signal(signum, frame):
        global _running
        print(f"\n[dispatcher] Received signal {signum}, shutting down...")
        _running = False

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    print(f"[dispatcher] Starting daemon (poll={poll_interval}s, max_concurrent={max_concurrent})")
    print(f"[dispatcher] Watching: {INBOX_DIR / 'pending'}")

    if dry_run:
        print("[dispatcher] DRY RUN - no agents will be spawned")

    PID_FILE.write_text(str(os.getpid()))

    try:
        while _running:
            cleanup_finished()

            available_slots = max_concurrent - len(active_processes)
            if available_slots <= 0:
                print(f"[dispatcher] At capacity ({max_concurrent} agents running)")
                time.sleep(poll_interval)
                continue

            messages = watch_inbox(poll_interval)
            if messages:
                print(f"[dispatcher] Found {len(messages)} message(s) ready for dispatch")

            for msg in messages[:available_slots]:
                msg_id = msg.get("id", "unknown")
                model = msg.get("dispatch", {}).get("model", "sonnet")

                if msg_id in active_processes:
                    continue

                print(f"[dispatcher] Spawning agent for {msg_id} with model {model}")

                if dry_run:
                    print(f"[dispatcher] DRY RUN: Would spawn {model} for {msg_id}")
                    continue

                pid, log_file = spawn_agent(msg)
                if pid:
                    timeout_min = msg.get("dispatch", {}).get("timeout_minutes", 30)
                    active_processes[msg_id] = (pid, time.time(), timeout_min)

                    if log_file:
                        try:
                            from . import inbox as _inbox
                        except ImportError:
                            import inbox as _inbox
                        msg["last_log_file"] = log_file
                        msg["status"] = "dispatched"
                        _inbox.save_message(msg)

            time.sleep(poll_interval)

    finally:
        if PID_FILE.exists():
            PID_FILE.unlink()
        print(f"[dispatcher] Daemon stopped. {len(active_processes)} agent(s) still running.")


def daemon_status() -> dict:
    """Get dispatcher daemon status.

    Returns:
        Dict with status info
    """
    status = {
        "running": False,
        "pid": None,
        "pending_count": 0,
        "ready_to_dispatch": 0,
    }

    if PID_FILE.exists():
        try:
            pid = int(PID_FILE.read_text().strip())
            os.kill(pid, 0)
            status["running"] = True
            status["pid"] = pid
        except (ValueError, OSError):
            pass

    pending_dir = INBOX_DIR / "pending"
    if pending_dir.exists():
        for f in pending_dir.glob("*.json"):
            status["pending_count"] += 1
            try:
                msg = json.loads(f.read_text())
                if should_dispatch(msg):
                    status["ready_to_dispatch"] += 1
            except Exception as e:
                logger.debug("value lookup failed: {}", e)

    return status


def stop_daemon() -> bool:
    """Stop the dispatcher daemon.

    Returns:
        True if stopped, False if not running
    """
    if not PID_FILE.exists():
        print("[dispatcher] Daemon not running (no PID file)")
        return False

    try:
        pid = int(PID_FILE.read_text().strip())
        os.kill(pid, signal.SIGTERM)
        print(f"[dispatcher] Sent SIGTERM to process {pid}")
        return True
    except (ValueError, OSError) as e:
        print(f"[dispatcher] Could not stop daemon: {e}")
        PID_FILE.unlink()
        return False
