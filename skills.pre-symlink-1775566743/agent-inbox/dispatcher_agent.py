#!/usr/bin/env python3
"""Agent spawning and verification for agent-inbox dispatcher.

Handles building prompts, spawning headless agents, verifying fixes,
and completing bug-fix workflows.
"""

import json
import os
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Dict, List, Tuple

from loguru import logger

from agent_inbox_config import (
    MODEL_COMMANDS,
    INBOX_DIR,
    LOG_DIR,
    get_project_path,
)
from dispatcher_escalation import escalate_to_human
from dispatcher_memory import recall_from_memory, learn_solution, checkpoint_fix


def _load_project_defaults() -> Dict:
    """Load per-project CLI overrides from ~/.agent-inbox/project_defaults.json.

    Returns:
        Dict with optional keys like {"cli": "pi"} or per-project overrides.
        Returns empty dict if file does not exist or cannot be parsed.
    """
    defaults_path = Path.home() / ".agent-inbox" / "project_defaults.json"
    if defaults_path.exists():
        try:
            return json.loads(defaults_path.read_text())
        except Exception as e:
            logger.warning("Failed to load project_defaults.json: {}", e)
    return {}


def _resolve_cli(project_name: str, model: str) -> List[str]:
    """Resolve the CLI command to use for spawning an agent.

    Selection priority:
    1. Per-project override in ~/.agent-inbox/project_defaults.json
       (key: project_name → {"cli": "pi"})
    2. Top-level "default" key in project_defaults.json ({"cli": "pi"})
    3. "pi" if shutil.which("pi") finds it on PATH
    4. Fall back to MODEL_COMMANDS[model] (e.g. claude --model sonnet)

    Args:
        project_name: Target project name (message["to"])
        model: Model name from dispatch config

    Returns:
        List[str] base command (without the prompt args)
    """
    project_defaults = _load_project_defaults()

    # Per-project CLI override
    project_cfg = project_defaults.get(project_name, {})
    cli_override = project_cfg.get("cli") or project_defaults.get("default", {}).get("cli")

    if cli_override == "pi":
        if shutil.which("pi"):
            logger.info("CLI chosen: pi (project_defaults override for '{}')", project_name)
            return ["pi"]
        else:
            logger.warning(
                "project_defaults requests 'pi' for '{}' but pi not found on PATH; falling back",
                project_name,
            )

    # Auto-detect: prefer pi if available
    if shutil.which("pi"):
        logger.info("CLI chosen: pi (auto-detected on PATH)")
        return ["pi"]

    # Fall back to MODEL_COMMANDS entry
    cmd_base = MODEL_COMMANDS.get(model, MODEL_COMMANDS.get("sonnet", ["claude", "--model", "sonnet"]))
    logger.info("CLI chosen: {} (MODEL_COMMANDS[{}])", cmd_base[0], model)
    return cmd_base.copy()


def build_prompt(
    message: dict,
    memory_context: Optional[str] = None,
    project_context: Optional[str] = None,
) -> str:
    """Build a bug-fix prompt from an inbox message.

    Args:
        message: Message dict with id, to, from, message, dispatch, context fields
        memory_context: Optional memory recall results to include
        project_context: Optional project-state report to prepend (for high/critical severity)

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

    # Add project-state context for high/critical severity
    if project_context:
        prompt_parts.extend([
            "## Current Project State",
            "",
            "The following project-state snapshot was collected to give you situational awareness:",
            "",
            project_context,
            "",
        ])

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

    # Add thread history if available
    thread_id = message.get("thread_id") or message.get("id")
    if thread_id:
        try:
            # Lazy import inbox to avoid circular issues
            try:
                from . import inbox
            except ImportError:
                import inbox

            # Get all messages in thread
            thread_msgs = inbox.list_thread(thread_id)

            # Filter out the current message itself
            history_parts = []
            for tm in thread_msgs:
                if tm.get("id") == msg_id:
                    continue  # Skip self (already in Description)

                sender = tm.get("from", "unknown")
                tm_content = tm.get("message", "")
                tm_type = tm.get("type", "info")
                tm_created = tm.get("created_at", "")

                history_parts.append(f"### Reply from {sender} ({tm_created})")
                history_parts.append(f"Type: {tm_type}")
                history_parts.append(tm_content)
                history_parts.append("")

            if history_parts:
                prompt_parts.extend([
                    "## Discussion History / Steering",
                    "Pay attention to these additional messages and guidance:",
                    "",
                ] + history_parts)

        except Exception as e:
            print(f"[dispatcher] Error fetching thread history: {e}")

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
        "## Context & State",
        "",
        "1. To understand the current project state, run:",
        "   `.pi/skills/create-context/run.sh generate --minimal`",
        "2. Read the generated `local/docs/CONTEXT.md` to ground your work.",
        "",
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


def get_project_state_context(project_path: Optional[Path]) -> Optional[str]:
    """Get cached project-state context for high/critical severity dispatch.

    Runs `project-state report --quick --json --cached` to get a cached snapshot.

    Args:
        project_path: Path to the project directory

    Returns:
        Project state JSON string, or None if unavailable
    """
    if not project_path:
        return None

    # Find project-state skill
    repo_root = Path(__file__).resolve().parents[3]
    ps_path = repo_root / ".pi" / "skills" / "project-state" / "run.sh"
    if not ps_path.exists():
        ps_path = Path.home() / ".claude" / "skills" / "project-state" / "run.sh"
    if not ps_path.exists():
        logger.warning("project-state skill not found")
        return None

    try:
        result = subprocess.run(
            [str(ps_path), "report", "--quick", "--json", "--cached"],
            cwd=project_path,
            capture_output=True,
            text=True,
            timeout=30,
            env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
        )
        if result.returncode == 0 and result.stdout.strip():
            logger.info("Got project-state context ({} bytes)", len(result.stdout))
            return result.stdout.strip()
        logger.warning("project-state returned exit {}", result.returncode)
    except subprocess.TimeoutExpired:
        logger.warning("project-state timed out after 30s")
    except Exception as e:
        logger.warning("project-state failed: {}", e)

    return None


def spawn_critical_agent(
    message: dict,
    project_context: Optional[str] = None,
) -> Tuple[Optional[int], Optional[str]]:
    """Spawn a Docker-isolated agent via /create-subagent for critical severity.

    Args:
        message: Message dict with dispatch config
        project_context: Optional project-state context to inject

    Returns:
        (Process ID, log_file) if spawned, (None, None) on error
    """
    msg_id = message.get("id", "unknown")
    to_project = message.get("to", "unknown")
    dispatch = message.get("dispatch", {})
    model = dispatch.get("model", "opus-4.5")

    # Find create-subagent skill
    repo_root = Path(__file__).resolve().parents[3]
    cs_path = repo_root / ".pi" / "skills" / "create-subagent" / "run.sh"
    if not cs_path.exists():
        cs_path = Path.home() / ".claude" / "skills" / "create-subagent" / "run.sh"
    if not cs_path.exists():
        logger.warning("create-subagent not found, falling back to standard spawn")
        return spawn_agent(message, project_context=project_context)

    project_path = get_project_path(to_project)
    if not project_path:
        logger.error("Project '{}' not registered", to_project)
        return None, None

    # Build prompt with full context
    memory_context = recall_from_memory(message.get("message", ""), Path(project_path))
    prompt = build_prompt(message, memory_context=memory_context, project_context=project_context)

    # Log file
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    log_file = LOG_DIR / f"{msg_id}_{timestamp}_critical.log"

    logger.info("Spawning critical agent for {} via create-subagent", msg_id)

    try:
        cmd = [
            str(cs_path), "spawn",
            "--name", f"inbox-fix-{msg_id}",
            "--model", model,
            "--workspace", str(project_path),
            "--prompt", prompt,
        ]

        with open(log_file, "w") as log_f:
            log_f.write(f"# Critical dispatch for {msg_id}\n")
            log_f.write(f"# Model: {model}\n")
            log_f.write(f"# Via: create-subagent (Docker)\n\n")
            log_f.flush()

            process = subprocess.Popen(
                cmd,
                stdout=log_f,
                stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
                start_new_session=True,
                env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
            )

        logger.info("Critical agent PID {} for {}", process.pid, msg_id)

        try:
            from . import inbox
        except ImportError:
            import inbox
        inbox.update_status(msg_id, "dispatched",
                          note=f"Critical: PID {process.pid} via create-subagent")

        return process.pid, str(log_file)

    except Exception as e:
        logger.error("Failed to spawn critical agent: {}", e)
        return None, None


def spawn_agent(
    message: dict,
    project_path: Optional[Path] = None,
    dry_run: bool = False,
    project_context: Optional[str] = None,
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

    # Resolve CLI (pi preferred, falls back to claude)
    cmd_base = _resolve_cli(to_project, model)
    cli_name = cmd_base[0]

    # Resolve project path
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

    # Build prompt with memory context and optional project context
    prompt = build_prompt(message, memory_context=memory_context, project_context=project_context)

    # Build full command.
    # pi uses: pi -p <prompt>
    # claude uses: claude --model <model> --no-session -p <prompt>
    if cli_name == "pi":
        cmd = cmd_base + ["-p", prompt]
    else:
        cmd = cmd_base + ["--no-session", "-p", prompt]

    if dry_run:
        print(f"[dispatcher] Would run in {project_path}:")
        print(f"[dispatcher] CLI: {cli_name}")
        print(f"[dispatcher] {' '.join(cmd[:5])}... (prompt truncated)")
        return None, None

    # Ensure log directory exists
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    # Create log file for this dispatch
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    log_file = LOG_DIR / f"{msg_id}_{timestamp}.log"

    print(f"[dispatcher] Spawning {model} agent for {msg_id} via {cli_name}")
    print(f"[dispatcher] Working directory: {project_path}")
    print(f"[dispatcher] Log file: {log_file}")

    try:
        # Open log file for output
        with open(log_file, "w") as log_f:
            log_f.write(f"# Dispatch log for {msg_id}\n")
            log_f.write(f"# CLI: {cli_name}\n")
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
                start_new_session=True,
                env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
            )

            print(f"[dispatcher] Started process {process.pid}")

            # Update message status to dispatched
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

    # Find log files for this message
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
    msg_type = message.get("type", "bug")
    dispatch = message.get("dispatch", {})
    test_command = dispatch.get("test_command")

    if not test_command:
        if msg_type == "bug":
            logger.warning(f"Bug message {msg_id} has no test_command — setting to needs_review")
            try:
                from . import inbox
            except ImportError:
                import inbox
            inbox.update_status(msg_id, "needs_review", note="Bug message missing test_command")
            return False, "Bug message requires test_command for verification"
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
            timeout=300,
            env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
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
            # SUPERVISOR LOOP: 1 auto-retry, then escalate via /interview
            MAX_RETRIES = 1
            current_retries = message.get("dispatch", {}).get("retry_count", 0)

            if current_retries < MAX_RETRIES:
                logger.info("Verification failed for {}. Auto-retry with fresh context ({}/{})",
                           msg_id, current_retries + 1, MAX_RETRIES)

                # Force-refresh project-state for retry
                project_path = get_project_path(message.get("to"))
                if project_path:
                    get_project_state_context(Path(project_path))

                updated_msg = message.copy()
                updated_msg["status"] = "pending"
                updated_msg["dispatch"]["retry_count"] = current_retries + 1

                original_msg = updated_msg.get("message", "")
                timestamp = datetime.now().strftime("%H:%M:%S")
                updated_msg["message"] = (
                    f"{original_msg}\n\n[System {timestamp}] Verification Failed:\n"
                    f"```\n{output[-1000:]}\n```\n"
                    f"Please analyze the error and try a different approach."
                )

                inbox.save_message(updated_msg)
                logger.info("Re-queued {} for retry with error context", msg_id)
            else:
                # Max retries exhausted — escalate via /interview then Discord fallback
                logger.warning("Max retries reached for {} — escalating", msg_id)
                escalate_to_human(message, output, inbox)

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

    # POST-HOOK: Learn solution and checkpoint for future agents
    if success:
        learn_solution(message, ack_note)
        checkpoint_fix(message, ack_note)

    print(f"[dispatcher] Fix completed and acked for {msg_id}")
    print(f"[dispatcher] Ack note: {ack_note}")
    return True
