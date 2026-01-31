#!/usr/bin/env python3
"""
AI-Powered Bug Triage Module for Agent-Inbox.

Features:
- Severity classification using LLM
- Auto-routing based on file paths in error messages
- Triage logging for audit trail
- Webhook notifications on status changes

Based on research from:
- n8n AI Bug Triage workflows
- LlamaIndex multi-agent patterns
- Enterprise bug triage best practices (60-70% time reduction)
"""
import json
import os
import re
import subprocess
import urllib.request
import urllib.error
import logging
import socket
import ipaddress
from urllib.parse import urlparse
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Dict, List, Tuple, Any

# Configuration
INBOX_DIR = Path(os.environ.get("AGENT_INBOX_DIR", Path.home() / ".agent-inbox"))
TRIAGE_LOG_DIR = INBOX_DIR / "triage_logs"
WEBHOOKS_FILE = INBOX_DIR / "webhooks.json"

# Logging setup
logger = logging.getLogger("agent_inbox.triage")
if not logger.handlers:
    logging.basicConfig(level=os.environ.get("AGENT_INBOX_LOG_LEVEL", "WARNING"))

# Valid webhook events
VALID_EVENTS = {"message_sent", "status_changed", "message_acked"}

# Cache for webhook URL validation (avoid repeated DNS lookups)
_webhook_validation_cache: Dict[str, bool] = {}

# Severity levels with descriptions
SEVERITY_LEVELS = {
    "critical": {
        "priority": "critical",
        "indicators": ["crash", "data loss", "security", "production down", "blocking"],
        "response_time": "immediate",
        "model_recommendation": "opus-4.5",
    },
    "high": {
        "priority": "high",
        "indicators": ["error", "exception", "failure", "broken", "regression"],
        "response_time": "same day",
        "model_recommendation": "opus-4.5",
    },
    "medium": {
        "priority": "normal",
        "indicators": ["bug", "issue", "incorrect", "unexpected", "wrong"],
        "response_time": "this sprint",
        "model_recommendation": "sonnet",
    },
    "low": {
        "priority": "low",
        "indicators": ["typo", "cosmetic", "enhancement", "minor", "polish"],
        "response_time": "backlog",
        "model_recommendation": "sonnet",
    },
}


def _ensure_dirs():
    """Ensure triage directories exist."""
    TRIAGE_LOG_DIR.mkdir(parents=True, exist_ok=True)


def _load_registry() -> Dict[str, str]:
    """Load project registry."""
    registry_file = INBOX_DIR / "projects.json"
    if registry_file.exists():
        try:
            return json.loads(registry_file.read_text())
        except Exception as e:
            logger.warning("Failed to load registry: %s", e)
    return {}


def _atomic_write(path: Path, data: str) -> bool:
    """Write atomically to a file to reduce race conditions."""
    try:
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(data)
        tmp.replace(path)  # Atomic on POSIX systems
        return True
    except Exception as e:
        logger.error("Atomic write failed for %s: %s", path, e)
        return False


def _is_ip(addr: str) -> bool:
    """Check if addr is a valid IP address."""
    try:
        ipaddress.ip_address(addr)
        return True
    except Exception:
        return False


def _is_private_or_localhost(host: str) -> bool:
    """Detect localhost or private IPs; skip DNS for obvious public hosts."""
    try:
        if not host or host in ("localhost",):
            return True
        if _is_ip(host):
            ip = ipaddress.ip_address(host)
        else:
            # Heuristic: if host has public-looking TLD, skip resolution
            public_like = any(host.endswith(tld) for tld in (".com", ".org", ".net", ".io", ".dev", ".co"))
            if public_like:
                return False
            ip = ipaddress.ip_address(socket.gethostbyname(host))
        return ip.is_loopback or ip.is_private or ip.is_link_local
    except Exception:
        # If resolution fails, be conservative and block
        return True


def _is_valid_webhook_url(url: str) -> bool:
    """Webhook URL validation with HTTPS default and private IP blocking.

    Environment variables:
        ALLOW_HTTP_WEBHOOKS=1: Allow http:// URLs (default: https only)
        ALLOW_PRIVATE_WEBHOOKS=1: Allow localhost/private IPs (default: blocked)
    """
    if url in _webhook_validation_cache:
        return _webhook_validation_cache[url]

    try:
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            _webhook_validation_cache[url] = False
            return False
        if not parsed.netloc:
            _webhook_validation_cache[url] = False
            return False

        # Enforce HTTPS by default unless explicitly allowed
        allow_http = os.environ.get("ALLOW_HTTP_WEBHOOKS", "").lower() in ("1", "true", "yes")
        if parsed.scheme == "http" and not allow_http:
            logger.warning("HTTP webhook blocked (set ALLOW_HTTP_WEBHOOKS=1 to allow): %s", url)
            _webhook_validation_cache[url] = False
            return False

        # Block localhost/private unless whitelisted
        allow_private = os.environ.get("ALLOW_PRIVATE_WEBHOOKS", "").lower() in ("1", "true", "yes")
        if not allow_private and _is_private_or_localhost(parsed.hostname or ""):
            logger.warning("Private/localhost webhook blocked (set ALLOW_PRIVATE_WEBHOOKS=1 to allow): %s", url)
            _webhook_validation_cache[url] = False
            return False

        _webhook_validation_cache[url] = True
        return True
    except Exception as e:
        logger.error("Webhook URL validation error for %s: %s", url, e)
        _webhook_validation_cache[url] = False
        return False


def _validate_events(events: Optional[List[str]]) -> Optional[List[str]]:
    """Validate and filter webhook events to valid set."""
    if not events:
        return None
    valid = [e.strip() for e in events if e.strip() in VALID_EVENTS]
    if len(valid) != len(events):
        invalid = set(events) - VALID_EVENTS
        logger.warning("Invalid webhook events filtered out: %s", sorted(invalid))
    return valid or None


# ============================================================================
# AI Severity Classification
# ============================================================================

def classify_severity_heuristic(message: str) -> Tuple[str, List[str]]:
    """Classify severity using keyword heuristics.

    Fast fallback when LLM is unavailable.

    Args:
        message: Bug description

    Returns:
        (severity, matched_indicators)
    """
    message_lower = message.lower()

    for severity, config in SEVERITY_LEVELS.items():
        matched = [ind for ind in config["indicators"] if ind in message_lower]
        if matched:
            return severity, matched

    return "medium", []  # Default to medium


def classify_severity_llm(message: str, context: Optional[str] = None) -> Dict[str, Any]:
    """Classify severity using LLM for better accuracy.

    Uses Claude/Codex to analyze the bug and determine:
    - Severity level
    - Recommended priority
    - Suggested model for fix
    - Reasoning

    Args:
        message: Bug description
        context: Optional additional context (stack traces, etc.)

    Returns:
        Classification result dict
    """
    prompt = f"""Analyze this bug report and classify its severity.

Bug Report:
{message}

{f"Additional Context:{chr(10)}{context}" if context else ""}

Respond with a JSON object containing:
- severity: one of "critical", "high", "medium", "low"
- priority: the priority level for task tracking
- reasoning: brief explanation of your classification (1-2 sentences)
- suggested_model: recommended AI model ("opus-4.5" for complex, "sonnet" for simple)
- estimated_complexity: "simple", "moderate", or "complex"
- affected_area: likely area of codebase affected (if detectable)

JSON response:"""

    # Try to use claude CLI for classification
    try:
        result = subprocess.run(
            ["claude", "--model", "haiku", "-p", prompt, "--output-format", "json"],
            capture_output=True,
            text=True,
            timeout=30,
        )

        if result.returncode == 0:
            # Parse JSON from output - try direct parse first, then extract
            output = result.stdout.strip()
            try:
                return json.loads(output)
            except json.JSONDecodeError:
                # Fallback: extract JSON object from output
                start = output.find("{")
                end = output.rfind("}")
                if start != -1 and end != -1 and end > start:
                    try:
                        return json.loads(output[start:end + 1])
                    except json.JSONDecodeError:
                        logger.warning("Failed to parse LLM JSON output")
    except subprocess.TimeoutExpired:
        logger.warning("LLM classification timed out")
    except FileNotFoundError:
        logger.debug("Claude CLI not found, using heuristics")
    except Exception as e:
        logger.warning("LLM classification failed: %s", e)

    # Fallback to heuristic
    severity, indicators = classify_severity_heuristic(message)
    config = SEVERITY_LEVELS[severity]

    return {
        "severity": severity,
        "priority": config["priority"],
        "reasoning": f"Heuristic match on indicators: {indicators}" if indicators else "Default classification",
        "suggested_model": config["model_recommendation"],
        "estimated_complexity": "moderate",
        "affected_area": "unknown",
        "method": "heuristic",
    }


# ============================================================================
# Auto-Routing
# ============================================================================

def extract_file_paths(text: str) -> List[str]:
    """Extract file paths from error messages and stack traces.

    Args:
        text: Bug description or stack trace

    Returns:
        List of detected file paths
    """
    patterns = [
        # Python traceback: File "/path/to/file.py", line 123
        r'File "([^"]+\.py)"',
        # JavaScript/Node: at /path/to/file.js:123
        r'at\s+(?:\S+\s+\()?(/[^\s:]+\.[jt]sx?)',
        # Generic path patterns
        r'(/[a-zA-Z0-9_/.-]+\.[a-zA-Z]+)(?::\d+)?',
        # Relative paths: src/module/file.py
        r'\b((?:src|lib|app|packages)/[a-zA-Z0-9_/.-]+\.[a-zA-Z]+)',
    ]

    paths = set()
    for pattern in patterns:
        for match in re.finditer(pattern, text):
            path = match.group(1)
            # Filter out common false positives
            if not any(x in path for x in ['/usr/', '/lib/', '/node_modules/', '.so', '.dll']):
                paths.add(path)

    return list(paths)


def detect_project_from_paths(file_paths: List[str]) -> Optional[str]:
    """Detect target project from file paths.

    Matches file paths against registered project directories.

    Args:
        file_paths: List of file paths extracted from error

    Returns:
        Project name if detected, None otherwise
    """
    registry = _load_registry()

    for path in file_paths:
        # Skip suspicious traversal attempts
        try:
            path_obj = Path(path)
        except Exception:
            continue
        if any(part == ".." for part in path_obj.parts):
            logger.debug("Skipping path with traversal: %s", path)
            continue

        # Try to resolve absolute paths
        if path_obj.is_absolute():
            for project_name, project_path in registry.items():
                try:
                    project_dir = Path(project_path).resolve()
                    if path_obj.resolve().is_relative_to(project_dir):
                        return project_name
                except (ValueError, OSError):
                    pass

        # Try to match relative paths
        for project_name, project_path in registry.items():
            project_dir = Path(project_path)
            # Check if path component matches project structure
            if project_name in path or any(
                part in path for part in project_dir.parts[-3:]
            ):
                return project_name

    return None


def auto_route(message: str, context_files: Optional[List[Dict]] = None) -> Optional[str]:
    """Automatically determine target project from message content.

    Args:
        message: Bug description
        context_files: Optional list of context file dicts

    Returns:
        Suggested project name or None
    """
    # Extract paths from message
    paths = extract_file_paths(message)

    # Also extract from context files
    if context_files:
        for ctx in context_files:
            content = ctx.get("content", "")
            paths.extend(extract_file_paths(content))
            # Also use the file path itself
            if ctx.get("path"):
                paths.append(ctx["path"])

    if paths:
        project = detect_project_from_paths(paths)
        if project:
            return project

    return None


# ============================================================================
# Triage Logging
# ============================================================================

def log_triage(
    msg_id: str,
    classification: Dict[str, Any],
    routing: Optional[str] = None,
    manual_override: bool = False,
) -> Path:
    """Log triage decision for audit trail.

    Args:
        msg_id: Message ID
        classification: Classification result dict
        routing: Target project (auto or manual)
        manual_override: Whether classification was manually overridden

    Returns:
        Path to triage log file
    """
    _ensure_dirs()

    log_entry = {
        "msg_id": msg_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "classification": classification,
        "routing": {
            "target_project": routing,
            "method": "manual" if manual_override else "auto",
        },
        "manual_override": manual_override,
    }

    # Write individual log file atomically
    log_file = TRIAGE_LOG_DIR / f"{msg_id}_triage.json"
    if not _atomic_write(log_file, json.dumps(log_entry, indent=2)):
        logger.error("Failed to write triage log for %s", msg_id)

    # Append to daily aggregate log (append is atomic on most systems)
    daily_log = TRIAGE_LOG_DIR / f"triage_{datetime.now().strftime('%Y%m%d')}.jsonl"
    try:
        with open(daily_log, "a") as f:
            f.write(json.dumps(log_entry) + "\n")
    except Exception as e:
        logger.error("Failed to append to daily triage log: %s", e)

    return log_file


def get_triage_log(msg_id: str) -> Optional[Dict]:
    """Get triage log for a message.

    Args:
        msg_id: Message ID

    Returns:
        Triage log dict or None
    """
    log_file = TRIAGE_LOG_DIR / f"{msg_id}_triage.json"
    if log_file.exists():
        return json.loads(log_file.read_text())
    return None


# ============================================================================
# Webhook Notifications
# ============================================================================

def _load_webhooks() -> List[Dict]:
    """Load webhook configurations."""
    if WEBHOOKS_FILE.exists():
        try:
            return json.loads(WEBHOOKS_FILE.read_text())
        except Exception:
            pass
    return []


def _save_webhooks(webhooks: List[Dict]) -> bool:
    """Save webhook configurations atomically."""
    INBOX_DIR.mkdir(parents=True, exist_ok=True)
    return _atomic_write(WEBHOOKS_FILE, json.dumps(webhooks, indent=2))


def register_webhook(url: str, events: List[str] = None, project: str = None) -> bool:
    """Register a webhook for notifications.

    Args:
        url: Webhook URL to POST to
        events: List of events to trigger on (default: all)
        project: Optional project filter

    Returns:
        True if registered, False if validation failed
    """
    # Validate URL before registering
    if not _is_valid_webhook_url(url):
        logger.error("Invalid webhook URL rejected: %s", url)
        return False

    # Validate and filter events
    validated_events = _validate_events(events)
    final_events = validated_events or ["message_sent", "status_changed", "message_acked"]

    webhooks = _load_webhooks()

    webhook = {
        "url": url,
        "events": final_events,
        "project": project,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    # Check for duplicate
    for existing in webhooks:
        if existing["url"] == url and existing.get("project") == project:
            existing.update(webhook)
            return _save_webhooks(webhooks)

    webhooks.append(webhook)
    return _save_webhooks(webhooks)


def unregister_webhook(url: str) -> bool:
    """Unregister a webhook.

    Args:
        url: Webhook URL to remove

    Returns:
        True if removed
    """
    webhooks = _load_webhooks()
    original_len = len(webhooks)
    webhooks = [w for w in webhooks if w["url"] != url]

    if len(webhooks) < original_len:
        _save_webhooks(webhooks)
        return True
    return False


def trigger_webhooks(event: str, data: Dict):
    """Trigger webhooks for an event.

    Args:
        event: Event type (message_sent, status_changed, message_acked)
        data: Event data to send
    """
    # Validate event type
    if event not in VALID_EVENTS:
        logger.warning("Invalid webhook event type: %s", event)
        return

    webhooks = _load_webhooks()

    for webhook in webhooks:
        # Check event filter
        if event not in webhook.get("events", []):
            continue

        # Check project filter
        if webhook.get("project") and data.get("to") != webhook["project"]:
            continue

        # Validate URL before sending (re-validate in case config was manually edited)
        url = webhook.get("url", "")
        if not _is_valid_webhook_url(url):
            logger.warning("Skipping invalid webhook URL: %s", url)
            continue

        # Send webhook
        try:
            payload = {
                "event": event,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "data": data,
            }

            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode(),
                headers={
                    "Content-Type": "application/json",
                    "User-Agent": "agent-inbox/2.0",
                },
                method="POST",
            )

            with urllib.request.urlopen(req, timeout=10) as resp:
                logger.debug("Webhook sent to %s: %s", url, resp.status)

        except urllib.error.HTTPError as e:
            logger.warning("Webhook HTTP error for %s: %s", url, e.code)
        except urllib.error.URLError as e:
            logger.warning("Webhook URL error for %s: %s", url, e.reason)
        except TimeoutError:
            logger.warning("Webhook timeout for %s", url)
        except Exception as e:
            logger.error("Webhook error for %s: %s", url, e)


# ============================================================================
# High-Level Triage Function
# ============================================================================

def triage_message(
    message: str,
    context_files: Optional[List[Dict]] = None,
    use_llm: bool = True,
) -> Dict[str, Any]:
    """Perform full triage on a message.

    Combines AI classification, auto-routing, and logging.

    Args:
        message: Bug description
        context_files: Optional context files
        use_llm: Whether to use LLM for classification

    Returns:
        Triage result with classification, routing, and recommendations
    """
    # Build context string from files
    context = None
    if context_files:
        context_parts = []
        for ctx in context_files:
            context_parts.append(f"File: {ctx.get('file', 'unknown')}")
            context_parts.append(ctx.get("content", "")[:2000])
        context = "\n".join(context_parts)

    # Classify severity
    if use_llm:
        classification = classify_severity_llm(message, context)
    else:
        severity, indicators = classify_severity_heuristic(message)
        classification = {
            "severity": severity,
            "priority": SEVERITY_LEVELS[severity]["priority"],
            "reasoning": f"Matched indicators: {indicators}" if indicators else "Default",
            "suggested_model": SEVERITY_LEVELS[severity]["model_recommendation"],
            "method": "heuristic",
        }

    # Auto-route
    suggested_project = auto_route(message, context_files)

    # Build result
    result = {
        "classification": classification,
        "suggested_project": suggested_project,
        "suggested_priority": classification.get("priority", "normal"),
        "suggested_model": classification.get("suggested_model", "sonnet"),
        "auto_route_confidence": "high" if suggested_project else "none",
    }

    return result


# ============================================================================
# CLI
# ============================================================================

if __name__ == "__main__":
    import sys
    import argparse

    parser = argparse.ArgumentParser(description="Agent-Inbox Triage Module")
    subparsers = parser.add_subparsers(dest="command")

    # classify
    p_classify = subparsers.add_parser("classify", help="Classify a bug message")
    p_classify.add_argument("message", help="Bug message to classify")
    p_classify.add_argument("--no-llm", action="store_true", help="Use heuristics only")

    # route
    p_route = subparsers.add_parser("route", help="Auto-detect target project")
    p_route.add_argument("message", help="Bug message with file paths")

    # triage
    p_triage = subparsers.add_parser("triage", help="Full triage (classify + route)")
    p_triage.add_argument("message", help="Bug message")
    p_triage.add_argument("--no-llm", action="store_true", help="Use heuristics only")

    # webhook
    p_webhook = subparsers.add_parser("webhook", help="Manage webhooks")
    p_webhook.add_argument("action", choices=["add", "remove", "list"])
    p_webhook.add_argument("--url", help="Webhook URL")
    p_webhook.add_argument("--events", help="Comma-separated events")
    p_webhook.add_argument("--project", help="Project filter")

    # log
    p_log = subparsers.add_parser("log", help="View triage log")
    p_log.add_argument("msg_id", help="Message ID")

    args = parser.parse_args()

    if args.command == "classify":
        result = classify_severity_llm(args.message) if not args.no_llm else None
        if not result:
            severity, indicators = classify_severity_heuristic(args.message)
            result = {"severity": severity, "indicators": indicators}
        print(json.dumps(result, indent=2))

    elif args.command == "route":
        project = auto_route(args.message)
        if project:
            print(f"Suggested project: {project}")
        else:
            print("Could not auto-detect project")

    elif args.command == "triage":
        result = triage_message(args.message, use_llm=not args.no_llm)
        print(json.dumps(result, indent=2))

    elif args.command == "webhook":
        if args.action == "add":
            if not args.url:
                print("Error: --url required")
                sys.exit(1)
            events = args.events.split(",") if args.events else None
            if register_webhook(args.url, events, args.project):
                print(f"Webhook registered: {args.url}")
            else:
                print("Error: Invalid webhook URL (must be HTTPS to public host)")
                print("  Set ALLOW_HTTP_WEBHOOKS=1 to allow HTTP")
                print("  Set ALLOW_PRIVATE_WEBHOOKS=1 to allow localhost/private IPs")
                sys.exit(1)

        elif args.action == "remove":
            if not args.url:
                print("Error: --url required")
                sys.exit(1)
            if unregister_webhook(args.url):
                print(f"Webhook removed: {args.url}")
            else:
                print("Webhook not found")

        elif args.action == "list":
            webhooks = _load_webhooks()
            if webhooks:
                for wh in webhooks:
                    print(f"  {wh['url']} - events: {wh.get('events', ['all'])}")
            else:
                print("No webhooks registered")

    elif args.command == "log":
        log = get_triage_log(args.msg_id)
        if log:
            print(json.dumps(log, indent=2))
        else:
            print(f"No triage log for: {args.msg_id}")

    else:
        parser.print_help()
