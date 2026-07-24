from __future__ import annotations

import os
import subprocess
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
