from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
ENSURE_SURF_CLI = REPO_ROOT / "skills/surf/scripts/ensure-surf-cli.sh"


def make_surf_cli(root: Path, *, host_newer_than_dist: bool) -> Path:
    surf_cli = root / "surf-cli"
    (surf_cli / "src/service-worker").mkdir(parents=True)
    (surf_cli / "dist/service-worker").mkdir(parents=True)
    (surf_cli / "native").mkdir(parents=True)
    (surf_cli / "package.json").write_text('{"scripts":{"build":"echo build"}}\n', encoding="utf-8")
    (surf_cli / "package-lock.json").write_text('{"lockfileVersion":3}\n', encoding="utf-8")
    (surf_cli / "dist/manifest.json").write_text("{}\n", encoding="utf-8")
    (surf_cli / "src/service-worker/index.ts").write_text("// src\n", encoding="utf-8")
    (surf_cli / "dist/service-worker/index.js").write_text("// dist\n", encoding="utf-8")
    (surf_cli / "native/host.cjs").write_text("// host\n", encoding="utf-8")

    older = 1_700_000_000_000_000_000
    dist = older + 1_000_000_000
    host = dist + 1_000_000_000 if host_newer_than_dist else older
    os.utime(surf_cli / "src/service-worker/index.ts", ns=(older, older))
    os.utime(surf_cli / "dist/service-worker/index.js", ns=(dist, dist))
    os.utime(surf_cli / "native/host.cjs", ns=(host, host))
    return surf_cli


def test_ensure_surf_cli_rebuilds_when_native_host_is_newer_than_dist(tmp_path: Path) -> None:
    surf_cli = make_surf_cli(tmp_path, host_newer_than_dist=True)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    npm_log = tmp_path / "npm.log"
    npm = bin_dir / "npm"
    npm.write_text(
        f"""#!/usr/bin/env bash
printf '%s\\n' "$*" >> "{npm_log}"
if [[ "$*" == "run build" ]]; then
  mkdir -p "${{SURF_CLI_PATH}}/dist/service-worker"
  touch "${{SURF_CLI_PATH}}/dist/manifest.json"
  touch "${{SURF_CLI_PATH}}/dist/service-worker/index.js"
fi
exit 0
""",
        encoding="utf-8",
    )
    npm.chmod(0o755)

    env = os.environ.copy()
    env["PATH"] = f"{bin_dir}:{env['PATH']}"
    env["SURF_CLI_PATH"] = str(surf_cli)
    proc = subprocess.run(
        ["bash", str(ENSURE_SURF_CLI)],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
        check=False,
    )

    assert proc.returncode == 0, proc.stderr
    assert "Building vendored surf-cli" in proc.stderr
    assert npm_log.read_text(encoding="utf-8").splitlines() == ["ci", "run build"]


def test_ensure_surf_cli_serializes_concurrent_builds(tmp_path: Path) -> None:
    surf_cli = make_surf_cli(tmp_path, host_newer_than_dist=True)
    bin_dir = tmp_path / "bin"
    state_dir = tmp_path / "state"
    bin_dir.mkdir()
    state_dir.mkdir()
    (state_dir / "active").write_text("0\n", encoding="utf-8")
    (state_dir / "max_active").write_text("0\n", encoding="utf-8")
    npm_log = state_dir / "npm.log"
    npm = bin_dir / "npm"
    npm.write_text(
        f"""#!/usr/bin/env bash
set -euo pipefail
state="{state_dir}"
(
  flock 200
  active="$(cat "$state/active")"
  active=$((active + 1))
  printf '%s\\n' "$active" > "$state/active"
  max_active="$(cat "$state/max_active")"
  if [[ "$active" -gt "$max_active" ]]; then
    printf '%s\\n' "$active" > "$state/max_active"
  fi
) 200>"$state/active.lock"
printf '%s\\n' "$*" >> "{npm_log}"
sleep 0.2
if [[ "$*" == "run build" ]]; then
  mkdir -p "${{SURF_CLI_PATH}}/dist/service-worker"
  touch "${{SURF_CLI_PATH}}/dist/manifest.json"
  touch "${{SURF_CLI_PATH}}/dist/service-worker/index.js"
fi
(
  flock 200
  active="$(cat "$state/active")"
  active=$((active - 1))
  printf '%s\\n' "$active" > "$state/active"
) 200>"$state/active.lock"
""",
        encoding="utf-8",
    )
    npm.chmod(0o755)

    env = os.environ.copy()
    env["PATH"] = f"{bin_dir}:{env['PATH']}"
    env["SURF_CLI_PATH"] = str(surf_cli)
    procs = [
        subprocess.Popen(
            ["bash", str(ENSURE_SURF_CLI)],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
        )
        for _ in range(8)
    ]
    results = [proc.communicate(timeout=10) + (proc.returncode,) for proc in procs]

    assert all(rc == 0 for _out, _err, rc in results), results
    assert npm_log.read_text(encoding="utf-8").splitlines() == ["ci", "run build"]
    assert (state_dir / "max_active").read_text(encoding="utf-8").strip() == "1"
    assert surf_cli.joinpath("dist/service-worker/index.js").stat().st_mtime_ns > surf_cli.joinpath(
        "native/host.cjs"
    ).stat().st_mtime_ns


def test_ensure_surf_cli_bounds_hung_build(tmp_path: Path) -> None:
    surf_cli = make_surf_cli(tmp_path, host_newer_than_dist=True)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    npm = bin_dir / "npm"
    npm.write_text(
        """#!/usr/bin/env bash
sleep 5
""",
        encoding="utf-8",
    )
    npm.chmod(0o755)

    env = os.environ.copy()
    env["PATH"] = f"{bin_dir}:{env['PATH']}"
    env["SURF_CLI_PATH"] = str(surf_cli)
    env["SURF_CLI_BUILD_TIMEOUT_SECONDS"] = "1"
    started = time.monotonic()
    proc = subprocess.run(
        ["bash", str(ENSURE_SURF_CLI)],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
        check=False,
    )
    elapsed = time.monotonic() - started

    assert proc.returncode == 124
    assert elapsed < 4
    assert "surf-cli build timed out after 1s" in proc.stderr
