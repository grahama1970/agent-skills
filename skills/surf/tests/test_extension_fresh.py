from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
EXTENSION_FRESH = REPO_ROOT / "skills/surf/scripts/extension-fresh.sh"


def make_surf_cli(root: Path) -> Path:
    surf_cli = root / "surf-cli"
    (surf_cli / "src/service-worker").mkdir(parents=True)
    (surf_cli / "dist/service-worker").mkdir(parents=True)
    (surf_cli / "native").mkdir(parents=True)
    (surf_cli / "src/service-worker/index.ts").write_text("// src\n", encoding="utf-8")
    (surf_cli / "dist/service-worker/index.js").write_text("// dist\n", encoding="utf-8")
    (surf_cli / "native/host.cjs").write_text("// host\n", encoding="utf-8")
    (surf_cli / "native/cli.cjs").write_text("// cli\n", encoding="utf-8")
    return surf_cli


def write_native_manifest(home: Path, installed_host: Path) -> None:
    manifest_dir = home / ".config/google-chrome/NativeMessagingHosts"
    manifest_dir.mkdir(parents=True)
    wrapper = home / ".local/share/surf-cli/host-wrapper.sh"
    wrapper.parent.mkdir(parents=True)
    wrapper.write_text(
        f'#!/bin/bash\ncd "{installed_host.parent}"\nexec "/usr/bin/node" "{installed_host}"\n',
        encoding="utf-8",
    )
    wrapper.chmod(0o755)
    (manifest_dir / "surf.browser.host.json").write_text(
        json.dumps(
            {
                "name": "surf.browser.host",
                "description": "Surf CLI Native Host",
                "path": str(wrapper),
                "type": "stdio",
                "allowed_origins": ["chrome-extension://example/"],
            }
        ),
        encoding="utf-8",
    )


def write_fake_process_tools(bin_dir: Path, running_host: Path) -> None:
    bin_dir.mkdir()
    (bin_dir / "pgrep").write_text(
        f"""#!/usr/bin/env bash
if [[ "$*" == *"{running_host}"* ]]; then
  echo "12345 /usr/bin/node {running_host}"
  exit 0
fi
exit 1
""",
        encoding="utf-8",
    )
    (bin_dir / "ps").write_text(
        """#!/usr/bin/env bash
echo "Thu Dec 31 23:59:59 2026"
""",
        encoding="utf-8",
    )
    (bin_dir / "pgrep").chmod(0o755)
    (bin_dir / "ps").chmod(0o755)


def run_extension_fresh(tmp_path: Path, current_cli: Path, installed_cli: Path) -> subprocess.CompletedProcess[str]:
    home = tmp_path / "home"
    installed_host = installed_cli / "native/host.cjs"
    write_native_manifest(home, installed_host)
    bin_dir = tmp_path / "bin"
    write_fake_process_tools(bin_dir, installed_host)
    env = os.environ.copy()
    env["HOME"] = str(home)
    env["PATH"] = f"{bin_dir}:{env['PATH']}"
    env["SURF_CLI_PATH"] = str(current_cli)
    return subprocess.run(
        ["bash", str(EXTENSION_FRESH), "--json"],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
        check=False,
    )


def test_extension_fresh_reports_installed_host_path_mismatch(tmp_path: Path) -> None:
    current_cli = make_surf_cli(tmp_path / "current")
    installed_cli = make_surf_cli(tmp_path / "installed")

    proc = run_extension_fresh(tmp_path, current_cli, installed_cli)

    assert proc.returncode == 1
    payload = json.loads(proc.stdout)
    assert payload["status"] == "stale"
    assert payload["installed_host_path_mismatch"] is True
    assert payload["host_processes"] == []
    assert payload["installed_host_processes"][0]["host_path"] == str(installed_cli / "native/host.cjs")
    assert payload["reasons"] == [
        "native host path mismatch: installed host is running from a different checkout"
    ]


def test_extension_fresh_accepts_running_host_from_current_checkout(tmp_path: Path) -> None:
    current_cli = make_surf_cli(tmp_path / "current")

    proc = run_extension_fresh(tmp_path, current_cli, current_cli)

    assert proc.returncode == 0
    payload = json.loads(proc.stdout)
    assert payload["status"] == "fresh"
    assert payload["installed_host_path_mismatch"] is False
    assert payload["host_processes"][0]["cmd"].endswith("native/host.cjs")
