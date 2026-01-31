#!/usr/bin/env python3
"""
Dispatcher Module for Agent-Inbox Headless Dispatch.

Handles spawning headless agents to process bug-fix requests with
model-specific CLI commands and proper process isolation.
"""
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Dict, Any, List

# Model to CLI command mapping
MODEL_COMMANDS: Dict[str, List[str]] = {
    "sonnet": ["claude", "--model", "sonnet"],
    "opus-4.5": ["claude", "--model", "opus"],
    "codex-5.2": ["codex", "--model", "gpt-5.2-codex"],
    "codex-5.2-high": ["codex", "--model", "gpt-5.2-codex", "--reasoning", "high"],
}

# Inbox directory configuration
INBOX_DIR = Path(os.environ.get("AGENT_INBOX_DIR", Path.home() / ".agent-inbox"))
REGISTRY_FILE = INBOX_DIR / "projects.json"
LOG_DIR = INBOX_DIR / "logs"


def _load_registry() -> Dict[str, str]:
    """Load project registry."""
    if REGISTRY_FILE.exists():
        try:
            return json.loads(REGISTRY_FILE.read_text())
        except Exception:
            pass
    return {}


def get_project_path(project_name: str) -> Optional[Path]:
    """Get filesystem path for a registered project.

    Args:
        project_name: Name of the project

    Returns:
        Path to project directory, or None if not registered
    """
    registry = _load_registry()
    path_str = registry.get(project_name)
    if path_str:
        return Path(path_str)
    return None


def recall_from_memory(query: str, project_path: Optional[Path] = None) -> Optional[str]:
    """Query memory for similar bugs and solutions.

    Uses the /memory skill to find relevant lessons learned.

    Args:
        query: Bug description or error message
        project_path: Path to run memory recall from

    Returns:
        Memory recall results as markdown, or None if unavailable
    """
    # Try to find memory skill
    memory_skill = Path.home() / ".pi" / "skills" / "memory" / "run.sh"
    if not memory_skill.exists():
        # Try alternate location
        memory_skill = Path.home() / ".agent" / "skills" / "memory" / "run.sh"
        if not memory_skill.exists():
            print("[dispatcher] Memory skill not found, skipping recall")
            return None

    try:
        # Build recall query from bug description
        # Truncate to avoid overly long queries
        recall_query = query[:500] if len(query) > 500 else query

        result = subprocess.run(
            ["bash", str(memory_skill), "recall", "--q", recall_query, "--k", "3"],
            cwd=project_path or Path.cwd(),
            capture_output=True,
            text=True,
            timeout=30,
        )

        if result.returncode == 0 and result.stdout.strip():
            output = result.stdout.strip()
            # Check if we got meaningful results
            if "No relevant" not in output and len(output) > 50:
                print(f"[dispatcher] Memory recall found relevant lessons")
                return output
            else:
                print("[dispatcher] No relevant lessons found in memory")
                return None
        else:
            print("[dispatcher] Memory recall returned no results")
            return None

    except subprocess.TimeoutExpired:
        print("[dispatcher] Memory recall timed out")
        return None
    except Exception as e:
        print(f"[dispatcher] Memory recall error: {e}")
        return None


def build_prompt(message: dict, memory_context: Optional[str] = None) -> str:
    """Build a bug-fix prompt from an inbox message.

    Args:
        message: Message dict with id, to, from, message, dispatch, context fields
        memory_context: Optional memory recall results to include

    Returns:
        Formatted prompt string for the agent
    """
    msg_id = message.get("id", "unknown")
    from_project = message.get("from", "unknown")
    to_project = message.get("to", "unknown")
    msg_type = message.get("type", "bug")
    priority = message.get("priority", "normal")
    content = message.get("message", "")
    dispatch = message.get("dispatch", {})
    test_command = dispatch.get("test_command")
    context_files = message.get("context", [])

    prompt_parts = [
        f"# Bug Fix Request from {from_project}",
        "",
        f"**Message ID**: {msg_id}",
        f"**Type**: {msg_type}",
        f"**Priority**: {priority}",
        "",
    ]

    # Add memory recall results first (prior solutions)
    if memory_context:
        prompt_parts.extend([
            "## Prior Solutions from Memory",
            "",
            "The following relevant lessons and solutions were found. Review and adapt as needed:",
            "",
            memory_context,
            "",
        ])

    prompt_parts.extend([
        "## Description",
        "",
        content,
        "",
    ])

    # Add context files if provided
    if context_files:
        prompt_parts.extend([
            "## Context Files",
            "",
        ])
        for ctx in context_files:
            prompt_parts.extend([
                f"### {ctx.get('file', 'Unknown')}",
                f"Path: `{ctx.get('path', 'N/A')}`",
                "```",
                ctx.get("content", ""),
                "```",
                "",
            ])

    prompt_parts.extend([
        "## Instructions",
        "",
        "1. Review any prior solutions from memory above",
        "2. Analyze the bug described above",
        "3. Find the root cause in the codebase",
        "4. Implement a fix",
        "5. Test your changes",
    ])

    if test_command:
        prompt_parts.extend([
            f"6. Run the verification command: `{test_command}`",
            "7. Only mark complete if verification passes",
        ])
    else:
        prompt_parts.extend([
            "6. Commit your changes with a clear message",
        ])

    prompt_parts.extend([
        "",
        "## Completion",
        "",
        "When done, update the inbox message status:",
        f"```",
        f"agent-inbox update-status {msg_id} done --note 'Fixed: <brief description>'",
        f"```",
    ])

    return "\n".join(prompt_parts)


def spawn_agent(
    message: dict,
    project_path: Optional[Path] = None,
    dry_run: bool = False,
) -> Optional[int]:
    """Spawn a detached headless agent to process a message.

    Args:
        message: Message dict with dispatch config
        project_path: Path to run the agent in (defaults to lookup from registry)
        dry_run: If True, print command but don't execute

    Returns:
        Process ID if spawned, None if dry_run or error
    """
    msg_id = message.get("id", "unknown")
    to_project = message.get("to", "unknown")
    dispatch = message.get("dispatch", {})
    model = dispatch.get("model", "sonnet")
    timeout_minutes = dispatch.get("timeout_minutes", 30)

    # Get CLI command for model
    if model not in MODEL_COMMANDS:
        print(f"[dispatcher] Error: Unknown model '{model}'")
        return None

    cmd_base = MODEL_COMMANDS[model].copy()

    # Resolve project path
    if project_path is None:
        project_path = get_project_path(to_project)
        if project_path is None:
            print(f"[dispatcher] Error: Project '{to_project}' not registered")
            print(f"[dispatcher] Register with: agent-inbox register {to_project} /path/to/project")
            return None

    # PRE-HOOK: Query memory for similar bugs and solutions
    print(f"[dispatcher] Querying memory for similar issues...")
    bug_description = message.get("message", "")
    memory_context = recall_from_memory(bug_description, project_path)

    # Build prompt with memory context
    prompt = build_prompt(message, memory_context=memory_context)

    # Build full command
    # Use --no-session to avoid session conflicts, -p for print mode (non-interactive)
    cmd = cmd_base + ["--no-session", "-p", prompt]

    if dry_run:
        print(f"[dispatcher] Would run in {project_path}:")
        print(f"[dispatcher] {' '.join(cmd[:5])}... (prompt truncated)")
        return None

    # Ensure log directory exists
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    # Create log file for this dispatch
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    log_file = LOG_DIR / f"{msg_id}_{timestamp}.log"

    print(f"[dispatcher] Spawning {model} agent for {msg_id}")
    print(f"[dispatcher] Working directory: {project_path}")
    print(f"[dispatcher] Log file: {log_file}")

    try:
        # Open log file for output
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

            # Spawn detached process
            process = subprocess.Popen(
                cmd,
                cwd=project_path,
                stdout=log_f,
                stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
                start_new_session=True,  # Detach from parent process group
            )

            print(f"[dispatcher] Started process {process.pid}")

            # Update message status to dispatched
            try:
                from . import inbox
            except ImportError:
                import inbox
            inbox.update_status(msg_id, "dispatched", note=f"PID: {process.pid}")

            return process.pid

    except Exception as e:
        print(f"[dispatcher] Error spawning agent: {e}")
        return None


def get_dispatch_log(msg_id: str) -> Optional[str]:
    """Get the most recent dispatch log for a message.

    Args:
        msg_id: Message ID

    Returns:
        Log file content, or None if not found
    """
    if not LOG_DIR.exists():
        return None

    # Find log files for this message
    logs = sorted(LOG_DIR.glob(f"{msg_id}_*.log"), reverse=True)
    if logs:
        return logs[0].read_text()
    return None


def verify_fix(message: dict, project_path: Optional[Path] = None) -> tuple[bool, str]:
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
        # No verification command - auto-pass
        return True, "No verification command specified"

    # Resolve project path
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
            timeout=300,  # 5 minute timeout for verification
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
            inbox.update_status(msg_id, "needs_verification",
                               note=f"Test failed (exit {result.returncode}): {output[:200]}")

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

    # If test command specified, run verification
    if test_command:
        verified, output = verify_fix(message)
        if not verified:
            print(f"[dispatcher] Fix not verified for {msg_id}")
            return False
        ack_note = f"Fix verified. Test: {test_command}"
    else:
        ack_note = note or "Completed"

    # Build fix summary for ack note
    if note:
        ack_note = f"{ack_note}. {note}"

    # Auto-ack the inbox message (moves to done/)
    inbox.ack_message(msg_id, note=ack_note)

    # Update task-monitor
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

    print(f"[dispatcher] Fix completed and acked for {msg_id}")
    print(f"[dispatcher] Ack note: {ack_note}")
    return True


# ============================================================================
# Dispatcher Daemon Functions
# ============================================================================

PID_FILE = INBOX_DIR / "dispatcher.pid"
_running = True  # Global flag for graceful shutdown


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

    # Check if project is registered
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
    import signal
    import time

    # Track active processes
    active_pids: Dict[str, int] = {}  # msg_id -> pid

    def cleanup_finished():
        """Remove finished processes from tracking."""
        finished = []
        for msg_id, pid in active_pids.items():
            try:
                # Check if process is still running
                os.kill(pid, 0)
            except OSError:
                finished.append(msg_id)

        for msg_id in finished:
            del active_pids[msg_id]
            print(f"[dispatcher] Agent for {msg_id} finished")

    def handle_signal(signum, frame):
        global _running
        print(f"\n[dispatcher] Received signal {signum}, shutting down...")
        _running = False

    # Set up signal handlers
    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    print(f"[dispatcher] Starting daemon (poll={poll_interval}s, max_concurrent={max_concurrent})")
    print(f"[dispatcher] Watching: {INBOX_DIR / 'pending'}")

    if dry_run:
        print("[dispatcher] DRY RUN - no agents will be spawned")

    # Write PID file
    PID_FILE.write_text(str(os.getpid()))

    try:
        while _running:
            cleanup_finished()

            # Check if we can spawn more
            available_slots = max_concurrent - len(active_pids)
            if available_slots <= 0:
                print(f"[dispatcher] At capacity ({max_concurrent} agents running)")
                time.sleep(poll_interval)
                continue

            # Find messages to dispatch
            messages = watch_inbox(poll_interval)
            if messages:
                print(f"[dispatcher] Found {len(messages)} message(s) ready for dispatch")

            # Dispatch up to available slots
            for msg in messages[:available_slots]:
                msg_id = msg.get("id", "unknown")
                model = msg.get("dispatch", {}).get("model", "sonnet")

                if msg_id in active_pids:
                    continue  # Already dispatching

                print(f"[dispatcher] Spawning agent for {msg_id} with model {model}")

                if dry_run:
                    print(f"[dispatcher] DRY RUN: Would spawn {model} for {msg_id}")
                    continue

                pid = spawn_agent(msg)
                if pid:
                    active_pids[msg_id] = pid

            time.sleep(poll_interval)

    finally:
        # Cleanup PID file
        if PID_FILE.exists():
            PID_FILE.unlink()
        print(f"[dispatcher] Daemon stopped. {len(active_pids)} agent(s) still running.")


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

    # Check PID file
    if PID_FILE.exists():
        try:
            pid = int(PID_FILE.read_text().strip())
            os.kill(pid, 0)  # Check if process exists
            status["running"] = True
            status["pid"] = pid
        except (ValueError, OSError):
            pass

    # Count pending messages
    pending_dir = INBOX_DIR / "pending"
    if pending_dir.exists():
        for f in pending_dir.glob("*.json"):
            status["pending_count"] += 1
            try:
                msg = json.loads(f.read_text())
                if should_dispatch(msg):
                    status["ready_to_dispatch"] += 1
            except Exception:
                pass

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
        # Clean up stale PID file
        PID_FILE.unlink()
        return False


# CLI for testing
if __name__ == "__main__":
    import argparse
    import signal

    parser = argparse.ArgumentParser(description="Agent-Inbox Dispatcher")
    subparsers = parser.add_subparsers(dest="command")

    # start command (daemon)
    p_start = subparsers.add_parser("start", help="Start the dispatcher daemon")
    p_start.add_argument("--poll", type=int, default=5, help="Poll interval in seconds")
    p_start.add_argument("--max-concurrent", type=int, default=3, help="Max concurrent agents")
    p_start.add_argument("--dry-run", action="store_true", help="Don't actually spawn agents")
    p_start.add_argument("--foreground", "-f", action="store_true", help="Run in foreground")

    # stop command
    p_stop = subparsers.add_parser("stop", help="Stop the dispatcher daemon")

    # status command
    p_status = subparsers.add_parser("status", help="Show dispatcher status")
    p_status.add_argument("--json", action="store_true", help="Output JSON")

    # spawn command (single message)
    p_spawn = subparsers.add_parser("spawn", help="Spawn agent for a single message")
    p_spawn.add_argument("msg_id", help="Message ID to process")
    p_spawn.add_argument("--dry-run", action="store_true", help="Show command without running")

    # log command
    p_log = subparsers.add_parser("log", help="View dispatch log")
    p_log.add_argument("msg_id", help="Message ID")

    # models command
    p_models = subparsers.add_parser("models", help="List supported models")

    args = parser.parse_args()

    if args.command == "start":
        status = daemon_status()
        if status["running"]:
            print(f"[dispatcher] Already running (PID {status['pid']})")
            sys.exit(1)

        if args.foreground:
            dispatch_loop(
                poll_interval=args.poll,
                max_concurrent=args.max_concurrent,
                dry_run=args.dry_run
            )
        else:
            # Daemonize
            pid = os.fork()
            if pid > 0:
                print(f"[dispatcher] Started daemon (PID {pid})")
                sys.exit(0)

            # Child process
            os.setsid()
            dispatch_loop(
                poll_interval=args.poll,
                max_concurrent=args.max_concurrent,
                dry_run=args.dry_run
            )

    elif args.command == "stop":
        stop_daemon()

    elif args.command == "status":
        status = daemon_status()
        if getattr(args, 'json', False):
            print(json.dumps(status, indent=2))
        else:
            if status["running"]:
                print(f"Dispatcher: RUNNING (PID {status['pid']})")
            else:
                print("Dispatcher: STOPPED")
            print(f"Pending messages: {status['pending_count']}")
            print(f"Ready to dispatch: {status['ready_to_dispatch']}")

    elif args.command == "spawn":
        try:
            from . import inbox
        except ImportError:
            import inbox

        msg = inbox.read_message(args.msg_id)
        if not msg:
            print(f"Message not found: {args.msg_id}")
            sys.exit(1)

        pid = spawn_agent(msg, dry_run=args.dry_run)
        if pid:
            print(f"Process started: {pid}")

    elif args.command == "log":
        log_content = get_dispatch_log(args.msg_id)
        if log_content:
            print(log_content)
        else:
            print(f"No log found for: {args.msg_id}")

    elif args.command == "models":
        print("Supported models:")
        for model, cmd in MODEL_COMMANDS.items():
            print(f"  {model}: {' '.join(cmd)}")

    else:
        parser.print_help()
