"""Workstation health probes.

Each probe follows the signature ``def probe_*(autofix: bool) -> ProbeResult``
and is registered in ``ALL_PROBES`` at the bottom of this module.

Inputs: filesystem state, system commands.
Outputs: ProbeResult dataclasses consumed by monitor.py reporting layer.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional

from loguru import logger

STORAGE_12TB = Path(os.environ.get("EMBRY_STORAGE", "/mnt/storage12tb"))


# ---------------------------------------------------------------------------
# Probe framework
# ---------------------------------------------------------------------------

class ProbeStatus(str, Enum):
    PASS = "pass"
    WARN = "warn"
    FAIL = "fail"
    SKIP = "skip"
    FIXED = "fixed"


@dataclass
class ProbeResult:
    probe_id: str
    name: str
    status: ProbeStatus
    message: str
    value: float = 0.0
    details: dict = field(default_factory=dict)
    auto_fixable: bool = False
    fix_applied: bool = False


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _disk_usage_pct(path: str = "/") -> float:
    """Return disk usage percentage for a mount point."""
    usage = shutil.disk_usage(path)
    return (usage.used / usage.total) * 100


def _dir_size_gb(path: Path) -> float:
    """Return directory size in GB using du."""
    if not path.exists():
        return 0.0
    try:
        result = subprocess.run(
            ["du", "-sb", str(path)],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode == 0:
            return int(result.stdout.split()[0]) / (1024**3)
    except (subprocess.TimeoutExpired, ValueError, IndexError):
        pass
    return 0.0


# ---------------------------------------------------------------------------
# Probe implementations
# ---------------------------------------------------------------------------

def probe_nvme_usage(autofix: bool = False) -> ProbeResult:
    """W01: Check NVMe root partition usage."""
    pct = _disk_usage_pct("/")
    if pct > 95:
        status = ProbeStatus.FAIL
        msg = f"CRITICAL: NVMe at {pct:.1f}% — immediate action needed"
    elif pct > 85:
        status = ProbeStatus.WARN
        msg = f"NVMe at {pct:.1f}% — above 85% threshold"
    else:
        status = ProbeStatus.PASS
        msg = f"NVMe at {pct:.1f}%"
    return ProbeResult("W01", "nvme-usage", status, msg, value=round(pct, 1))


# Artifact patterns that should be on 12TB, not NVMe
_ARTIFACT_GLOBS = [
    ("*.ckpt", 0),
    ("*.safetensors", 0),
    ("*.bin", 100),  # min MB
    ("*.gguf", 0),
    ("*.webm", 50),
    ("*.mkv", 50),
    ("*.mp4", 100),
]
_ARTIFACT_DIRS = ["models", "backups", "checkpoints", "training_data"]


def probe_nvme_artifacts(autofix: bool = False) -> ProbeResult:
    """W02: Scan for models/backups/media on NVMe that belong on 12TB."""
    home = Path.home()
    violations: list[str] = []

    # Check workspace for artifact directories
    workspace = home / "workspace"
    if workspace.exists():
        for artifact_dir_name in _ARTIFACT_DIRS:
            try:
                result = subprocess.run(
                    ["find", str(workspace), "-maxdepth", "4",
                     "-type", "d", "-name", artifact_dir_name],
                    capture_output=True, text=True, timeout=30,
                )
                for line in result.stdout.strip().splitlines():
                    p = Path(line)
                    # Skip if it's a symlink to 12TB
                    if p.is_symlink():
                        target = str(p.resolve())
                        if target.startswith(str(STORAGE_12TB)):
                            continue
                    size_gb = _dir_size_gb(p)
                    if size_gb > 0.5:  # Only flag dirs > 500MB
                        violations.append(f"{p} ({size_gb:.1f}GB)")
            except subprocess.TimeoutExpired:
                continue

    # Check for large model files in home
    for glob_pattern, min_mb in _ARTIFACT_GLOBS:
        try:
            result = subprocess.run(
                ["find", str(workspace), "-maxdepth", "5",
                 "-name", glob_pattern, "-type", "f"],
                capture_output=True, text=True, timeout=30,
            )
            for line in result.stdout.strip().splitlines():
                if not line:
                    continue
                p = Path(line)
                try:
                    size_mb = p.stat().st_size / (1024**2)
                    if size_mb >= max(min_mb, 100):
                        violations.append(f"{p} ({size_mb:.0f}MB)")
                except OSError:
                    continue
        except subprocess.TimeoutExpired:
            continue

    if violations:
        msg = f"{len(violations)} artifact(s) on NVMe should be on 12TB"
        return ProbeResult(
            "W02", "nvme-artifacts", ProbeStatus.WARN, msg,
            value=len(violations),
            details={"violations": violations[:20]},
        )
    return ProbeResult("W02", "nvme-artifacts", ProbeStatus.PASS,
                       "No artifact violations found")


def probe_cache_bloat(autofix: bool = False) -> ProbeResult:
    """W03: Check known cache directories for bloat."""
    home = Path.home()
    caches = {
        "uv": (home / ".cache/uv", 20),
        "huggingface": (home / ".cache/huggingface", 30),
        "pip": (home / ".cache/pip", 2),
        "npm": (home / ".cache/npm", 2),
    }

    bloated: list[str] = []
    total_gb = 0.0

    for name, (path, threshold_gb) in caches.items():
        size_gb = _dir_size_gb(path)
        total_gb += size_gb
        if size_gb > threshold_gb:
            bloated.append(f"{name}: {size_gb:.1f}GB (>{threshold_gb}GB)")

    fix_applied = False
    if autofix and bloated:
        logger.info("Auto-fixing cache bloat...")
        for cmd in [
            ["uv", "cache", "prune"],
            ["pip", "cache", "purge"],
            ["npm", "cache", "clean", "--force"],
        ]:
            try:
                subprocess.run(cmd, capture_output=True, timeout=120)
                logger.info("Ran: {}", " ".join(cmd))
            except (subprocess.TimeoutExpired, FileNotFoundError):
                pass
        fix_applied = True

    if bloated:
        status = ProbeStatus.FIXED if fix_applied else ProbeStatus.WARN
        msg = f"{len(bloated)} cache(s) over threshold: {', '.join(bloated)}"
    else:
        status = ProbeStatus.PASS
        msg = f"All caches within limits (total: {total_gb:.1f}GB)"

    return ProbeResult(
        "W03", "cache-bloat", status, msg,
        value=round(total_gb, 1),
        auto_fixable=True, fix_applied=fix_applied,
    )


def probe_experiment_growth(autofix: bool = False) -> ProbeResult:
    """W04: Check experiment dirs on NVMe >50GB."""
    experiments = Path.home() / "workspace" / "experiments"
    if not experiments.exists():
        return ProbeResult("W04", "experiment-growth", ProbeStatus.SKIP,
                           "No experiments directory found")

    large: list[str] = []
    total_gb = 0.0

    try:
        for d in sorted(experiments.iterdir()):
            if not d.is_dir():
                continue
            # Skip symlinks pointing to 12TB
            if d.is_symlink():
                target = str(d.resolve())
                if target.startswith(str(STORAGE_12TB)):
                    continue
            size_gb = _dir_size_gb(d)
            total_gb += size_gb
            if size_gb > 50:
                large.append(f"{d.name}: {size_gb:.0f}GB")
    except OSError:
        pass

    if large:
        msg = f"{len(large)} experiment(s) >50GB on NVMe: {', '.join(large)}"
        return ProbeResult("W04", "experiment-growth", ProbeStatus.WARN, msg,
                           value=round(total_gb, 1),
                           details={"large_dirs": large})
    return ProbeResult("W04", "experiment-growth", ProbeStatus.PASS,
                       f"All experiments within limits (total: {total_gb:.0f}GB)",
                       value=round(total_gb, 1))


def probe_arango_backup(autofix: bool = False) -> ProbeResult:
    """W05: Check ArangoDB backup freshness and location."""
    backup_dir = STORAGE_12TB / "backups" / "arangodb"

    # Also check for backups on NVMe (violation)
    nvme_backup = Path.home() / ".local/state/devops-agent/arangodumps"
    if nvme_backup.exists() and any(nvme_backup.iterdir()):
        size_gb = _dir_size_gb(nvme_backup)
        if size_gb > 0.1:
            return ProbeResult(
                "W05", "arango-backup", ProbeStatus.WARN,
                f"ArangoDB backups on NVMe ({size_gb:.1f}GB) — should be on 12TB",
                value=size_gb,
            )

    if not backup_dir.exists():
        return ProbeResult("W05", "arango-backup", ProbeStatus.WARN,
                           f"Backup dir not found: {backup_dir}")

    # Find most recent backup
    backups = sorted(backup_dir.iterdir(), key=lambda p: p.stat().st_mtime,
                     reverse=True) if backup_dir.exists() else []
    if not backups:
        return ProbeResult("W05", "arango-backup", ProbeStatus.WARN,
                           "No backups found on 12TB")

    newest = backups[0]
    age_hours = (time.time() - newest.stat().st_mtime) / 3600

    if age_hours > 48:
        return ProbeResult("W05", "arango-backup", ProbeStatus.WARN,
                           f"Latest backup is {age_hours:.0f}h old (>{48}h threshold)",
                           value=round(age_hours, 1))
    return ProbeResult("W05", "arango-backup", ProbeStatus.PASS,
                       f"Latest backup: {newest.name} ({age_hours:.0f}h ago)",
                       value=round(age_hours, 1))


def probe_docker_reclaimable(autofix: bool = False) -> ProbeResult:
    """W06: Check Docker reclaimable space."""
    try:
        result = subprocess.run(
            ["docker", "system", "df", "--format", "{{.Reclaimable}}"],
            capture_output=True, text=True, timeout=15,
        )
        if result.returncode != 0:
            return ProbeResult("W06", "docker-reclaimable", ProbeStatus.SKIP,
                               "Docker not available")

        # Parse reclaimable sizes — format like "1.2GB (50%)" per line
        total_gb = 0.0
        for line in result.stdout.strip().splitlines():
            line = line.strip()
            if not line:
                continue
            # Extract the size part before any parentheses
            size_str = line.split("(")[0].strip()
            if "GB" in size_str:
                total_gb += float(size_str.replace("GB", "").strip())
            elif "MB" in size_str:
                total_gb += float(size_str.replace("MB", "").strip()) / 1024
            elif "kB" in size_str:
                total_gb += float(size_str.replace("kB", "").strip()) / (1024**2)
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return ProbeResult("W06", "docker-reclaimable", ProbeStatus.SKIP,
                           "Docker command failed")

    if total_gb > 50:
        msg = f"Docker reclaimable: {total_gb:.0f}GB (>50GB) — run `docker system prune`"
        return ProbeResult("W06", "docker-reclaimable", ProbeStatus.WARN, msg,
                           value=round(total_gb, 1))
    return ProbeResult("W06", "docker-reclaimable", ProbeStatus.PASS,
                       f"Docker reclaimable: {total_gb:.1f}GB",
                       value=round(total_gb, 1))


def probe_zombie_processes(autofix: bool = False) -> ProbeResult:
    """W07: Check for zombie processes (daemons >24h, build tools >1h)."""
    zombies: list[str] = []
    def _proc_age_hours(pid: str) -> Optional[float]:
        """Return process age in hours using /proc starttime + uptime."""
        try:
            with open(f"/proc/{pid}/stat") as handle:
                stat = handle.read().split()
            start_ticks = int(stat[21])
            with open("/proc/uptime") as handle:
                uptime_seconds = float(handle.read().split()[0])
            clk_tck = os.sysconf(os.sysconf_names["SC_CLK_TCK"])
            age_seconds = uptime_seconds - (start_ticks / clk_tck)
            if age_seconds < 0:
                return None
            return age_seconds / 3600
        except (OSError, ValueError, IndexError, KeyError):
            return None

    # (pattern, max_age_hours, label)
    _PATTERNS = [
        ("claude", 24, "claude"), ("chromium", 24, "chromium"), ("chrome", 24, "chrome"),
        # 2026-08-27 incident: five codex TUIs aged 2-6 days held ~640k
        # inotify watches and exhausted the kernel budget (ENOSPC for every
        # new dev server). Codex sessions older than 48h are stale.
        ("codex", 48, "codex"),
        ("vitest", 1, "build-zombie"), ("jest", 1, "build-zombie"),
        ("webpack", 1, "build-zombie"), ("esbuild", 1, "build-zombie"),
    ]
    for pattern, max_age, tag in _PATTERNS:
        try:
            result = subprocess.run(
                ["pgrep", "-af", pattern], capture_output=True, text=True, timeout=10)
            for line in result.stdout.strip().splitlines():
                parts = line.split(None, 1)
                if len(parts) < 2 or ("monitor" in parts[1] and "workstation" in parts[1]):
                    continue
                pid, cmd = parts
                age_h = _proc_age_hours(pid)
                if age_h is None:
                    continue
                if age_h > max_age:
                    zombies.append(f"PID {pid} ({tag}, {age_h:.0f}h): {cmd[:80]}")
        except (subprocess.TimeoutExpired, FileNotFoundError):
            continue

    if zombies:
        msg = f"{len(zombies)} zombie process(es) above thresholds"
        return ProbeResult("W07", "zombie-processes", ProbeStatus.WARN, msg,
                           value=len(zombies),
                           details={"zombies": zombies[:10]})
    return ProbeResult("W07", "zombie-processes", ProbeStatus.PASS,
                       "No zombie processes found")


def probe_drive_health(autofix: bool = False) -> ProbeResult:
    """W08: Check SMART status of drives."""
    drives_checked = 0
    issues: list[str] = []

    for dev in ["/dev/nvme0n1", "/dev/sda"]:
        try:
            result = subprocess.run(
                ["sudo", "smartctl", "-H", dev],
                capture_output=True, text=True, timeout=15,
            )
            drives_checked += 1
            output = result.stdout.lower()
            if "passed" not in output and "ok" not in output:
                issues.append(f"{dev}: SMART check did not report PASSED")
        except (subprocess.TimeoutExpired, FileNotFoundError):
            continue

    if drives_checked == 0:
        return ProbeResult("W08", "drive-health", ProbeStatus.SKIP,
                           "smartctl not available or no drives accessible")
    if issues:
        return ProbeResult("W08", "drive-health", ProbeStatus.FAIL,
                           "; ".join(issues), value=len(issues))
    return ProbeResult("W08", "drive-health", ProbeStatus.PASS,
                       f"{drives_checked} drive(s) healthy",
                       value=drives_checked)


# Known /tmp prefixes from skills that create temp workspaces
_TMP_SKILL_PREFIXES = [
    "code-review-workspace-",
    "learn_datalake_worker_",
    "extractor_",
]

# Max age (hours) before a temp dir is considered orphaned
_TMP_MAX_AGE_HOURS = 4
# Size (GB) that forces orphan status regardless of age — no legitimate
# review workspace should be this large (2026-03-05: 979GB incident)
_TMP_SIZE_FORCE_ORPHAN_GB = 1.0
# Total /tmp threshold in GB before warning
_TMP_WARN_GB = 10


def probe_tmp_bloat(autofix: bool = False) -> ProbeResult:
    """W09: Detect /tmp bloat from orphaned skill workspaces."""
    tmp = Path("/tmp")
    orphaned: list[str] = []
    total_gb = 0.0

    # Scan for known skill temp dirs
    try:
        for entry in tmp.iterdir():
            if not entry.is_dir():
                continue
            matched = any(entry.name.startswith(p) for p in _TMP_SKILL_PREFIXES)
            if not matched:
                continue
            try:
                age_hours = (time.time() - entry.stat().st_mtime) / 3600
            except OSError:
                continue
            size_gb = _dir_size_gb(entry)
            # Orphan if old enough OR if suspiciously large (no legit workspace is >1GB)
            if age_hours > _TMP_MAX_AGE_HOURS or size_gb > _TMP_SIZE_FORCE_ORPHAN_GB:
                total_gb += size_gb
                reason = f"{age_hours:.0f}h old" if age_hours > _TMP_MAX_AGE_HOURS else f"oversized"
                orphaned.append(f"{entry.name} ({size_gb:.1f}GB, {reason})")
    except OSError:
        return ProbeResult("W09", "tmp-bloat", ProbeStatus.SKIP,
                           "Cannot read /tmp")

    # Also check total /tmp size
    tmp_total_gb = _dir_size_gb(tmp)

    fix_applied = False
    if autofix and orphaned:
        logger.info("Auto-fixing /tmp bloat: removing {} orphaned dir(s)", len(orphaned))
        for entry in tmp.iterdir():
            if not entry.is_dir():
                continue
            matched = any(entry.name.startswith(p) for p in _TMP_SKILL_PREFIXES)
            if not matched:
                continue
            try:
                age_hours = (time.time() - entry.stat().st_mtime) / 3600
                size_gb = _dir_size_gb(entry)
            except OSError:
                continue
            if age_hours > _TMP_MAX_AGE_HOURS or size_gb > _TMP_SIZE_FORCE_ORPHAN_GB:
                logger.info("Removing orphaned temp dir: {} ({:.1f}GB)", entry.name, size_gb)
                shutil.rmtree(entry, ignore_errors=True)
        # Restart IBus — /tmp fillup breaks its IPC, killing keyboard input
        # in Chrome and other apps. Safe to run even if IBus is healthy.
        try:
            subprocess.run(
                ["ibus-daemon", "--replace", "--xim", "--daemonize"],
                capture_output=True, timeout=10,
            )
            logger.info("Restarted ibus-daemon to restore keyboard input")
        except (subprocess.TimeoutExpired, FileNotFoundError):
            logger.warning("Could not restart ibus-daemon")
        fix_applied = True

    if orphaned:
        status = ProbeStatus.FIXED if fix_applied else ProbeStatus.FAIL
        msg = (f"{len(orphaned)} orphaned temp dir(s) in /tmp "
               f"({total_gb:.1f}GB) — /tmp total: {tmp_total_gb:.0f}GB")
        return ProbeResult(
            "W09", "tmp-bloat", status, msg,
            value=round(total_gb, 1),
            details={"orphaned": orphaned[:20]},
            auto_fixable=True, fix_applied=fix_applied,
        )
    if tmp_total_gb > _TMP_WARN_GB:
        return ProbeResult(
            "W09", "tmp-bloat", ProbeStatus.WARN,
            f"/tmp is {tmp_total_gb:.0f}GB (>{_TMP_WARN_GB}GB) — no known skill dirs, investigate manually",
            value=round(tmp_total_gb, 1),
        )
    return ProbeResult("W09", "tmp-bloat", ProbeStatus.PASS,
                       f"/tmp is {tmp_total_gb:.1f}GB",
                       value=round(tmp_total_gb, 1))


def probe_inotify_watches(autofix: bool = False) -> ProbeResult:
    """W10: Check inotify watch budget (2026-08-27 incident: exhaustion by
    stale agent sessions made every new file-watching dev server fail with
    ENOSPC while the limit itself looked healthy)."""
    try:
        limit = int(Path("/proc/sys/fs/inotify/max_user_watches").read_text())
    except (OSError, ValueError):
        return ProbeResult("W10", "inotify-watches", ProbeStatus.SKIP,
                           "cannot read inotify limits")

    usage: dict[str, int] = {}
    total = 0
    for proc in Path("/proc").glob("[0-9]*"):
        count = 0
        try:
            for fdinfo in (proc / "fdinfo").iterdir():
                try:
                    count += fdinfo.read_text().count("inotify wd:")
                except OSError:
                    continue
        except OSError:
            continue
        if count:
            total += count
            try:
                cmd = (proc / "cmdline").read_bytes().replace(b"\0", b" ").decode()[:60]
            except OSError:
                cmd = "?"
            usage[f"{proc.name} {cmd.strip()}"] = count

    pct = (total / limit) * 100 if limit else 0.0
    top = sorted(usage.items(), key=lambda kv: kv[1], reverse=True)[:5]
    details = {"total": total, "limit": limit,
               "top_consumers": [f"{c} watches: {k}" for k, c in top]}
    msg = f"{total}/{limit} watches in use ({pct:.0f}%)"
    if pct >= 90:
        return ProbeResult("W10", "inotify-watches", ProbeStatus.FAIL, msg,
                           value=round(pct, 1), details=details)
    if pct >= 70:
        return ProbeResult("W10", "inotify-watches", ProbeStatus.WARN, msg,
                           value=round(pct, 1), details=details)
    return ProbeResult("W10", "inotify-watches", ProbeStatus.PASS, msg,
                       value=round(pct, 1), details=details)


# ---------------------------------------------------------------------------
# Probe registry
# ---------------------------------------------------------------------------

ALL_PROBES = [
    ("W01", "nvme-usage", probe_nvme_usage),
    ("W02", "nvme-artifacts", probe_nvme_artifacts),
    ("W03", "cache-bloat", probe_cache_bloat),
    ("W04", "experiment-growth", probe_experiment_growth),
    ("W05", "arango-backup", probe_arango_backup),
    ("W06", "docker-reclaimable", probe_docker_reclaimable),
    ("W07", "zombie-processes", probe_zombie_processes),
    ("W08", "drive-health", probe_drive_health),
    ("W09", "tmp-bloat", probe_tmp_bloat),
    ("W10", "inotify-watches", probe_inotify_watches),
]
