from __future__ import annotations

import os
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
INSTALLER = REPO_ROOT / "agents" / "surf-doctor" / "install-tab-maintenance-timer.sh"
SERVICE_TEMPLATE = REPO_ROOT / "agents" / "surf-doctor" / "systemd" / "surf-tab-maintenance.service"
TIMER_TEMPLATE = REPO_ROOT / "agents" / "surf-doctor" / "systemd" / "surf-tab-maintenance.timer"


def run_installer(tmp_path: Path, *args: str, extra_env: dict[str, str] | None = None) -> tuple[subprocess.CompletedProcess[str], Path, Path]:
    xdg_config = tmp_path / "config"
    xdg_state = tmp_path / "state"
    bin_dir = tmp_path / "bin"
    log = tmp_path / "systemctl.log"
    bin_dir.mkdir(exist_ok=True)
    (bin_dir / "systemctl").write_text(
        "#!/usr/bin/env bash\n"
        f"printf '%s\\n' \"$*\" >> {log}\n"
        "exit 0\n"
    )
    (bin_dir / "systemctl").chmod(0o755)
    env = os.environ.copy()
    env.update(
        {
            "HOME": str(tmp_path / "home"),
            "XDG_CONFIG_HOME": str(xdg_config),
            "XDG_STATE_HOME": str(xdg_state),
            "PATH": f"{bin_dir}:{env.get('PATH', '')}",
        }
    )
    if extra_env:
        env.update(extra_env)
    proc = subprocess.run(
        ["bash", str(INSTALLER), *args],
        text=True,
        capture_output=True,
        env=env,
        cwd=REPO_ROOT,
    )
    return proc, xdg_config, log


def test_user_systemd_templates_have_safe_periodic_maintenance_defaults() -> None:
    service = SERVICE_TEMPLATE.read_text()
    timer = TIMER_TEMPLATE.read_text()

    assert "Type=oneshot" in service
    assert "tab-maintenance.sh" not in service  # rendered by installer, not hard-coded
    assert "@TAB_MAINTENANCE_SCRIPT@ --repair-safe" in service
    assert "@RECEIPT_DIR@" in service
    assert "RuntimeMaxSec=@RUNTIME_MAX_SEC@" in service
    assert "TimeoutStartSec=@RUNTIME_MAX_SEC@" in service
    assert "/usr/bin/flock -n %t/surf-tab-maintenance.lock" in service

    assert "OnUnitActiveSec=@CADENCE@" in timer
    assert "RandomizedDelaySec=@RANDOMIZED_DELAY@" in timer
    assert "Persistent=true" in timer
    assert "WantedBy=timers.target" in timer


def test_installer_is_idempotent_and_does_not_enable_or_start_by_default(tmp_path: Path) -> None:
    first, xdg_config, log = run_installer(tmp_path)
    assert first.returncode == 0, first.stderr
    second, _, _ = run_installer(tmp_path)
    assert second.returncode == 0, second.stderr

    user_dir = xdg_config / "systemd" / "user"
    service = (user_dir / "surf-tab-maintenance.service").read_text()
    timer = (user_dir / "surf-tab-maintenance.timer").read_text()
    calls = log.read_text().splitlines()

    assert "OnUnitActiveSec=30min" in timer
    assert "RandomizedDelaySec=5min" in timer
    assert "RuntimeMaxSec=120" in service
    assert "--repair-safe" in service
    assert "/surf/tab-maintenance-receipts" in service
    assert any(call == "--user daemon-reload" for call in calls)
    assert not any(" enable " in f" {call} " for call in calls)
    assert not any(" start " in f" {call} " for call in calls)


def test_installer_only_enables_and_starts_when_explicitly_requested(tmp_path: Path) -> None:
    proc, _, log = run_installer(
        tmp_path,
        "--enable",
        "--start",
        extra_env={
            "SURF_TAB_MAINTENANCE_CADENCE": "45min",
            "SURF_TAB_MAINTENANCE_RANDOMIZED_DELAY": "7min",
        },
    )
    assert proc.returncode == 0, proc.stderr
    calls = log.read_text().splitlines()
    assert "--user enable surf-tab-maintenance.timer" in calls
    assert "--user start surf-tab-maintenance.timer" in calls
