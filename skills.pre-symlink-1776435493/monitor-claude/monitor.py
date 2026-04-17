#!/usr/bin/env python3
"""monitor-claude: Continuous system-wide process health watchdog.

Detects memory-leaked sessions, zombie headless agents, runaway CPU,
stale Chromium/Chrome processes, and long-running Python scripts with no TTY.
Fires Discord alerts and optionally auto-kills processes exceeding hard limits.
"""
from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import typer
from loguru import logger

# Import discord notify from common
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "common"))
try:
    from discord_notify import notify_health, notify_error
except ImportError:
    def notify_health(*a, **kw):
        pass
    def notify_error(*a, **kw):
        pass

app = typer.Typer(help="System-wide process health watchdog")

# ---------------------------------------------------------------------------
# Configuration (env-overridable)
# ---------------------------------------------------------------------------
MAX_RSS_GB = float(os.environ.get("CLAUDE_MAX_RSS_GB", "5"))
HARD_RSS_GB = float(os.environ.get("CLAUDE_HARD_RSS_GB", "15"))
MAX_HEADLESS_HOURS = float(os.environ.get("CLAUDE_MAX_HEADLESS_HOURS", "4"))
MAX_PROCESSES = int(os.environ.get("CLAUDE_MAX_PROCESSES", "15"))
SCAN_INTERVAL = int(os.environ.get("CLAUDE_SCAN_INTERVAL", "300"))

# Per-type zombie thresholds (hours)
ZOMBIE_THRESHOLDS: dict[str, float] = {
    "claude": float(os.environ.get("CLAUDE_MAX_HEADLESS_HOURS", "4")),
    "chromium": float(os.environ.get("CHROMIUM_MAX_HEADLESS_HOURS", "12")),
    "python": float(os.environ.get("PYTHON_MAX_HEADLESS_HOURS", "8")),
}

ALL_PROCESS_TYPES = {"claude", "chromium", "python"}

LOG_DIR = Path.home() / ".pi" / "memory" / "monitor-claude"
LOG_FILE = LOG_DIR / "alerts.jsonl"
STATE_DIR = Path.home() / ".pi" / "monitor-claude"
REPORT_FILE = STATE_DIR / "report.json"


@dataclass
class MonitoredProcess:
    """Parsed info about a single monitored process."""
    pid: int
    rss_gb: float
    cpu_pct: float
    start_time: str
    tty: str
    elapsed_hours: float
    cmd: str
    process_type: str = "claude"

    @property
    def is_headless(self) -> bool:
        return self.tty == "?"

    @property
    def is_memory_leak(self) -> bool:
        return self.rss_gb >= MAX_RSS_GB

    @property
    def is_hard_limit(self) -> bool:
        return self.rss_gb >= HARD_RSS_GB

    @property
    def is_zombie(self) -> bool:
        threshold = ZOMBIE_THRESHOLDS.get(self.process_type, MAX_HEADLESS_HOURS)
        return self.is_headless and self.elapsed_hours >= threshold

    @property
    def is_cpu_runaway(self) -> bool:
        return self.cpu_pct >= 80.0 and self.elapsed_hours >= 1.0


@dataclass
class ScanResult:
    """Results from a single scan pass."""
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    total_processes: int = 0
    total_rss_gb: float = 0.0
    interactive_count: int = 0
    headless_count: int = 0
    memory_leaks: list[dict] = field(default_factory=list)
    zombies: list[dict] = field(default_factory=list)
    cpu_runaways: list[dict] = field(default_factory=list)
    hard_kills: list[dict] = field(default_factory=list)
    process_sprawl: bool = False


def _classify_process_line(line: str) -> Optional[str]:
    """Determine the process type from a ps aux line, or None if not monitored.

    Returns one of: "claude", "chromium", "python", or None.
    """
    lower = line.lower()

    # Skip grep/awk/monitor artifacts
    if "grep" in lower or "awk" in lower or "monitor.py" in lower:
        return None

    # Claude Code headless agents
    if "claude" in lower and "--dangerously-skip-permissions" in lower:
        return "claude"

    # Chromium / Chrome zombies
    if "chromium" in lower or "chrome" in lower:
        return "chromium"

    # Long-running Python with no TTY (checked later via tty field)
    if "python" in lower:
        return "python"

    return None


def get_monitored_processes(
    types: Optional[set[str]] = None,
) -> list[MonitoredProcess]:
    """Parse ps output to find monitored processes.

    Args:
        types: Set of process types to detect. Defaults to all types.
    """
    if types is None:
        types = ALL_PROCESS_TYPES

    try:
        result = subprocess.run(
            ["ps", "aux"],
            capture_output=True, text=True, timeout=10,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        logger.error("Failed to run ps")
        return []

    processes = []
    now = datetime.now()

    for line in result.stdout.splitlines()[1:]:  # skip header
        proc_type = _classify_process_line(line)
        if proc_type is None or proc_type not in types:
            continue

        parts = line.split(None, 10)
        if len(parts) < 11:
            continue

        try:
            pid = int(parts[1])
            cpu_pct = float(parts[2])
            rss_kb = int(parts[5])
            rss_gb = rss_kb / 1024 / 1024
            tty = parts[6]
            start_time = parts[8]
            cmd = parts[10]

            # Estimate elapsed hours from START field
            elapsed_hours = _estimate_elapsed_hours(start_time, now)

            # For python type, only include headless (no TTY) processes
            if proc_type == "python" and tty != "?":
                continue

            processes.append(MonitoredProcess(
                pid=pid,
                rss_gb=round(rss_gb, 1),
                cpu_pct=cpu_pct,
                start_time=start_time,
                tty=tty,
                elapsed_hours=round(elapsed_hours, 1),
                cmd=cmd[:120],
                process_type=proc_type,
            ))
        except (ValueError, IndexError):
            continue

    return processes


def _estimate_elapsed_hours(start_str: str, now: datetime) -> float:
    """Estimate hours since process started from ps START field.

    ps shows time (HH:MM) for today's processes and date (MonDD or FebDD) for older ones.
    """
    # If it contains a colon, it's a time today (e.g. "09:45")
    if ":" in start_str and not start_str.startswith("Feb") and len(start_str) <= 5:
        try:
            h, m = start_str.split(":")
            start = now.replace(hour=int(h), minute=int(m), second=0)
            if start > now:
                start -= timedelta(days=1)
            return (now - start).total_seconds() / 3600
        except ValueError:
            pass

    # Otherwise it's a date like "Feb21", "Jan05", etc.
    months = {
        "Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4, "May": 5, "Jun": 6,
        "Jul": 7, "Aug": 8, "Sep": 9, "Oct": 10, "Nov": 11, "Dec": 12,
    }
    for month_name, month_num in months.items():
        if start_str.startswith(month_name):
            try:
                day = int(start_str[3:])
                start = now.replace(month=month_num, day=day, hour=0, minute=0, second=0)
                if start > now:
                    start = start.replace(year=now.year - 1)
                return (now - start).total_seconds() / 3600
            except (ValueError, IndexError):
                pass

    # Fallback: unknown age
    return 0.0


def check_embry_agent() -> dict:
    """Check if the Embry Agent D-Bus daemon is running and responsive."""
    result = {"systemd_active": False, "dbus_ping": False, "error": None}
    try:
        svc = subprocess.run(
            ["systemctl", "--user", "is-active", "embry-agent.service"],
            capture_output=True, text=True, timeout=5,
        )
        result["systemd_active"] = svc.stdout.strip() == "active"
    except Exception as e:
        result["error"] = f"systemctl check failed: {e}"

    try:
        ping = subprocess.run(
            ["busctl", "--user", "call", "org.embry.Agent",
             "/org/embry/Agent", "org.embry.Agent", "Ping"],
            capture_output=True, text=True, timeout=5,
        )
        result["dbus_ping"] = "pong" in ping.stdout
    except Exception as e:
        if not result["error"]:
            result["error"] = f"D-Bus ping failed: {e}"

    return result


def _parse_types(types_str: str) -> set[str]:
    """Parse comma-separated types string into a validated set."""
    requested = {t.strip().lower() for t in types_str.split(",")}
    valid = requested & ALL_PROCESS_TYPES
    if not valid:
        logger.warning(
            "No valid types in '{}'. Valid: {}. Using all.",
            types_str, ", ".join(sorted(ALL_PROCESS_TYPES)),
        )
        return ALL_PROCESS_TYPES
    invalid = requested - ALL_PROCESS_TYPES
    if invalid:
        logger.warning("Ignoring unknown process types: {}", ", ".join(sorted(invalid)))
    return valid


def scan_processes(
    kill: bool = False,
    types: Optional[set[str]] = None,
) -> ScanResult:
    """Scan monitored processes and classify findings."""
    processes = get_monitored_processes(types=types)
    result = ScanResult()
    result.total_processes = len(processes)
    result.total_rss_gb = round(sum(p.rss_gb for p in processes), 1)
    result.interactive_count = sum(1 for p in processes if not p.is_headless)
    result.headless_count = sum(1 for p in processes if p.is_headless)
    result.process_sprawl = len(processes) > MAX_PROCESSES

    for proc in processes:
        proc_info = asdict(proc)

        # Hard kill threshold -- auto-kill if --kill
        if proc.is_hard_limit:
            result.hard_kills.append(proc_info)
            if kill:
                _kill_process(proc.pid, proc.rss_gb, "hard RSS limit")

        # Memory leak (soft)
        elif proc.is_memory_leak:
            result.memory_leaks.append(proc_info)

        # Zombie headless agent (per-type threshold)
        if proc.is_zombie:
            result.zombies.append(proc_info)
            if kill:
                _kill_process(proc.pid, proc.rss_gb, f"zombie {proc.process_type}")

        # CPU runaway
        if proc.is_cpu_runaway and not proc.is_zombie:
            result.cpu_runaways.append(proc_info)

    return result


def _kill_process(pid: int, rss_gb: float, reason: str) -> bool:
    """Kill a process, trying SIGTERM first, then SIGKILL."""
    logger.warning("Killing PID {} ({:.1f} GB) -- reason: {}", pid, rss_gb, reason)
    try:
        os.kill(pid, signal.SIGTERM)
        time.sleep(3)
        # Check if still alive
        try:
            os.kill(pid, 0)  # signal 0 = check existence
            logger.warning("PID {} ignored SIGTERM, sending SIGKILL", pid)
            os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass  # Already dead
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        logger.error("Permission denied killing PID {}", pid)
        return False


def _log_alert(result: ScanResult) -> None:
    """Append scan result to alert log."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    with open(LOG_FILE, "a") as f:
        f.write(json.dumps(asdict(result)) + "\n")


def _format_findings(result: ScanResult) -> str:
    """Format scan findings as human-readable text."""
    lines = []
    lines.append(f"Monitored processes: {result.total_processes} "
                 f"(interactive={result.interactive_count}, headless={result.headless_count})")
    lines.append(f"Total RSS: {result.total_rss_gb} GB")

    if result.process_sprawl:
        lines.append(f"WARNING: Process sprawl -- {result.total_processes} > {MAX_PROCESSES} limit")

    if result.hard_kills:
        lines.append(f"\nHARD LIMIT ({HARD_RSS_GB} GB+) -- {len(result.hard_kills)} processes:")
        for p in result.hard_kills:
            lines.append(f"  PID {p['pid']} [{p['process_type']}]: {p['rss_gb']} GB, "
                        f"{p['cpu_pct']}% CPU, started {p['start_time']}, TTY={p['tty']}")

    if result.memory_leaks:
        lines.append(f"\nMEMORY LEAKS ({MAX_RSS_GB}-{HARD_RSS_GB} GB) -- {len(result.memory_leaks)} processes:")
        for p in result.memory_leaks:
            lines.append(f"  PID {p['pid']} [{p['process_type']}]: {p['rss_gb']} GB, "
                        f"{p['cpu_pct']}% CPU, started {p['start_time']}, TTY={p['tty']}")

    if result.zombies:
        # Group by type for clearer output
        by_type: dict[str, list[dict]] = {}
        for p in result.zombies:
            by_type.setdefault(p["process_type"], []).append(p)
        for ptype, procs in sorted(by_type.items()):
            threshold = ZOMBIE_THRESHOLDS.get(ptype, MAX_HEADLESS_HOURS)
            lines.append(f"\nZOMBIE {ptype.upper()} (>{threshold}h, no TTY) -- {len(procs)} processes:")
            for p in procs:
                lines.append(f"  PID {p['pid']}: {p['rss_gb']} GB, {p['elapsed_hours']}h old, "
                            f"{p['cpu_pct']}% CPU")

    if result.cpu_runaways:
        lines.append(f"\nCPU RUNAWAYS (>80% for >1h) -- {len(result.cpu_runaways)} processes:")
        for p in result.cpu_runaways:
            lines.append(f"  PID {p['pid']} [{p['process_type']}]: {p['cpu_pct']}% CPU, "
                        f"{p['rss_gb']} GB, started {p['start_time']}")

    if not (result.hard_kills or result.memory_leaks or result.zombies
            or result.cpu_runaways or result.process_sprawl):
        lines.append("\nAll clear -- no issues detected.")

    return "\n".join(lines)


def _has_findings(result: ScanResult) -> bool:
    """Check if scan has any actionable findings."""
    return bool(
        result.hard_kills or result.memory_leaks or result.zombies
        or result.cpu_runaways or result.process_sprawl
    )


def _build_figure_data(result: ScanResult) -> dict:
    """Build figure_data for visualization."""
    return {
        "bar": {
            "metrics": {
                "total_processes": result.total_processes,
                "interactive_processes": result.interactive_count,
                "headless_processes": result.headless_count,
                "zombies_found": len(result.zombies),
                "memory_leaks": len(result.memory_leaks),
                "hard_kills": len(result.hard_kills),
                "cpu_runaways": len(result.cpu_runaways),
                "total_rss_gb": round(result.total_rss_gb, 2),
            }
        }
    }


def _discord_alert(result: ScanResult) -> None:
    """Send Discord alert if there are findings."""
    if not _has_findings(result):
        return

    parts = []
    if result.hard_kills:
        parts.append(f"{len(result.hard_kills)} hard-killed (>{HARD_RSS_GB}GB)")
    if result.memory_leaks:
        parts.append(f"{len(result.memory_leaks)} memory leaks (>{MAX_RSS_GB}GB)")
    if result.zombies:
        # Summarize zombie counts per type
        by_type: dict[str, int] = {}
        for p in result.zombies:
            by_type[p["process_type"]] = by_type.get(p["process_type"], 0) + 1
        zombie_parts = [f"{count} {ptype}" for ptype, count in sorted(by_type.items())]
        parts.append(f"zombies: {', '.join(zombie_parts)}")
    if result.cpu_runaways:
        parts.append(f"{len(result.cpu_runaways)} CPU runaways")
    if result.process_sprawl:
        parts.append(f"process sprawl ({result.total_processes})")

    msg = f"Total: {result.total_processes} procs, {result.total_rss_gb} GB RSS. " + "; ".join(parts)

    severity = "critical" if result.hard_kills else "warning"
    notify_health(
        "monitor-claude",
        severity,
        msg,
        title="Process Health Alert",
        data={
            "total_processes": result.total_processes,
            "total_rss_gb": result.total_rss_gb,
            "hard_kills": len(result.hard_kills),
            "memory_leaks": len(result.memory_leaks),
            "zombies": len(result.zombies),
        },
    )


# ---------------------------------------------------------------------------
# CLI Commands
# ---------------------------------------------------------------------------

@app.command()
def scan(
    kill: bool = typer.Option(False, "--kill", help="Auto-kill processes exceeding hard limits"),
    output_json: bool = typer.Option(False, "--json", help="JSON output"),
    types: str = typer.Option(
        "claude,chromium,python", "--types",
        help="Comma-separated process types to monitor (claude,chromium,python)",
    ),
):
    """One-shot scan of all monitored processes."""
    type_set = _parse_types(types)
    result = scan_processes(kill=kill, types=type_set)
    _log_alert(result)
    _discord_alert(result)

    if output_json:
        output_dict = asdict(result)
        output_dict["figure_data"] = _build_figure_data(result)
        json_str = json.dumps(output_dict, indent=2)
        print(json_str)

        # Save to report file
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        REPORT_FILE.write_text(json_str)
    else:
        print(_format_findings(result))

    # Exit 0 even with findings — the monitor succeeded at detecting problems.
    # Scheduler cares about "did the monitor run?" not "did it find problems?"


@app.command()
def status(
    types: str = typer.Option(
        "claude,chromium,python", "--types",
        help="Comma-separated process types to monitor (claude,chromium,python)",
    ),
):
    """Quick summary of monitored process health."""
    type_set = _parse_types(types)
    processes = get_monitored_processes(types=type_set)
    total_rss = sum(p.rss_gb for p in processes)
    interactive = [p for p in processes if not p.is_headless]
    headless = [p for p in processes if p.is_headless]

    # Count per type
    by_type: dict[str, int] = {}
    for p in processes:
        by_type[p.process_type] = by_type.get(p.process_type, 0) + 1

    print(f"Monitored processes: {len(processes)}")
    for ptype in sorted(by_type):
        print(f"  {ptype}: {by_type[ptype]}")
    print(f"  Interactive: {len(interactive)}")
    print(f"  Headless:    {len(headless)}")
    print(f"Total RSS:     {total_rss:.1f} GB")
    print()

    if processes:
        top = sorted(processes, key=lambda p: p.rss_gb, reverse=True)[:5]
        print("Top 5 by memory:")
        for p in top:
            kind = "headless" if p.is_headless else f"TTY={p.tty}"
            flags = []
            if p.is_hard_limit:
                flags.append("HARD-LIMIT")
            elif p.is_memory_leak:
                flags.append("LEAK")
            if p.is_zombie:
                flags.append("ZOMBIE")
            if p.is_cpu_runaway:
                flags.append("CPU-RUNAWAY")
            flag_str = f" [{', '.join(flags)}]" if flags else ""
            print(f"  PID {p.pid:>8} [{p.process_type:>8}]: {p.rss_gb:>5.1f} GB  "
                  f"{p.cpu_pct:>5.1f}% CPU  {p.elapsed_hours:>5.1f}h  {kind}{flag_str}")


@app.command()
def watch(
    types: str = typer.Option(
        "claude,chromium,python", "--types",
        help="Comma-separated process types to monitor (claude,chromium,python)",
    ),
):
    """Continuous monitoring -- scan every SCAN_INTERVAL seconds."""
    type_set = _parse_types(types)
    logger.info("Starting watch mode (interval={}s, types={})", SCAN_INTERVAL, ",".join(sorted(type_set)))
    while True:
        try:
            result = scan_processes(kill=True, types=type_set)
            _log_alert(result)
            _discord_alert(result)

            if _has_findings(result):
                logger.warning("Findings:\n{}", _format_findings(result))
            else:
                logger.info("All clear -- {} procs, {:.1f} GB",
                           result.total_processes, result.total_rss_gb)

        except Exception as e:
            logger.error("Scan failed: {}", e)
            notify_error("monitor-claude", f"Scan failed: {e}")

        time.sleep(SCAN_INTERVAL)


@app.command()
def history(lines: int = typer.Option(20, "--lines", "-n", help="Number of recent alerts")):
    """Show recent alert history."""
    if not LOG_FILE.exists():
        print("No alert history yet.")
        return

    all_lines = LOG_FILE.read_text().strip().splitlines()
    for line in all_lines[-lines:]:
        try:
            entry = json.loads(line)
            ts = entry.get("timestamp", "?")[:19]
            total = entry.get("total_processes", 0)
            rss = entry.get("total_rss_gb", 0)
            leaks = len(entry.get("memory_leaks", []))
            zombies = len(entry.get("zombies", []))
            kills = len(entry.get("hard_kills", []))
            flags = []
            if kills:
                flags.append(f"{kills} killed")
            if leaks:
                flags.append(f"{leaks} leaks")
            if zombies:
                flags.append(f"{zombies} zombies")
            flag_str = " -- " + ", ".join(flags) if flags else " -- clean"
            print(f"[{ts}] {total} procs, {rss:.1f} GB{flag_str}")
        except json.JSONDecodeError:
            continue


if __name__ == "__main__":
    app()
