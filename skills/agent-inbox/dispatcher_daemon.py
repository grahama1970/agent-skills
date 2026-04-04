#!/usr/bin/env python3
"""Daemon loop for agent-inbox dispatcher.

Handles continuous polling, process management, timeout enforcement,
workflow step transitions, and graceful shutdown.
"""

import json
import os
import signal
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, List

from agent_inbox_config import (
    INBOX_DIR,
    REGISTRY_FILE,
    get_project_path,
)
from dispatcher_agent import spawn_agent, spawn_critical_agent, verify_fix, get_project_state_context
from loguru import logger

# Path to the agents-registry.json relative to this file's repo root
_REPO_ROOT = Path(__file__).resolve().parents[3]  # .pi/skills/agent-inbox/ -> repo root
_AGENTS_REGISTRY = _REPO_ROOT / ".pi" / "agents-registry.json"

# Daemon state
PID_FILE = INBOX_DIR / "dispatcher.pid"
_running = True  # Global flag for graceful shutdown
_last_sweep_time: float = 0.0  # epoch timestamp of last staleness sweep

# Staleness thresholds by message type
_STALE_THRESHOLDS = {
    "info": timedelta(days=7),
    "request": timedelta(days=7),
    "bug": timedelta(days=14),
    "question": timedelta(days=3),
}

# Test sender prefixes that get cleaned up immediately
_TEST_SENDERS = {"test-project", "integration-test"}

_SWEEP_INTERVAL_SECONDS = 3600  # 1 hour


def _lazy_import_inbox():
    """Lazy import inbox module (same pattern used elsewhere in this file)."""
    try:
        from . import inbox as _inbox
    except ImportError:
        import inbox as _inbox
    return _inbox


def sweep_stale() -> int:
    """Sweep stale messages from the pending inbox.

    Staleness rules:
    - info/request older than 7 days: auto-ack
    - bug older than 14 days: mark status 'stale', log warning
    - question older than 3 days: auto-ack
    - Messages from test senders: auto-ack immediately

    Returns:
        Number of messages swept.
    """
    pending_dir = INBOX_DIR / "pending"
    if not pending_dir.exists():
        return 0

    _inbox = _lazy_import_inbox()
    now = datetime.now(timezone.utc)
    swept = 0

    for f in list(pending_dir.glob("*.json")):
        try:
            msg = json.loads(f.read_text())
        except Exception as e:
            logger.warning("sweep_stale: failed to read {}: {}", f.name, e)
            continue

        msg_id = msg.get("id")
        if not msg_id:
            continue

        sender = msg.get("from", "")
        msg_type = msg.get("type", "info")

        # Rule: test senders get cleaned up immediately
        if sender in _TEST_SENDERS:
            logger.info("sweep_stale: cleaning up test message {} from '{}'", msg_id, sender)
            _inbox.ack_message(msg_id, note="Test data cleaned up")
            swept += 1
            continue

        # Parse created_at
        created_at_str = msg.get("created_at")
        if not created_at_str:
            continue

        try:
            # Handle trailing 'Z' (already UTC) — fromisoformat handles it in 3.11+
            created_at = datetime.fromisoformat(created_at_str.replace("Z", "+00:00"))
        except (ValueError, TypeError) as e:
            logger.warning("sweep_stale: bad created_at in {}: {}", msg_id, e)
            continue

        age = now - created_at

        # Rule: bugs get marked stale (not auto-acked) — needs human review
        if msg_type == "bug":
            threshold = _STALE_THRESHOLDS["bug"]
            if age > threshold:
                logger.warning("Bug stale for 14 days, needs human review: {}", msg_id)
                _inbox.update_status(msg_id, "stale",
                                     note="Bug stale for 14 days, needs human review")
                swept += 1
            continue

        # Rule: info, request, question — auto-ack if older than threshold
        threshold = _STALE_THRESHOLDS.get(msg_type)
        if threshold and age > threshold:
            days = threshold.days
            note = f"Auto-closed: stale after {days} days"
            if msg_type == "question":
                note = f"Auto-closed: question unanswered for {days} days"
            logger.info("sweep_stale: auto-acking {} (type={}, age={}d)", msg_id, msg_type, age.days)
            _inbox.ack_message(msg_id, note=note)
            swept += 1

    if swept:
        logger.info("sweep_stale: swept {} message(s)", swept)

    return swept


def auto_register_projects() -> None:
    """Auto-register projects from agents-registry.json into projects.json.

    Reads ~/.agent-inbox/projects.json (existing registry) and
    .pi/agents-registry.json, then registers any new agent project paths
    that are not already present.

    The project root is derived from each agent's `paths.agents_md` value
    by stripping the relative path back to the repo root (e.g.
    .pi/agents/brandon-bailey/AGENTS.md -> repo root).
    """
    if not _AGENTS_REGISTRY.exists():
        logger.debug("agents-registry.json not found at {}, skipping auto-register", _AGENTS_REGISTRY)
        return

    # Load existing projects registry
    existing: Dict[str, str] = {}
    if REGISTRY_FILE.exists():
        try:
            existing = json.loads(REGISTRY_FILE.read_text())
        except Exception as e:
            logger.warning("Failed to parse projects.json: {}", e)

    # Load agents-registry
    try:
        agents_data = json.loads(_AGENTS_REGISTRY.read_text())
    except Exception as e:
        logger.warning("Failed to parse agents-registry.json: {}", e)
        return

    agents = agents_data.get("agents", [])
    added: List[str] = []

    for agent in agents:
        agent_id = agent.get("id", "")
        if not agent_id:
            continue

        # Skip if already registered
        if agent_id in existing:
            continue

        agents_md_rel = agent.get("paths", {}).get("agents_md", "")
        if not agents_md_rel:
            logger.debug("Agent {} has no paths.agents_md, skipping", agent_id)
            continue

        # Derive project root: .pi/agents/<id>/AGENTS.md -> repo root (4 levels up from file)
        # Path: <repo>/.pi/agents/<id>/AGENTS.md  => parent x3 = <repo>/.pi => parent = <repo>
        agents_md_path = _REPO_ROOT / agents_md_rel
        project_root = agents_md_path.parents[3]  # strip AGENTS.md, <id>/, agents/, .pi/

        if not project_root.exists():
            logger.warning("Derived project root {} does not exist for agent {}, skipping", project_root, agent_id)
            continue

        existing[agent_id] = str(project_root)
        added.append(agent_id)
        logger.info("Auto-registered project '{}' -> {}", agent_id, project_root)

    if added:
        REGISTRY_FILE.parent.mkdir(parents=True, exist_ok=True)
        REGISTRY_FILE.write_text(json.dumps(existing, indent=2))
        logger.info("auto_register_projects: registered {} new project(s): {}", len(added), added)
    else:
        logger.debug("auto_register_projects: no new projects to register")


def _get_severity(message: dict) -> str:
    """Extract severity from a message's triage metadata.

    Args:
        message: Message dict

    Returns:
        Severity string: "low", "medium", "high", or "critical". Defaults to "medium".
    """
    return message.get("triage", {}).get("severity", "medium")


def should_dispatch(message: dict) -> bool:
    """Check if a message should be dispatched.

    A message should be dispatched if:
    - It has dispatch config
    - auto_spawn is True
    - Status is "pending" (not already dispatched)
    - Target project is registered
    - Severity is not "low" (low-severity messages are noted, not dispatched)

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

    # Low severity: set status to "noted" and skip dispatch
    severity = _get_severity(message)
    if severity == "low":
        msg_id = message.get("id", "unknown")
        logger.info("Low-severity message {} — setting status to 'noted', skipping dispatch", msg_id)
        try:
            _inbox = _lazy_import_inbox()
            _inbox.update_status(msg_id, "noted", note="Low severity — noted, not dispatched")
        except Exception as e:
            logger.warning("Failed to update low-severity message status: {}", e)
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
                os.kill(pid, 0)  # Check if still running
            except OSError:
                finished.append(msg_id)
                continue

            # Check timeout
            elapsed_min = (now - spawn_time) / 60
            if timeout_min and elapsed_min > timeout_min:
                print(f"[dispatcher] Agent for {msg_id} exceeded timeout ({timeout_min}m), killing PID {pid}")
                try:
                    os.kill(pid, signal.SIGTERM)
                    time.sleep(2)
                    # Force kill if still alive
                    try:
                        os.kill(pid, 0)
                        os.kill(pid, signal.SIGKILL)
                    except OSError:
                        pass
                except OSError:
                    pass
                finished.append(msg_id)

                # Update status to failed
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
                # Lazy import inbox
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

                        # If we haven't reached the end, transition
                        if steps and current_idx < len(steps) - 1:
                            next_idx = current_idx + 1
                            next_step = steps[next_idx]
                            print(f"[dispatcher] Workflow {msg_id}: Transitioning to step {next_idx} ({next_step.get('name')})")

                            # Update workflow state
                            workflow["current_step_index"] = next_idx
                            msg["workflow"] = workflow

                            # Update dispatch config
                            dispatch = msg.get("dispatch", {})
                            if "model" in next_step:
                                dispatch["model"] = next_step["model"]
                            if "timeout_minutes" in next_step:
                                dispatch["timeout_minutes"] = next_step["timeout_minutes"]
                            if "test_command" in next_step:
                                dispatch["test_command"] = next_step["test_command"]
                            msg["dispatch"] = dispatch

                            # Update prompt/message to include new instruction
                            original_msg = msg.get("message_original", msg.get("message", ""))
                            if "message_original" not in msg:
                                msg["message_original"] = original_msg

                            prev_log = msg.get("last_log_file", "unknown")

                            instruction = next_step.get("instruction", "")
                            msg["message"] = f"{original_msg}\n\n[System] Completed Step {current_idx}. See output at {prev_log}.\n\n[System] Proceeding to Step {next_idx}: {next_step.get('name')}\nInstruction: {instruction}"

                            # Re-queue
                            msg["status"] = "pending"
                            msg["dispatch"]["retry_count"] = 0  # Reset retries for new step

                            _inbox.save_message(msg)
                            continue  # Skip verification for intermediate steps

                    # Agent finished but didn't update status
                    print(f"[dispatcher] Running post-agent verification for {msg_id}")
                    verify_fix(msg, project_path=get_project_path(msg.get("to")))
            except Exception as e:
                print(f"[dispatcher] Error in post-agent verification: {e}")

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

    # Auto-register projects from agents-registry before entering the loop
    auto_register_projects()

    # Write PID file
    PID_FILE.write_text(str(os.getpid()))

    try:
        while _running:
            # Staleness sweep — runs at most once per hour
            global _last_sweep_time
            now_epoch = time.time()
            if now_epoch - _last_sweep_time >= _SWEEP_INTERVAL_SECONDS:
                try:
                    swept = sweep_stale()
                    if swept:
                        logger.info("Staleness sweep completed: {} message(s) swept", swept)
                except Exception as e:
                    logger.error("Staleness sweep failed: {}", e)
                _last_sweep_time = now_epoch

            cleanup_finished()

            # Check if we can spawn more
            available_slots = max_concurrent - len(active_processes)
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

                if msg_id in active_processes:
                    continue  # Already dispatching

                severity = _get_severity(msg)
                print(f"[dispatcher] Spawning agent for {msg_id} with model {model} (severity={severity})")

                if dry_run:
                    print(f"[dispatcher] DRY RUN: Would spawn {model} for {msg_id} (severity={severity})")
                    continue

                # Route dispatch based on severity tier
                if severity == "critical":
                    # Critical: Docker-isolated agent via create-subagent
                    project_context = get_project_state_context(get_project_path(msg.get("to")))
                    pid, log_file = spawn_critical_agent(msg, project_context=project_context)
                elif severity == "high":
                    # High: standard agent with project-state context injected
                    project_context = get_project_state_context(get_project_path(msg.get("to")))
                    pid, log_file = spawn_agent(msg, project_context=project_context)
                else:
                    # Medium (default): standard agent, no extra context
                    pid, log_file = spawn_agent(msg)
                if pid:
                    timeout_min = msg.get("dispatch", {}).get("timeout_minutes", 30)
                    active_processes[msg_id] = (pid, time.time(), timeout_min)

                    # Store log file in message for workflow tracking
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
        # Cleanup PID file
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
        # Clean up stale PID file
        PID_FILE.unlink()
        return False
