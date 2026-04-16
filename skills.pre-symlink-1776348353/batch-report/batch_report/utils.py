"""Common utilities for batch-report skill.

This module provides shared utility functions used across the batch-report
skill modules, including JSON loading, YAML config, and agent inbox integration.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Optional

from rich.console import Console

from batch_report.config import (
    AGENT_INBOX_SCRIPT,
    BATCH_CONFIG_PATH,
    BatchFormat,
)

try:
    import yaml

    HAS_YAML = True
except ImportError:
    yaml = None
    HAS_YAML = False

console = Console()

_WARNED_NO_YAML = False


def load_json(path: Path) -> dict:
    """Load JSON file safely.

    Args:
        path: Path to the JSON file.

    Returns:
        Parsed JSON as dict, or dict with _error key on failure.
    """
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        return {"_error": str(e), "_path": str(path)}


def load_batch_config() -> dict:
    """Load batch configuration from YAML.

    Returns:
        Configuration dict with 'batches' and 'settings' keys.
    """
    if not HAS_YAML:
        global _WARNED_NO_YAML
        if not _WARNED_NO_YAML:
            console.print("[yellow]Warning: PyYAML not installed; batch config disabled[/]")
            _WARNED_NO_YAML = True
        return {"batches": {}, "settings": {}}

    if not BATCH_CONFIG_PATH.exists():
        return {"batches": {}, "settings": {}}

    try:
        with open(BATCH_CONFIG_PATH, encoding="utf-8") as f:
            return yaml.safe_load(f) or {"batches": {}, "settings": {}}
    except Exception as e:
        console.print(f"[yellow]Warning: Could not load batch config: {e}[/]")
        return {"batches": {}, "settings": {}}


def get_batch_type_config(batch_type: str) -> dict:
    """Get configuration for a specific batch type.

    Args:
        batch_type: The batch type identifier.

    Returns:
        Configuration dict for the batch type.
    """
    config = load_batch_config()
    return config.get("batches", {}).get(batch_type, {})


def detect_batch_format(output_dir: Path) -> BatchFormat:
    """Auto-detect batch format from directory structure.

    Args:
        output_dir: Path to the batch output directory.

    Returns:
        Detected BatchFormat enum value.
    """
    # Check for extractor format (manifest.json, timings_summary.json)
    manifests = list(output_dir.glob("*/manifest.json"))
    if manifests and list(output_dir.glob("*/timings_summary.json")):
        return BatchFormat.extractor

    # Check for youtube transcripts format
    state_file = output_dir / ".batch_state.json"
    if state_file.exists():
        state = load_json(state_file)
        # Prefer explicit batch_type when available
        bt = (state.get("batch_type") or "").lower()
        if bt == "youtube":
            return BatchFormat.youtube
        # Heuristic fallback based on description content
        if "description" in state and "transcript" in state.get("description", "").lower():
            return BatchFormat.youtube

    # Check for generic state file
    if state_file.exists():
        return BatchFormat.generic

    # Fallback to generic
    return BatchFormat.generic


def send_to_agent_inbox(
    project: str, report: str, priority: str = "normal"
) -> Optional[str]:
    """Send report to agent-inbox.

    Args:
        project: Target project name.
        report: Report content to send.
        priority: Message priority (normal, high, low).

    Returns:
        Message ID if successful, None otherwise.
    """
    if not AGENT_INBOX_SCRIPT or not AGENT_INBOX_SCRIPT.exists():
        if AGENT_INBOX_SCRIPT:
            console.print(
                f"[yellow]Warning: agent-inbox not found at {AGENT_INBOX_SCRIPT}[/]"
            )
        else:
            console.print(
                "[yellow]Warning: agent-inbox script not configured[/]"
            )
        return None

    try:
        result = subprocess.run(
            [
                sys.executable,
                str(AGENT_INBOX_SCRIPT),
                "send",
                "--to",
                project,
                "--type",
                "bug",
                "--priority",
                priority,
                report,
            ],
            capture_output=True,
            text=True,
            cwd=AGENT_INBOX_SCRIPT.parent,
        )

        if result.returncode == 0:
            # Extract message ID from output
            for line in result.stdout.splitlines():
                if "Message sent:" in line:
                    return line.split("Message sent:")[-1].strip()
        else:
            console.print(f"[red]Failed to send to agent-inbox: {result.stderr}[/]")
    except Exception as e:
        console.print(f"[red]Error sending to agent-inbox: {e}[/]")

    return None
