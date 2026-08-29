"""Morning Discord/Slack handoff for the opportunity report."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any

from .util import read_json, utc_now, write_json


def _default_report_url(run_dir: Path) -> str:
    return f"file://{run_dir}/report/index.html"


def _counts_from(nightly: dict[str, Any], digest: dict[str, Any]) -> dict[str, Any]:
    counts = digest.get("counts")
    if isinstance(counts, dict):
        return counts
    steps = nightly.get("steps") if isinstance(nightly.get("steps"), dict) else {}
    digest_step = steps.get("digest") if isinstance(steps.get("digest"), dict) else {}
    step_counts = digest_step.get("counts")
    return step_counts if isinstance(step_counts, dict) else {}


def _top_items(digest: dict[str, Any], limit: int) -> list[dict[str, Any]]:
    items = digest.get("top")
    if not isinstance(items, list):
        return []
    return [item for item in items[:limit] if isinstance(item, dict)]


def build_morning_discord_message(
    run_dir: Path,
    *,
    report_url: str | None = None,
    max_items: int = 5,
) -> dict[str, Any]:
    nightly_path = run_dir / "nightly-receipt.json"
    digest_path = run_dir / "morning-digest.json"
    nightly = read_json(nightly_path)
    digest = read_json(digest_path)
    steps = nightly.get("steps") if isinstance(nightly.get("steps"), dict) else {}
    counts = _counts_from(nightly, digest)
    linkedin = steps.get("browser_capture_linkedin") if isinstance(steps.get("browser_capture_linkedin"), dict) else {}
    memory_sync = steps.get("memory_sync") if isinstance(steps.get("memory_sync"), dict) else {}
    contacts = steps.get("suggested_contacts") if isinstance(steps.get("suggested_contacts"), dict) else {}
    url = report_url or _default_report_url(run_dir)

    lines = [
        "monitor-opportunities morning handoff",
        f"status={nightly.get('status')} mode={nightly.get('mode')}",
        f"report={url}",
        (
            "counts="
            f"{counts.get('employment', 0)} employment, "
            f"{counts.get('consulting', 0)} consulting, "
            f"{counts.get('total', 0)} total"
        ),
        (
            "linkedin="
            f"top_applicant={linkedin.get('top_applicant_count', 0)} "
            f"easy_apply={linkedin.get('easy_apply_count', 0)} "
            f"captured={linkedin.get('captured', 0)}"
        ),
        (
            "memory="
            f"exit_code={memory_sync.get('exit_code')} "
            f"readback={memory_sync.get('readback_found')} "
            f"relationship_readback={memory_sync.get('relationship_readback_found')}"
        ),
        (
            "contacts="
            f"suggestions={contacts.get('suggestions', 0)} "
            f"mandate_relevant={contacts.get('mandate_relevant', 0)}"
        ),
        "",
        "Discuss and authorize exact actions only. Easy Apply is a signal, not automatic submit.",
        "",
        "Top rows:",
    ]

    for index, item in enumerate(_top_items(digest, max_items), start=1):
        action = item.get("action") if isinstance(item.get("action"), dict) else {}
        apply_url = action.get("apply_on_site") or item.get("apply_url") or ""
        inmail_target = item.get("inmail_target") if isinstance(item.get("inmail_target"), dict) else {}
        target = str(inmail_target.get("name") or "").strip()
        score = item.get("response_score")
        score_text = f" score={score}" if score is not None else ""
        line = f"{index}. {item.get('organization')} - {item.get('title')} ({item.get('opportunity_type')}){score_text}"
        if target:
            line += f"; contact={target}"
        if apply_url:
            line += f"; apply={apply_url}"
        lines.append(line[:450])

    content = "\n".join(lines)
    return {
        "schema": "monitor_opportunities.morning_discord_handoff.v1",
        "run": str(run_dir),
        "nightly_receipt": str(nightly_path),
        "digest": str(digest_path),
        "report_url": url,
        "title": "monitor-opportunities morning handoff",
        "content": content[:1900],
        "counts": counts,
        "linkedin": {
            "top_applicant_count": linkedin.get("top_applicant_count", 0),
            "easy_apply_count": linkedin.get("easy_apply_count", 0),
            "captured": linkedin.get("captured", 0),
        },
        "top_count": len(_top_items(digest, max_items)),
        "external_effects": False,
    }


def send_morning_discord_handoff(
    *,
    run_dir: Path,
    workdir: Path,
    ops_discord_run: Path,
    out: Path,
    webhook: str | None = None,
    discord_bot: bool = False,
    channel_id: str | None = None,
    channel_name: str | None = None,
    report_url: str | None = None,
    post: bool = False,
    max_items: int = 5,
) -> dict[str, Any]:
    payload = build_morning_discord_message(run_dir, report_url=report_url, max_items=max_items)
    out.parent.mkdir(parents=True, exist_ok=True)
    payload_path = out.parent / "morning-discord-message.json"
    write_json(payload_path, payload)

    resolved_webhook = webhook or os.getenv("MONITOR_OPPORTUNITIES_MORNING_DISCORD_WEBHOOK") or "slack"
    resolved_channel_name = channel_name or os.getenv("MONITOR_OPPORTUNITIES_MORNING_DISCORD_CHANNEL") or "horus"
    command = [
        str(ops_discord_run),
        "notify",
        "--title",
        str(payload["title"]),
        "--content",
        str(payload["content"]),
        "--json",
    ]
    if discord_bot:
        command.append("--discord-bot")
        if channel_id:
            command.extend(["--channel-id", channel_id])
        else:
            command.extend(["--channel-name", resolved_channel_name])
    else:
        command.extend(["--webhook", resolved_webhook])
    if not post:
        command.append("--dry-run")

    receipt: dict[str, Any] = {
        "schema": "monitor_opportunities.morning_discord_handoff_receipt.v1",
        "generated_at": utc_now(),
        "status": "PENDING",
        "run": str(run_dir),
        "payload": str(payload_path),
        "ops_discord_run": str(ops_discord_run),
        "command": command,
        "dry_run": not post,
        "external_effects": bool(post),
        "transport": "discord_bot" if discord_bot else "webhook",
        "webhook": None if discord_bot else resolved_webhook,
        "channel_id": channel_id,
        "channel_name": resolved_channel_name if discord_bot and not channel_id else None,
    }
    if not ops_discord_run.is_file():
        receipt.update({"status": "FAILED", "error": "ops-discord runner missing"})
        write_json(out, receipt)
        return receipt

    try:
        proc = subprocess.run(
            command,
            cwd=workdir,
            capture_output=True,
            text=True,
            timeout=90,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        receipt.update({"status": "FAILED", "error": str(exc)})
        write_json(out, receipt)
        return receipt

    receipt.update(
        {
            "exit_code": proc.returncode,
            "stdout_tail": proc.stdout[-4000:],
            "stderr_tail": proc.stderr[-4000:],
        }
    )
    try:
        ops_receipt = json.loads(proc.stdout)
    except json.JSONDecodeError:
        ops_receipt = {"status": "INVALID_JSON"}
    receipt["ops_discord_receipt"] = ops_receipt
    expected = "SENT" if post else "DRY_RUN"
    receipt["status"] = "PASS" if proc.returncode == 0 and ops_receipt.get("status") == expected else "FAILED"
    if isinstance(ops_receipt, dict):
        receipt["message_url"] = ops_receipt.get("message_url")
        receipt["ops_discord_status"] = ops_receipt.get("status")
        receipt["ops_discord_source"] = ops_receipt.get("source")
    write_json(out, receipt)
    return receipt
