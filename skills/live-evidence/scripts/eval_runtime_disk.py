#!/usr/bin/env python3
"""Agentic eval: the runtime must not default onto a rotational disk.

Live Evidence is latency-critical. It imports torch/whisper/fastapi on every
start and spawns sibling-skill runners per question, so the interpreter and
venv live on the hot path.

Measured on this machine 2026-08-17:
    /home/graham       -> /dev/nvme0n1p2  rotational=0  1.2T free
    /mnt/storage12tb   -> /dev/sda1       rotational=1  87% full

`run.sh` and `sanity.sh` both defaulted `UV_PROJECT_ENVIRONMENT` to
`/mnt/storage12tb/...` whenever that path was writable, i.e. they preferred the
spinning disk and only fell back to NVMe when the slow disk was unavailable.
This eval fails if that preference returns.

It also guards the related defect found in the same session: sibling runners
inherit `UV_PROJECT_ENVIRONMENT` from the server and rebuild the server's own
venv mid-request, which surfaced as `Removed virtual environment at: ...` in
the Ask lane detail, `FileNotFoundError` from the Memory lane, and an SSL CA
bundle vanishing under a running httpx client.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
failures: list[str] = []


def check(name: str, passed: bool, detail: str) -> None:
    print(f"{name}: {'PASS' if passed else 'FAIL'} ({detail})")
    if not passed:
        failures.append(name)


def backing_device(path: Path) -> tuple[str | None, int | None]:
    """Return (device, rotational) for the filesystem holding path."""

    probe = path
    while not probe.exists() and probe != probe.parent:
        probe = probe.parent
    try:
        source = subprocess.run(
            ["df", "--output=source", str(probe)],
            capture_output=True, text=True, check=False,
        ).stdout.strip().splitlines()[-1].strip()
    except Exception:  # noqa: BLE001
        return None, None
    base = subprocess.run(
        ["lsblk", "-no", "pkname", source],
        capture_output=True, text=True, check=False,
    ).stdout.strip().splitlines()
    base_name = base[0].strip() if base else Path(source).name
    rot_file = Path(f"/sys/block/{base_name}/queue/rotational")
    if not rot_file.exists():
        return source, None
    try:
        return source, int(rot_file.read_text().strip())
    except ValueError:
        return source, None


def resolved_default(script: Path) -> str | None:
    """Read the UV_PROJECT_ENVIRONMENT default a launcher script would use."""

    text = script.read_text(encoding="utf-8", errors="ignore")
    matches = re.findall(r'UV_PROJECT_ENVIRONMENT="([^"]+)"', text)
    return matches[-1] if matches else None


def check_launcher_defaults() -> None:
    for name in ("run.sh", "sanity.sh"):
        script = SKILL_DIR / name
        if not script.exists():
            check(f"{name} default venv is not on a spinning disk", False, "script missing")
            continue
        default = resolved_default(script) or ""
        hardcoded_slow = "/mnt/storage12tb" in default
        check(
            f"{name} default venv is not hardcoded to /mnt/storage12tb",
            not hardcoded_slow,
            f"default={default[:90]}",
        )


def check_no_slow_disk_preference() -> None:
    """The launcher must not PREFER the slow disk when it happens to exist."""

    text = (SKILL_DIR / "run.sh").read_text(encoding="utf-8", errors="ignore")
    prefers = bool(
        re.search(r"-w\s+/mnt/storage12tb.*\n\s*export UV_PROJECT_ENVIRONMENT=\"/mnt/storage12tb", text)
    )
    check(
        "run.sh does not prefer the slow disk when writable",
        not prefers,
        "no `if writable /mnt/storage12tb -> use it` branch",
    )


def check_effective_venv_device() -> None:
    """Whatever venv this process would use must not be rotational."""

    env_value = os.getenv("UV_PROJECT_ENVIRONMENT")
    target = Path(env_value) if env_value else Path(
        os.getenv("XDG_CACHE_HOME", str(Path.home() / ".cache"))
    ) / "live-evidence" / "venv"
    device, rotational = backing_device(target)
    if rotational is None:
        check(
            "effective venv is not on a rotational device",
            True,
            f"{target} -> {device}, rotational flag unavailable (skipped)",
        )
        return
    check(
        "effective venv is not on a rotational device",
        rotational == 0,
        f"{target} -> {device} rotational={rotational}",
    )


def check_runner_env_is_sanitised() -> None:
    """Sibling runners must not inherit UV_PROJECT_ENVIRONMENT."""

    sys.path.insert(0, str(SKILL_DIR / "src"))
    try:
        from live_evidence.retrieval.subprocess_env import child_env
    except Exception as exc:  # noqa: BLE001
        check("runner env strips UV_PROJECT_ENVIRONMENT", False, f"import failed: {exc}")
        return

    os.environ["UV_PROJECT_ENVIRONMENT"] = "/tmp/should-not-propagate"
    os.environ["VIRTUAL_ENV"] = "/tmp/should-not-propagate-either"
    env = child_env()
    check(
        "runner env strips UV_PROJECT_ENVIRONMENT",
        "UV_PROJECT_ENVIRONMENT" not in env,
        "a runner inheriting it rebuilds the server's own venv mid-request",
    )
    check(
        "runner env strips VIRTUAL_ENV",
        "VIRTUAL_ENV" not in env,
        "same failure class as UV_PROJECT_ENVIRONMENT",
    )
    check(
        "runner env preserves unrelated variables",
        env.get("PATH") == os.environ.get("PATH"),
        "PATH passes through unchanged",
    )


def check_negative_control() -> None:
    """The rotational detector must actually identify a spinning disk.

    Without this, a detector that always reports rotational=0 would make every
    check above pass vacuously.
    """

    slow = Path("/mnt/storage12tb")
    if not slow.exists():
        check(
            "negative control detects a known rotational disk",
            True,
            "no /mnt/storage12tb on this host (skipped)",
        )
        return
    device, rotational = backing_device(slow)
    check(
        "negative control detects a known rotational disk",
        rotational == 1,
        f"{slow} -> {device} rotational={rotational} (detector discriminates)",
    )


def main() -> int:
    print("live-evidence runtime disk agentic eval")
    print()
    check_launcher_defaults()
    check_no_slow_disk_preference()
    check_effective_venv_device()
    check_runner_env_is_sanitised()
    check_negative_control()
    print()
    if failures:
        print(f"runtime disk eval: FAIL ({len(failures)} failed: {', '.join(failures)})")
        return 1
    print("runtime disk eval: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
