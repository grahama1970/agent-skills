"""Task registry loading, state management, and embed builders for Discord publisher."""

from __future__ import annotations

import json
from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import Optional

from publisher_config import (
    REGISTRY_FILE,
    COMPONENT_TEXT_DISPLAY,
    FLAG_IS_COMPONENTS_V2,
    progress_bar,
)


def load_registry() -> dict:
    """Load task registry."""
    if not REGISTRY_FILE.exists():
        return {"tasks": {}}
    try:
        return json.loads(REGISTRY_FILE.read_text())
    except Exception:
        return {"tasks": {}}


def load_task_state(state_file: str) -> dict:
    """Load individual task state file."""
    path = Path(state_file)
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except Exception:
        return {}


def get_all_task_states() -> list[dict]:
    """Get states for all registered tasks."""
    registry = load_registry()
    tasks = []

    for name, config in registry.get("tasks", {}).items():
        state_file = config.get("state_file", "")
        state = load_task_state(state_file)

        completed_raw = state.get("completed", 0)
        # Handle completed as list (items) or int (count)
        completed = len(completed_raw) if isinstance(completed_raw, list) else completed_raw
        total = config.get("total") or state.get("total", 0)
        # Handle total as list or int
        if isinstance(total, list):
            total = len(total)
        pct = (completed / total * 100) if total > 0 else 0

        errors_raw = state.get("errors", 0)
        errors = len(errors_raw) if isinstance(errors_raw, list) else (errors_raw or 0)

        tasks.append({
            "name": name,
            "completed": completed,
            "total": total,
            "pct": pct,
            "status": state.get("status", "unknown"),
            "errors": errors,
            "description": config.get("description", ""),
            "project": config.get("project", ""),
        })

    return tasks


def build_v2_dashboard() -> dict:
    """Build a minimal, mobile-first Components V2 dashboard.

    Design principles (from /review-design brutal critique):
    - ONE emoji per message (header only)
    - NO progress bars (unreadable on mobile)
    - NO percentage health scores (false precision)
    - TWO sections maximum (header + details if needed)
    - Binary/tri-state health: green clear, yellow working, red attention
    - 320px mobile width test
    - Actionable: what's wrong + how to fix

    Returns the full webhook payload with components and flags.
    """
    tasks = get_all_task_states()

    # Categorize tasks
    blocked_tasks = [t for t in tasks if t["errors"] > 0]
    active_tasks = [t for t in tasks if t["errors"] == 0 and 0 < t["pct"] < 100]
    done_tasks = [t for t in tasks if t["pct"] >= 100 and t["errors"] == 0]

    # Sort blocked by error count (most errors first)
    blocked_tasks.sort(key=lambda t: t["errors"], reverse=True)

    components = []

    if blocked_tasks:
        n_blocked = len(blocked_tasks)
        verb = "needs" if n_blocked == 1 else "need"
        header = f"## \U0001f534 HORUS \u2014 {n_blocked} task{'s' if n_blocked != 1 else ''} {verb} attention"
    elif active_tasks:
        header = f"## \U0001f7e1 HORUS \u2014 {len(active_tasks)} active"
        if done_tasks:
            header += f", {len(done_tasks)} done"
        top_names = [t["name"].split(":")[-1][:15] for t in active_tasks[:3]]
        header += f"\n{', '.join(top_names)}"
        if len(active_tasks) > 3:
            header += f" +{len(active_tasks) - 3}"
    elif done_tasks:
        header = f"## \U0001f7e2 HORUS \u2014 {len(done_tasks)} complete"
    else:
        header = "## HORUS \u2014 idle"

    components.append({
        "type": COMPONENT_TEXT_DISPLAY,
        "content": header,
    })

    if blocked_tasks:
        detail_lines = []
        for task in blocked_tasks[:4]:
            raw_name = task["name"].split(":")[-1]
            if len(raw_name) > 24:
                name = raw_name[:10] + "..." + raw_name[-10:]
            else:
                name = raw_name

            err_count = task["errors"]
            detail_lines.append(f"**{name}** \u2014 {err_count} error{'s' if err_count != 1 else ''}")

        if len(blocked_tasks) > 4:
            detail_lines.append(f"*+{len(blocked_tasks) - 4} more*")

        detail_lines.append("")
        detail_lines.append("[View details \u2192](http://localhost:8765/)")

        components.append({
            "type": COMPONENT_TEXT_DISPLAY,
            "content": "\n".join(detail_lines),
        })

    return {
        "components": components,
        "flags": FLAG_IS_COMPONENTS_V2,
    }


def build_status_embed() -> dict:
    """Build Discord embed for current status - mobile-optimized."""
    tasks = get_all_task_states()

    if not tasks:
        return {
            "title": "HORUS",
            "description": "No active tasks",
            "color": 0x808080,
            "timestamp": datetime.now(tz=None).isoformat(),
        }

    active_tasks = []
    errored_tasks = []
    done_tasks = []
    stale_tasks = []

    for task in tasks:
        if task["errors"] > 0:
            errored_tasks.append(task)
        elif task["pct"] >= 100:
            done_tasks.append(task)
        elif task["pct"] > 0:
            active_tasks.append(task)
        else:
            stale_tasks.append(task)

    active_tasks.sort(key=lambda t: t["pct"], reverse=True)

    lines = []

    if active_tasks:
        for task in active_tasks[:6]:
            bar = progress_bar(task["pct"], width=10)
            name = task["name"].split(":")[-1][:18]
            lines.append(f"`{bar}` {task['pct']:>3.0f}%  {name}")

        if len(active_tasks) > 6:
            lines.append(f"       *+{len(active_tasks) - 6} more*")

    if errored_tasks:
        lines.append("\u200b")
        lines.append("**ERRORS**")
        for task in errored_tasks[:3]:
            name = task["name"].split(":")[-1][:20]
            lines.append(f"\u2022 {name}")

    if not active_tasks and not errored_tasks:
        if done_tasks:
            lines.append("All tasks complete")
        else:
            lines.append("No active tasks")

    description = "\n".join(lines)

    if errored_tasks:
        color = 0xED4245
    elif active_tasks:
        color = 0x5865F2
    else:
        color = 0x57F287

    parts = []
    if active_tasks:
        parts.append(f"{len(active_tasks)} active")
    if done_tasks:
        parts.append(f"{len(done_tasks)} done")
    if errored_tasks:
        parts.append(f"{len(errored_tasks)} errors")
    if stale_tasks:
        parts.append(f"{len(stale_tasks)} pending")

    footer_text = " \u00b7 ".join(parts) if parts else "idle"

    return {
        "title": "HORUS",
        "description": description,
        "color": color,
        "footer": {"text": footer_text},
        "timestamp": datetime.now(tz=None).isoformat(),
    }


def generate_dashboard_image() -> Optional[bytes]:
    """Generate dashboard image using matplotlib."""
    try:
        import matplotlib.pyplot as plt
        import matplotlib.patches as mpatches
        from matplotlib.figure import Figure
    except ImportError:
        print("matplotlib not available, skipping dashboard image")
        return None

    tasks = get_all_task_states()
    if not tasks:
        return None

    plt.style.use('dark_background')
    fig, ax = plt.subplots(figsize=(8, max(3, len(tasks) * 0.6)))
    fig.patch.set_facecolor('#2C2F33')
    ax.set_facecolor('#2C2F33')

    tasks = sorted(tasks, key=lambda t: t["pct"], reverse=True)

    y_positions = range(len(tasks))
    bar_height = 0.6

    for i, task in enumerate(tasks):
        ax.barh(i, 100, height=bar_height, color='#40444B', zorder=1)

        color = '#43B581' if task["pct"] >= 100 else '#7289DA'
        if task["errors"] > 0:
            color = '#F04747'
        ax.barh(i, task["pct"], height=bar_height, color=color, zorder=2)

        ax.text(-2, i, task["name"], ha='right', va='center',
                fontsize=10, color='white', fontweight='bold')

        ax.text(102, i, f'{task["pct"]:.0f}%', ha='left', va='center',
                fontsize=10, color='white')

    ax.set_xlim(-40, 115)
    ax.set_ylim(-0.5, len(tasks) - 0.5)
    ax.set_yticks([])
    ax.set_xticks([])
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    ax.spines['bottom'].set_visible(False)
    ax.spines['left'].set_visible(False)

    fig.suptitle('HORUS Task Monitor', fontsize=14, color='white', fontweight='bold', y=0.98)

    fig.text(0.5, 0.02, datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
             ha='center', fontsize=8, color='#72767D')

    plt.tight_layout(rect=[0.15, 0.05, 0.95, 0.95])

    buf = BytesIO()
    fig.savefig(buf, format='png', dpi=150, facecolor='#2C2F33', edgecolor='none')
    buf.seek(0)
    plt.close(fig)

    return buf.read()
