#!/usr/bin/env python3
"""Discord webhook publisher for task-monitor + workstation health.

Provides:
- Real-time task updates (completion, errors)
- Periodic task dashboards (Components V2, mobile-friendly)
- Workstation health monitoring (memory, limits, GPU)
- Rate-limited webhook posting

Usage:
    # Post task status (V2 dashboard)
    python discord_publisher.py post-v2

    # Post workstation health
    python discord_publisher.py post-health

    # Start daemon (tasks every 5min, health every 15min)
    python discord_publisher.py daemon --interval 300 --health-interval 900

    # Legacy commands
    python discord_publisher.py post-status    # Old embed format
    python discord_publisher.py post-dashboard # With chart image
"""
from __future__ import annotations

import json
import time
from datetime import datetime
from typing import Optional

import httpx
import typer

# Re-export all public names from submodules for backward compatibility
from publisher_config import (
    DISCORD_WEBHOOK_URL,
    EVENTS_DIR,
    REGISTRY_FILE,
    DASHBOARD_CACHE,
    _rate_limit,
    progress_bar,
    progress_bar_modern,
    COMPONENT_ACTION_ROW,
    COMPONENT_SECTION,
    COMPONENT_TEXT_DISPLAY,
    COMPONENT_THUMBNAIL,
    COMPONENT_SEPARATOR,
    COMPONENT_CONTAINER,
    FLAG_IS_COMPONENTS_V2,
)
from publisher_tasks import (
    load_registry,
    load_task_state,
    get_all_task_states,
    build_v2_dashboard,
    build_status_embed,
    generate_dashboard_image,
)
from publisher_health import (
    OPS_WORKSTATION_PATH,
    get_workstation_health,
    build_health_dashboard,
)
from publisher_events import (
    STATUS_COLORS,
    STATUS_ICONS,
    process_skill_events as _process_skill_events_impl,
)

app = typer.Typer(help="Discord publisher for task-monitor")


def post_webhook(embed: dict = None, image_bytes: Optional[bytes] = None, v2_payload: dict = None) -> bool:
    """Post to Discord webhook.

    Args:
        embed: Legacy embed dict (for backwards compatibility)
        image_bytes: Optional image to attach
        v2_payload: Components V2 payload (components + flags)
    """
    if not DISCORD_WEBHOOK_URL:
        print("ERROR: DISCORD_WEB_HOOK_URL not set")
        return False

    _rate_limit()

    try:
        # Components V2 mode
        if v2_payload:
            url = DISCORD_WEBHOOK_URL
            if "?" in url:
                url += "&with_components=true"
            else:
                url += "?with_components=true"

            with httpx.Client(timeout=30) as client:
                r = client.post(
                    url,
                    json=v2_payload,
                    headers={"Content-Type": "application/json"},
                )

            if r.status_code in (200, 204):
                print("Posted Components V2 dashboard to Discord")
                return True
            else:
                print(f"Discord V2 error: {r.status_code} {r.text[:500]}")
                print("Falling back to legacy embed...")
                return post_webhook(embed=build_status_embed())

        # Legacy embed mode
        if image_bytes:
            files = {
                "file": ("dashboard.png", image_bytes, "image/png"),
            }
            payload = {
                "payload_json": json.dumps({
                    "embeds": [embed],
                })
            }
            with httpx.Client(timeout=30) as client:
                r = client.post(DISCORD_WEBHOOK_URL, data=payload, files=files)
        else:
            with httpx.Client(timeout=30) as client:
                r = client.post(
                    DISCORD_WEBHOOK_URL,
                    json={"embeds": [embed]},
                    headers={"Content-Type": "application/json"},
                )

        if r.status_code in (200, 204):
            print("Posted to Discord successfully")
            return True
        else:
            print(f"Discord webhook error: {r.status_code} {r.text}")
            return False

    except Exception as e:
        print(f"Discord post failed: {e}")
        return False


def process_skill_events() -> int:
    """Process pending skill events from the events directory."""
    return _process_skill_events_impl(post_webhook)


@app.command()
def post_status():
    """Post current task status to Discord (legacy embed)."""
    embed = build_status_embed()
    post_webhook(embed=embed)


@app.command()
def post_v2():
    """Post professional Components V2 dashboard to Discord."""
    payload = build_v2_dashboard()
    post_webhook(v2_payload=payload)


@app.command()
def post_dashboard(with_chart: bool = typer.Option(False, help="Include chart image")):
    """Post visual dashboard to Discord."""
    embed = build_status_embed()

    image = None
    if with_chart:
        image = generate_dashboard_image()
        if image:
            embed["image"] = {"url": "attachment://dashboard.png"}

    post_webhook(embed, image)


@app.command()
def daemon(
    interval: int = typer.Option(300, help="Seconds between dashboard posts"),
    text_on_change: bool = typer.Option(True, help="Post text update on task changes"),
    health_interval: int = typer.Option(900, help="Seconds between health checks (0 to disable)"),
):
    """Run daemon that posts updates to Discord."""
    print(f"Starting Discord publisher daemon (interval: {interval}s, health: {health_interval}s)")

    last_states = {}
    last_dashboard_time = 0
    last_health_time = 0
    last_health_status = "ok"

    while True:
        try:
            current_states = {t["name"]: t for t in get_all_task_states()}

            # Check for changes
            if text_on_change:
                for name, state in current_states.items():
                    prev = last_states.get(name, {})

                    # Detect completion
                    if state["pct"] >= 100 and prev.get("pct", 0) < 100:
                        embed = {
                            "title": f"Task completed: {name}",
                            "description": f"{state['completed']}/{state['total']} items",
                            "color": 0x2ECC71,
                            "timestamp": datetime.now(tz=None).isoformat(),
                        }
                        post_webhook(embed)

                    # Detect new errors
                    if state["errors"] > prev.get("errors", 0):
                        embed = {
                            "title": f"Task errors: {name}",
                            "description": f"{state['errors']} errors detected",
                            "color": 0xFF6B6B,
                            "timestamp": datetime.now(tz=None).isoformat(),
                        }
                        post_webhook(embed)

            last_states = current_states

            # Process any pending skill events
            events_processed = process_skill_events()
            if events_processed > 0:
                print(f"Processed {events_processed} skill events")

            # Periodic task dashboard
            if time.time() - last_dashboard_time >= interval:
                post_v2()
                last_dashboard_time = time.time()

            # Periodic health check
            if health_interval > 0 and time.time() - last_health_time >= health_interval:
                try:
                    health = get_workstation_health()
                    limits = health.get("limits", {})
                    critical = limits.get("critical", 0) if limits else 0
                    warnings = limits.get("warnings", 0) if limits else 0
                    mem_pct = health.get("memory", {}).get("used_pct", 0) if health.get("memory") else 0

                    if critical > 0 or mem_pct >= 90:
                        current_status = "critical"
                    elif warnings > 0 or mem_pct >= 75:
                        current_status = "warning"
                    else:
                        current_status = "ok"

                    if current_status != last_health_status:
                        if current_status == "critical":
                            embed = {
                                "title": "Workstation health critical",
                                "description": f"Memory: {mem_pct}%, Limits: {critical} critical",
                                "color": 0xFF0000,
                                "timestamp": datetime.now(tz=None).isoformat(),
                            }
                            post_webhook(embed)
                        elif current_status == "warning" and last_health_status == "ok":
                            embed = {
                                "title": "Workstation health warning",
                                "description": f"Memory: {mem_pct}%, Limits: {warnings} warnings",
                                "color": 0xFFAA00,
                                "timestamp": datetime.now(tz=None).isoformat(),
                            }
                            post_webhook(embed)
                        elif current_status == "ok" and last_health_status != "ok":
                            embed = {
                                "title": "Workstation health recovered",
                                "description": "All systems normal",
                                "color": 0x00FF00,
                                "timestamp": datetime.now(tz=None).isoformat(),
                            }
                            post_webhook(embed)

                        last_health_status = current_status

                except Exception as e:
                    print(f"Health check error: {e}")

                last_health_time = time.time()

            time.sleep(30)

        except KeyboardInterrupt:
            print("Daemon stopped")
            break
        except Exception as e:
            print(f"Daemon error: {e}")
            time.sleep(60)


@app.command()
def test():
    """Test Discord webhook connection."""
    embed = {
        "title": "Test Message",
        "description": "Task monitor Discord integration is working!",
        "color": 0x7289DA,
        "timestamp": datetime.now(tz=None).isoformat(),
    }
    if post_webhook(embed):
        print("Webhook test successful")
    else:
        print("Webhook test failed")


@app.command()
def cleanup(
    dry_run: bool = typer.Option(True, help="Show what would be removed without removing"),
    keep_active: bool = typer.Option(True, help="Keep tasks with 0 < progress < 100"),
    keep_recent_done: int = typer.Option(5, help="Keep N most recent completed tasks"),
):
    """Clean up stale tasks from the registry."""
    if not REGISTRY_FILE.exists():
        print("No registry file found")
        return

    registry = json.loads(REGISTRY_FILE.read_text())
    tasks = registry.get("tasks", {})

    print(f"Current tasks: {len(tasks)}")

    to_remove = []
    active = []
    done = []
    stale = []

    for name, config in tasks.items():
        state = load_task_state(config.get("state_file", ""))
        completed_raw = state.get("completed", 0)
        completed = len(completed_raw) if isinstance(completed_raw, list) else completed_raw
        total = config.get("total") or state.get("total", 0)
        if isinstance(total, list):
            total = len(total)
        pct = (completed / total * 100) if total > 0 else 0

        if pct >= 100:
            done.append((name, config))
        elif pct > 0:
            active.append((name, pct))
        else:
            stale.append(name)

    print(f"  Active (0<pct<100): {len(active)}")
    print(f"  Completed (100%): {len(done)}")
    print(f"  Stale (0%): {len(stale)}")

    to_remove.extend(stale)

    if len(done) > keep_recent_done:
        done.sort(key=lambda x: x[0], reverse=True)
        for name, _ in done[keep_recent_done:]:
            to_remove.append(name)

    print(f"\nWould remove: {len(to_remove)} tasks")

    if to_remove[:20]:
        print("Examples:")
        for name in to_remove[:20]:
            print(f"  - {name}")
        if len(to_remove) > 20:
            print(f"  ... and {len(to_remove) - 20} more")

    if dry_run:
        print("\nDry run - no changes made. Run with --no-dry-run to apply.")
    else:
        for name in to_remove:
            del tasks[name]
        registry["tasks"] = tasks
        REGISTRY_FILE.write_text(json.dumps(registry, indent=2))
        print(f"\nRemoved {len(to_remove)} tasks. {len(tasks)} remaining.")


@app.command()
def post_health():
    """Post workstation health to Discord."""
    if not OPS_WORKSTATION_PATH.exists():
        print(f"ERROR: ops-workstation not found at {OPS_WORKSTATION_PATH}")
        return

    payload = build_health_dashboard()
    post_webhook(v2_payload=payload)


@app.command()
def health_check():
    """Check workstation health (local output, no Discord)."""
    health = get_workstation_health()
    print(json.dumps(health, indent=2))


@app.command()
def process_events():
    """Process pending skill events and post to Discord."""
    count = process_skill_events()
    print(f"Processed {count} events")


if __name__ == "__main__":
    app()
