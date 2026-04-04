"""Dashboard TUI - Rich terminal user interface.

Follows task-monitor/tui.py pattern: rich.live.Live with rich.layout.Layout.
NVIS MIL-STD-3009 color palette throughout.

Inputs: collect_all() dict from collectors.py (14 collectors).
Outputs: Rich Live TUI with 9 panels in 4-tier layout:
  Row 1: Daemons | Subagents | Cost Tracker
  Row 2: Cascade+LLM | Chutes Quota
  Row 3: PDF Review | Quarantine
  Row 4: Active Tasks (full width)
  Footer: Monitor status strip
Failure modes: individual panels show N/A on collector error; SIGINT exits cleanly.
"""
from __future__ import annotations

import json
import signal
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from loguru import logger
from rich.console import Console
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from collectors import collect_all

console = Console()

REFRESH_INTERVAL = 5
CONFIG_PATH = Path.home() / ".pi" / "dashboard" / "config.json"
_DEFAULT_THRESHOLDS = {
    "cost": {
        "daily_warn": 5.0,
        "daily_crit": 10.0,
        "mtd_warn": 50.0,
        "mtd_crit": 80.0,
    }
}


def _load_config() -> dict[str, Any]:
    """Load dashboard config from ~/.pi/dashboard/config.json with defaults."""
    config = dict(_DEFAULT_THRESHOLDS)
    try:
        if CONFIG_PATH.exists():
            user = json.loads(CONFIG_PATH.read_text())
            for section, vals in user.items():
                if isinstance(vals, dict):
                    config.setdefault(section, {}).update(vals)
                else:
                    config[section] = vals
    except Exception as exc:
        logger.debug("Config load failed: {}", exc)
    return config

# NVIS palette — MIL-STD-3009 (canonical: nvis_base.py)
NVIS_GREEN = "#00ff88"   # C_GREEN  — healthy, nominal, ownship
NVIS_RED = "#ff4444"     # C_RED    — hostile, failed, critical
NVIS_AMBER = "#ffaa00"   # C_AMBER  — warning, degraded
NVIS_BLUE = "#44aaff"    # C_BLUE   — friendly, info
NVIS_WHITE = "#c8c8c8"   # C_WHITE  — text labels
NVIS_DIM = "#505050"     # C_DIM    — muted, secondary
NVIS_YELLOW = "#ffe600"  # C_YELLOW — unknown


def _status_style(status: str) -> str:
    """Map status string to NVIS color style."""
    s = status.lower()
    if s in ("ok", "healthy", "running", "active"):
        return NVIS_GREEN
    if s in ("degraded", "warning", "partial"):
        return NVIS_AMBER
    if s in ("error", "down", "critical"):
        return NVIS_RED
    return NVIS_DIM


def _progress_bar(used: float, total: float, width: int = 10) -> str:
    """Render a block-character progress bar."""
    if total <= 0:
        return "\u2591" * width
    pct = min(used / total, 1.0)
    filled = int(width * pct)
    return "\u2588" * filled + "\u2591" * (width - filled)


class DashboardTUI:
    """Embry OS development dashboard TUI."""

    def __init__(self) -> None:
        self.running = False
        self._data: dict[str, Any] = {}

    def _refresh_data(self) -> None:
        """Collect fresh data from all sources."""
        logger.debug("Refreshing dashboard data")
        self._data = collect_all()

    def create_header(self) -> Panel:
        """Create header panel with title, timestamp, daemon count, skill count, git, backends."""
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        daemons = self._data.get("daemon_health", {})
        skills = self._data.get("skill_health", {})
        git = self._data.get("git_status", {})
        backends = self._data.get("backend_health", {})
        d_healthy = daemons.get("healthy", 0)
        d_total = daemons.get("total", 0)
        s_total = skills.get("total_skills", 0)

        header = Text()
        header.append(" EMBRY OS ", style=f"bold {NVIS_WHITE}")
        header.append(" \u25aa ", style=NVIS_DIM)
        header.append(now, style=NVIS_DIM)
        header.append(" \u25aa ", style=NVIS_DIM)
        d_style = NVIS_GREEN if d_healthy == d_total and d_total > 0 else NVIS_AMBER
        header.append(f"{d_healthy}/{d_total} daemons", style=d_style)
        header.append(" \u25aa ", style=NVIS_DIM)
        header.append(f"{s_total} skills", style=NVIS_BLUE)

        # Git status
        if "error" not in git:
            branch = git.get("branch", "")
            dirty = git.get("dirty_files", 0)
            header.append(" \u25aa ", style=NVIS_DIM)
            header.append(f"\u2387 {branch}", style=NVIS_BLUE)
            if dirty:
                header.append(f" +{dirty}", style=NVIS_AMBER)

        # Backend availability
        b_avail = backends.get("available", 0)
        b_total = backends.get("total", 0)
        if b_total:
            header.append(" \u25aa ", style=NVIS_DIM)
            b_style = NVIS_GREEN if b_avail == b_total else NVIS_AMBER if b_avail > 0 else NVIS_RED
            header.append(f"{b_avail}/{b_total} backends", style=b_style)

        return Panel(header, style="bold")

    def create_daemons_panel(self) -> Panel:
        """Create daemon health panel."""
        data = self._data.get("daemon_health", {})
        if "error" in data:
            return Panel(f"[{NVIS_RED}]{data['error']}[/{NVIS_RED}]", title="[bold]Daemons[/bold]", border_style=NVIS_RED)

        healthy = data.get("healthy", 0)
        total = data.get("total", 0)
        daemons = data.get("daemons", {})

        table = Table(show_header=False, box=None, padding=(0, 1))
        table.add_column("Daemon", style=NVIS_BLUE, width=12)
        table.add_column("Status", width=12)

        for name, info in sorted(daemons.items()):
            status = info.get("status", "unknown")
            style = _status_style(status)
            table.add_row(name, f"[{style}]{status.upper()}[/{style}]")

        title = f"[bold]Daemons ({healthy}/{total})[/bold]"
        border = NVIS_GREEN if healthy == total else NVIS_AMBER if healthy > 0 else NVIS_RED
        return Panel(table, title=title, border_style=border)

    def create_cascade_panel(self) -> Panel:
        """Create cascade state + LLM metrics + shadow agreement panel."""
        cascade = self._data.get("cascade_state", {})
        llm = self._data.get("llm_metrics", {})
        shadow = self._data.get("shadow_agreement", {})

        table = Table(show_header=False, box=None, padding=(0, 1))
        table.add_column("Metric", style=NVIS_BLUE, width=22)
        table.add_column("Value", width=18)

        if "error" not in cascade:
            table.add_row(
                "Models",
                f"{cascade.get('validators', 0)} val  {cascade.get('classifiers', 0)} cls  {cascade.get('regressors', 0)} reg",
            )

        if "error" not in shadow:
            rate = shadow.get("agreement_rate", 0)
            style = NVIS_GREEN if rate >= 0.7 else NVIS_AMBER if rate >= 0.5 else NVIS_RED
            table.add_row("Shadow agreement", f"[{style}]{rate:.0%}[/{style}]")

        if "error" not in llm:
            table.add_row("LLM calls (24h)", str(llm.get("calls_today", 0)))
            avg = llm.get("avg_latency_ms", 0)
            table.add_row("Avg latency", f"{avg / 1000:.1f}s" if avg else "N/A")
            table.add_row("Cache hit", f"{llm.get('cache_hit_rate', 0):.0%}")

            tiers = llm.get("tier_distribution", {})
            if tiers:
                total_calls = sum(tiers.values())
                tier_parts = []
                for t, count in sorted(tiers.items()):
                    pct = count / total_calls * 100 if total_calls else 0
                    tier_parts.append(f"{t}={pct:.0f}%")
                table.add_row("Tier", " ".join(tier_parts))

        return Panel(table, title="[bold]Cascade[/bold]", border_style=NVIS_BLUE)

    def create_chutes_panel(self) -> Panel:
        """Create Chutes quota panel."""
        data = self._data.get("chutes_quota", {})
        if "error" in data and "used" not in data:
            return Panel(f"[{NVIS_RED}]{data['error']}[/{NVIS_RED}]", title="[bold]Chutes Quota[/bold]", border_style=NVIS_RED)

        used = data.get("used", 0)
        quota = data.get("quota", 5000)
        remaining = data.get("remaining", quota - used)
        balance = data.get("balance", "?")
        slots = data.get("slots_in_use", "?")

        bar = _progress_bar(used, quota)
        pct_color = NVIS_GREEN if remaining > quota * 0.2 else NVIS_AMBER if remaining > 0 else NVIS_RED

        lines = Text()
        lines.append(f" {bar} ", style=pct_color)
        lines.append(f"{used:.0f}/{quota:.0f}\n")

        if isinstance(balance, (int, float)):
            bal_color = NVIS_GREEN if balance > 0.50 else NVIS_RED
            lines.append(f" Balance: [{bal_color}]${balance:.2f}[/{bal_color}]\n")
        else:
            lines.append(f" Balance: {balance}\n")

        reset = data.get("reset_in_seconds")
        if reset and isinstance(reset, (int, float)):
            h, m = int(reset) // 3600, (int(reset) % 3600) // 60
            lines.append(f" Reset: {h}h {m}m\n")

        lines.append(f" Concurrency: {slots}/5 slots")

        return Panel(lines, title="[bold]Chutes Quota[/bold]", border_style=NVIS_AMBER)

    def create_tasks_panel(self) -> Panel:
        """Create active tasks panel with elapsed time and current item."""
        data = self._data.get("active_tasks", {})
        active = data.get("active", 0)
        tasks = data.get("tasks", [])

        if not tasks:
            content = f"[{NVIS_DIM}](idle)[/{NVIS_DIM}]"
        else:
            table = Table(show_header=False, box=None, padding=(0, 1), expand=True)
            table.add_column("Task", style=NVIS_BLUE, width=18)
            table.add_column("Progress", width=30)
            table.add_column("Time", style=NVIS_DIM, width=8)
            table.add_column("Item", style=NVIS_DIM, width=20)

            for t in tasks[:8]:
                bar = _progress_bar(t.get("completed", 0), t.get("total", 1), width=15)
                elapsed = t.get("elapsed_seconds", 0)
                if elapsed >= 3600:
                    time_str = f"{elapsed / 3600:.1f}h"
                elif elapsed >= 60:
                    time_str = f"{elapsed / 60:.0f}m{elapsed % 60:.0f}s"
                elif elapsed > 0:
                    time_str = f"{elapsed:.1f}s"
                else:
                    time_str = ""
                item = (t.get("current_item") or "")[:20]
                table.add_row(
                    t["name"][:18],
                    f"[{NVIS_BLUE}]{bar}[/{NVIS_BLUE}] {t.get('completed', 0)}/{t.get('total', '?')} ({t.get('pct', 0):.0f}%)",
                    time_str,
                    item,
                )
            content = table

        return Panel(content, title=f"[bold]Active Tasks ({active})[/bold]", border_style=NVIS_AMBER)

    def create_skill_health_panel(self) -> Panel:
        """Create skill health panel."""
        data = self._data.get("skill_health", {})
        if "error" in data:
            return Panel(f"[{NVIS_DIM}]{data['error']}[/{NVIS_DIM}]", title="[bold]Skill Health[/bold]", border_style=NVIS_DIM)

        overall = data.get("overall_status", "unknown")
        total = data.get("total_skills", 0)
        counts = data.get("status_counts", {})

        parts = []
        parts.append(f"Overall: [{_status_style(overall)}]{overall.upper()}[/{_status_style(overall)}]")
        parts.append(f"  {total} skills")
        for status_name in ("warning", "critical"):
            count = counts.get(status_name, 0)
            if count > 0:
                parts.append(f"  [{_status_style(status_name)}]{count} {status_name}[/{_status_style(status_name)}]")
            else:
                parts.append(f"  0 {status_name}")

        return Panel("  ".join(parts), title="[bold]Skill Health[/bold]", border_style=NVIS_GREEN)

    def create_subagents_panel(self) -> Panel:
        """Create subagent backend status panel."""
        data = self._data.get("subagent_state", {})
        if "error" in data:
            return Panel(f"[{NVIS_RED}]{data['error']}[/{NVIS_RED}]", title="[bold]Subagents[/bold]", border_style=NVIS_RED)

        backends = data.get("backends", {})
        running = data.get("running", 0)
        completed = data.get("completed", 0)
        errored = data.get("errored", 0)

        table = Table(show_header=False, box=None, padding=(0, 1))
        table.add_column("Backend", style=NVIS_BLUE, width=10)
        table.add_column("Status", width=14)

        for name in ("claude", "codex", "gemini"):
            info = backends.get(name, {})
            b_run = info.get("running", 0)
            b_done = info.get("completed", 0)
            b_err = info.get("errored", 0)
            if b_run > 0:
                style = NVIS_GREEN
                label = f"{b_run} run"
            elif b_err > 0:
                style = NVIS_RED
                label = f"{b_err} err"
            elif b_done > 0:
                style = NVIS_DIM
                label = f"{b_done} done"
            else:
                style = NVIS_DIM
                label = "idle"
            table.add_row(name.capitalize(), f"[{style}]{label}[/{style}]")

        summary = f"[{NVIS_DIM}]{completed} done[/{NVIS_DIM}]"
        if errored:
            summary += f"  [{NVIS_RED}]{errored} err[/{NVIS_RED}]"

        border = NVIS_RED if errored else NVIS_GREEN if running else NVIS_DIM
        return Panel(table, title=f"[bold]Subagents ({running} run)[/bold]", subtitle=summary, border_style=border)

    def create_cost_panel(self) -> Panel:
        """Create cost tracker panel from ops-costs data with config-driven thresholds."""
        data = self._data.get("cost_data", {})
        if "error" in data:
            return Panel(f"[{NVIS_DIM}]{data['error']}[/{NVIS_DIM}]", title="[bold]Cost Tracker[/bold]", border_style=NVIS_DIM)

        config = _load_config().get("cost", {})
        daily_warn = config.get("daily_warn", 5.0)
        daily_crit = config.get("daily_crit", 10.0)
        mtd_warn = config.get("mtd_warn", 50.0)
        mtd_crit = config.get("mtd_crit", 80.0)

        table = Table(show_header=False, box=None, padding=(0, 1))
        table.add_column("Item", style=NVIS_BLUE, width=10)
        table.add_column("Value", width=16)

        today = data.get("today", data.get("daily_total", 0))
        mtd = data.get("mtd", data.get("monthly_total", 0))
        providers = data.get("providers", data.get("by_provider", {}))

        today_style = NVIS_GREEN if today < daily_warn else NVIS_AMBER if today < daily_crit else NVIS_RED
        table.add_row("Today", f"[{today_style}]${today:.2f}[/{today_style}]")

        for name, amount in sorted(providers.items()):
            if isinstance(amount, (int, float)):
                table.add_row(name.capitalize(), f"${amount:.2f}")

        mtd_style = NVIS_GREEN if mtd < mtd_warn else NVIS_AMBER if mtd < mtd_crit else NVIS_RED
        table.add_row("MTD", f"[{mtd_style}]${mtd:.2f}[/{mtd_style}]")

        return Panel(table, title="[bold]Cost Tracker[/bold]", border_style=NVIS_BLUE)

    def create_monitors_panel(self) -> Panel:
        """Create compact monitor status strip."""
        data = self._data.get("monitor_reports", {})
        monitors = data.get("monitors", {})

        if not monitors:
            return Panel(f"[{NVIS_DIM}]No monitor data[/{NVIS_DIM}]", title="[bold]Monitors[/bold]", border_style=NVIS_DIM)

        parts = Text()
        for name, info in sorted(monitors.items()):
            short = name.replace("monitor-", "")
            if isinstance(info, dict) and "error" not in info:
                health = info.get("health", "unknown")
                if health in ("healthy", "ok"):
                    parts.append(f"\u25cf{short}", style=NVIS_GREEN)
                elif health == "warning":
                    parts.append(f"\u25b2{short}", style=NVIS_AMBER)
                elif health == "critical":
                    parts.append(f"\u2715{short}", style=NVIS_RED)
                else:
                    parts.append(f"\u25cf{short}", style=NVIS_DIM)
            else:
                parts.append(f"\u25cf{short}", style=NVIS_DIM)
            parts.append("  ")

        overall = data.get("overall_health", "unknown")
        border = _status_style(overall) if overall != "no_data" else NVIS_DIM
        reporting = data.get("monitors_reporting", 0)
        total = data.get("monitors_total", 0)
        return Panel(parts, title=f"[bold]Monitors ({reporting}/{total})[/bold]", border_style=border)

    def create_review_pdf_panel(self) -> Panel:
        """Create PDF Review panel showing verdict distribution and today's activity."""
        data = self._data.get("review_pdf", {})
        if "error" in data:
            return Panel(f"[{NVIS_RED}]{data['error']}[/{NVIS_RED}]", title="[bold]PDF Review[/bold]", border_style=NVIS_RED)

        approvals = data.get("approvals_today", 0)
        flags = data.get("flags_today", 0)
        corrections = data.get("corrections_today", 0)
        latest = data.get("latest_run", "")

        total = approvals + flags
        pass_pct = (approvals / total * 100) if total > 0 else 100

        table = Table(show_header=False, box=None, padding=(0, 1))
        table.add_column("Metric", style=NVIS_BLUE, width=16)
        table.add_column("Value", width=14)

        # Verdict distribution
        table.add_row("PASS", f"[{NVIS_GREEN}]{approvals}[/{NVIS_GREEN}]")
        table.add_row("WARN/FAIL", f"[{NVIS_AMBER}]{flags}[/{NVIS_AMBER}]")
        table.add_row("Corrections", f"[{NVIS_YELLOW}]{corrections}[/{NVIS_YELLOW}]")

        if latest:
            short_ts = latest[11:19] if len(latest) > 19 else latest
            table.add_row("Last run", f"[{NVIS_DIM}]{short_ts}[/{NVIS_DIM}]")

        if pass_pct > 80:
            border = NVIS_GREEN
        elif pass_pct > 50:
            border = NVIS_AMBER
        else:
            border = NVIS_RED

        return Panel(table, title="[bold]PDF Review[/bold]", border_style=border)

    def create_quarantine_panel(self) -> Panel:
        """Create Quarantine panel showing pending items and by-reason breakdown."""
        data = self._data.get("quarantine", {})
        if "error" in data:
            return Panel(f"[{NVIS_RED}]{data['error']}[/{NVIS_RED}]", title="[bold]Quarantine[/bold]", border_style=NVIS_RED)

        pending = data.get("pending", 0)
        resolved_today = data.get("resolved_today", 0)
        by_reason = data.get("by_reason", {})
        total_processed = data.get("total_processed", 0)

        if pending > 20:
            pending_style = NVIS_RED
        elif pending > 5:
            pending_style = NVIS_AMBER
        else:
            pending_style = NVIS_GREEN

        table = Table(show_header=False, box=None, padding=(0, 1))
        table.add_column("Metric", style=NVIS_BLUE, width=18)
        table.add_column("Value", width=10)

        table.add_row("Pending", f"[bold {pending_style}]{pending}[/bold {pending_style}]")
        table.add_row("Resolved today", f"[{NVIS_GREEN}]{resolved_today}[/{NVIS_GREEN}]")
        table.add_row("Total processed", str(total_processed))

        # By-reason breakdown
        for reason, count in sorted(by_reason.items()):
            if count > 0:
                label = reason.replace("_", " ").title()
                table.add_row(f"  {label}", str(count))

        border = NVIS_RED if pending > 20 else NVIS_AMBER if pending > 5 else NVIS_GREEN
        return Panel(table, title="[bold]Quarantine[/bold]", border_style=border)

    def create_display(self) -> Layout:
        """Create the full dashboard layout — 4-tier with 10 panels.

        Layout (NVIS MIL-STD-3009):
          header (3h)
          row1: daemons | subagents | cost_tracker (8h)
          row2: cascade+LLM | chutes_quota (8h)
          row3: pdf_review | quarantine (8h)
          tasks (8h)
          monitors strip (3h)
        """
        layout = Layout()

        layout.split_column(
            Layout(self.create_header(), name="header", size=3),
            Layout(name="row1", size=8),
            Layout(name="row2", size=8),
            Layout(name="row3", size=8),
            Layout(self.create_tasks_panel(), name="tasks", size=8),
            Layout(self.create_monitors_panel(), name="monitors", size=3),
        )

        layout["row1"].split_row(
            Layout(self.create_daemons_panel(), name="daemons"),
            Layout(self.create_subagents_panel(), name="subagents"),
            Layout(self.create_cost_panel(), name="cost"),
        )

        layout["row2"].split_row(
            Layout(self.create_cascade_panel(), name="cascade", ratio=2),
            Layout(self.create_chutes_panel(), name="chutes"),
        )

        layout["row3"].split_row(
            Layout(self.create_review_pdf_panel(), name="pdf_review"),
            Layout(self.create_quarantine_panel(), name="quarantine"),
        )

        return layout

    def run(self, refresh_interval: int = REFRESH_INTERVAL) -> None:
        """Run the live TUI."""
        self.running = True

        def signal_handler(sig, frame):
            self.running = False

        signal.signal(signal.SIGINT, signal_handler)

        # Initial data load
        self._refresh_data()

        with Live(self.create_display(), console=console, refresh_per_second=1, screen=True) as live:
            last_refresh = time.time()
            while self.running:
                now = time.time()
                if now - last_refresh >= refresh_interval:
                    self._refresh_data()
                    last_refresh = now
                live.update(self.create_display())
                time.sleep(1)

        console.print(f"\n[{NVIS_GREEN}]Dashboard stopped.[/{NVIS_GREEN}]")
