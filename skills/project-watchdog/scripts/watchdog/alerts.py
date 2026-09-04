"""Human alerting at the receipt boundary, composed from $ops-discord.

project-watchdog owns no Discord code, tokens, or webhook config. When an
eventful receipt needs a human's eyes (``BLOCKED``, ``NEEDS_ATTENTION``, or an
``idle_streak_exceeded`` escalation) this module shells out to the sibling
``ops-discord`` skill's ``notify`` command. ops-discord resolves the webhook
named ``watchdog`` from ``OPS_DISCORD_WEBHOOK_WATCHDOG_URL`` (env or
``~/.zshrc``, which matters under cron).

Guarantees, in order of importance:

- Alert delivery failure NEVER fails the tick. The outcome is recorded on the
  receipt under ``alert`` either way.
- Repeating blockers are deduplicated: one post per fingerprint per
  ``PROJECT_WATCHDOG_ALERT_RENOTIFY_SECONDS`` (default 24h), not one per
  5-minute cron tick. memory#158 re-emitted the same BLOCKED receipt for days;
  a per-tick post would just move that noise to Discord.
- Dry-run ticks pass ``--dry-run`` to ops-discord so nothing is posted.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import time
from pathlib import Path
from typing import Any

from . import config

#: Receipt statuses that a human should hear about.
ALERT_STATUSES = frozenset({"BLOCKED", "NEEDS_ATTENTION"})

DEFAULT_RENOTIFY_SECONDS = 86400
WEBHOOK_NAME = "watchdog"
#: The operator's live Discord transport is the bot token in ~/.zshrc, not a
#: webhook (verified 2026-09-03: only SLACK_WEBHOOK_URL is a webhook there,
#: while DISCORD_BOT_TOKEN + guild resolve channel #horus). Default to the bot
#: channel; override with PROJECT_WATCHDOG_ALERT_CHANNEL, or force the webhook
#: path by exporting OPS_DISCORD_WEBHOOK_WATCHDOG_URL.
DEFAULT_BOT_CHANNEL = "horus"

#: Sibling skill, resolved from this skill's own location so it follows the
#: checkout it runs from (same pattern as config.ASK_RUN_SH).
OPS_DISCORD_RUN_SH = config.SKILL_DIR.parent / "ops-discord" / "run.sh"


def _renotify_seconds() -> int:
    raw = os.environ.get("PROJECT_WATCHDOG_ALERT_RENOTIFY_SECONDS")
    try:
        return int(raw) if raw else DEFAULT_RENOTIFY_SECONDS
    except ValueError:
        return DEFAULT_RENOTIFY_SECONDS


def _alerts_state_path() -> Path:
    return config.state_root() / "alerts.json"


def _fingerprint(receipt: dict[str, Any]) -> str:
    """Stable identity of the condition, not the tick.

    Same project + status + stop_reason + per-issue (issue, status, summary)
    tuples → same fingerprint, so a blocker that repeats every 5 minutes posts
    once per renotify window.
    """
    issues = [
        (h.get("issue_number"), h.get("status"), h.get("summary"))
        for h in receipt.get("handled_issues") or []
    ]
    key = json.dumps(
        [
            receipt.get("project"),
            receipt.get("status"),
            receipt.get("stop_reason"),
            issues,
        ],
        sort_keys=True,
        default=str,
    )
    return hashlib.sha256(key.encode()).hexdigest()[:16]


def _should_alert(receipt: dict[str, Any]) -> bool:
    if os.environ.get("PROJECT_WATCHDOG_ALERTS", "").lower() in {"off", "0", "false"}:
        return False
    if receipt.get("status") in ALERT_STATUSES:
        return True
    if receipt.get("stop_reason") == "idle_streak_exceeded":
        return True
    # A completed ticket is human-notable good news (operator 2026-09-03):
    # notify when a tick actually handled a ticket to completion. NOOP fleet
    # rotation stays silent.
    if receipt.get("status") == "COMPLETED" and any(
        h.get("status") == "COMPLETED" for h in receipt.get("handled_issues") or []
    ):
        return True
    return False


def _render_content(receipt: dict[str, Any]) -> str:
    lines = [
        f"status={receipt.get('status')} stop_reason={receipt.get('stop_reason')}",
        f"run_id={receipt.get('run_id')} receipt={receipt.get('receipt_path') or receipt.get('receipt_dir')}",
    ]
    for handled in (receipt.get("handled_issues") or [])[:5]:
        summary = (handled.get("summary") or "")[:300]
        lines.append(
            f"#{handled.get('issue_number')} [{handled.get('status')}] {summary}"
        )
    for error in (receipt.get("errors") or [])[:3]:
        lines.append(f"error: {str(error)[:300]}")
    return "\n".join(lines)[:1800]


def maybe_alert(receipt: dict[str, Any]) -> None:
    """Post a human alert for this receipt through $ops-discord, best effort.

    Mutates ``receipt['alert']`` with the outcome. Never raises.
    """
    try:
        if not _should_alert(receipt):
            return
        fingerprint = _fingerprint(receipt)
        state_path = _alerts_state_path()
        now = time.time()
        try:
            state = json.loads(state_path.read_text())
        except (OSError, ValueError):
            state = {}
        last = state.get(fingerprint, 0)
        if now - last < _renotify_seconds():
            receipt["alert"] = {
                "status": "DEDUPED",
                "fingerprint": fingerprint,
                "last_sent_at": last,
            }
            return
        dry_run = not receipt.get("apply", False) or bool(
            os.environ.get("PROJECT_WATCHDOG_ALERT_DRY_RUN")
        )
        if not OPS_DISCORD_RUN_SH.exists():
            receipt["alert"] = {
                "status": "OPS_DISCORD_MISSING",
                "fingerprint": fingerprint,
                "run_sh": str(OPS_DISCORD_RUN_SH),
            }
            return
        argv = [str(OPS_DISCORD_RUN_SH), "notify"]
        if os.environ.get(f"OPS_DISCORD_WEBHOOK_{WEBHOOK_NAME.upper()}_URL"):
            argv += ["--webhook", WEBHOOK_NAME]
        else:
            channel = os.environ.get(
                "PROJECT_WATCHDOG_ALERT_CHANNEL", DEFAULT_BOT_CHANNEL
            )
            argv += ["--discord-bot", "--channel-name", channel]
        argv += [
            "--title",
            f"project-watchdog {receipt.get('status')}",
            "--content",
            _render_content(receipt),
            "--json",
        ]
        if dry_run:
            argv.append("--dry-run")
        proc = subprocess.run(
            argv, capture_output=True, text=True, timeout=30, check=False
        )
        try:
            notify_receipt = json.loads(proc.stdout)
        except ValueError:
            notify_receipt = {"raw_stdout": proc.stdout[-500:]}
        # A real delivery is the ONLY thing that may advance the dedupe clock.
        # A zero exit is not delivery: a dry run exits zero, and an unverified
        # webhook send exits zero without proof anything was posted. Requiring
        # status==SENT plus a message_id/message_url means a dry run or a
        # silent no-op cannot suppress the next real notification
        # (WebGPT P0, 2026-09-04).
        exit_ok = proc.returncode == 0
        message_ref = notify_receipt.get("message_id") or notify_receipt.get("message_url")
        really_delivered = (
            not dry_run
            and notify_receipt.get("status") == "SENT"
            and bool(message_ref)
        )
        receipt["alert"] = {
            "status": notify_receipt.get("status")
            or ("SENT" if exit_ok else "ALERT_DELIVERY_FAILED"),
            "delivered": really_delivered,
            "dry_run": dry_run,
            "message_ref": message_ref,
            "fingerprint": fingerprint,
            "exit_code": proc.returncode,
            "notify_receipt": notify_receipt,
        }
        if not exit_ok:
            receipt["alert"]["status"] = "ALERT_DELIVERY_FAILED"
            receipt["alert"]["stderr"] = proc.stderr[-500:]
        if really_delivered:
            state[fingerprint] = now
            state_path.parent.mkdir(parents=True, exist_ok=True)
            state_path.write_text(json.dumps(state, indent=2, sort_keys=True))
    except Exception as exc:  # noqa: BLE001 - alerting must never fail the tick
        receipt["alert"] = {
            "status": "ALERT_DELIVERY_FAILED",
            "error": str(exc)[:300],
        }
