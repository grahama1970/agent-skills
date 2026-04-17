#!/usr/bin/env python3
"""
Dispatcher Module for Agent-Inbox Headless Dispatch.

Thin assembler: imports from dispatch_core and dispatch_agent.
Provides backward-compatible re-exports and CLI entry point.
"""

import json
import os
import sys
from pathlib import Path

# Re-export everything from sub-modules for backward compatibility
from dispatch_core import (
    load_model_registry,
    MODEL_COMMANDS,
    INBOX_DIR,
    REGISTRY_FILE,
    LOG_DIR,
    get_project_path,
    recall_from_memory,
    _learn_solution,
    build_prompt,
)

from dispatch_agent import (
    PID_FILE,
    spawn_agent,
    get_dispatch_log,
    verify_fix,
    complete_fix,
    should_dispatch,
    watch_inbox,
    dispatch_loop,
    daemon_status,
    stop_daemon,
)


# CLI for testing
if __name__ == "__main__":
    import signal
    import typer

    app = typer.Typer(help="Agent-Inbox Dispatcher")

    @app.command()
    def start(
        poll: int = typer.Option(5, help="Poll interval in seconds"),
        max_concurrent: int = typer.Option(3, help="Max concurrent agents"),
        dry_run: bool = typer.Option(False, help="Don't actually spawn agents"),
        foreground: bool = typer.Option(False, "-f", "--foreground", help="Run in foreground"),
    ):
        status = daemon_status()
        if status["running"]:
            print(f"[dispatcher] Already running (PID {status['pid']})")
            raise typer.Exit(code=1)

        if foreground:
            dispatch_loop(
                poll_interval=poll,
                max_concurrent=max_concurrent,
                dry_run=dry_run
            )
        else:
            # Daemonize
            pid = os.fork()
            if pid > 0:
                print(f"[dispatcher] Started daemon (PID {pid})")
                raise typer.Exit(code=0)

            # Child process
            os.setsid()
            dispatch_loop(
                poll_interval=poll,
                max_concurrent=max_concurrent,
                dry_run=dry_run
            )

    @app.command()
    def stop():
        stop_daemon()

    @app.command()
    def status(
        output_json: bool = typer.Option(False, "--json", help="Output JSON"),
    ):
        st = daemon_status()
        if output_json:
            print(json.dumps(st, indent=2))
        else:
            if st["running"]:
                print(f"Dispatcher: RUNNING (PID {st['pid']})")
            else:
                print("Dispatcher: STOPPED")
            print(f"Pending messages: {st['pending_count']}")
            print(f"Ready to dispatch: {st['ready_to_dispatch']}")

    @app.command()
    def spawn(
        msg_id: str = typer.Argument(..., help="Message ID to process"),
        dry_run: bool = typer.Option(False, help="Show command without running"),
    ):
        try:
            from . import inbox
        except ImportError:
            import inbox

        msg = inbox.read_message(msg_id)
        if not msg:
            print(f"Message not found: {msg_id}")
            raise typer.Exit(code=1)

        pid = spawn_agent(msg, dry_run=dry_run)
        if pid:
            print(f"Process started: {pid}")

    @app.command()
    def log(
        msg_id: str = typer.Argument(..., help="Message ID"),
    ):
        log_content = get_dispatch_log(msg_id)
        if log_content:
            print(log_content)
        else:
            print(f"No log found for: {msg_id}")

    @app.command()
    def models():
        print("Supported models:")
        for model, cmd in MODEL_COMMANDS.items():
            print(f"  {model}: {' '.join(cmd)}")

    app()
