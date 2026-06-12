#!/usr/bin/env python3
"""Render a cron registration for a scheduled $loop prompt.

This script intentionally does not install cron by default. It writes:
- loop-job.json
- run-loop.sh wrapper
- crontab.txt with one reviewed crontab line
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import stat
from pathlib import Path

CRON_NICKNAMES = {"@hourly", "@daily", "@weekly", "@monthly", "@yearly", "@annually", "@reboot"}


def validate_job_name(name: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9_.-]+", "-", name.strip()).strip("-._")
    if not slug:
        raise ValueError("job name must contain at least one letter or digit")
    return slug


def validate_schedule(schedule: str) -> None:
    s = schedule.strip()
    if s in CRON_NICKNAMES:
        return
    parts = s.split()
    if len(parts) != 5:
        raise ValueError("cron schedule must be a nickname like @hourly or exactly 5 fields")
    allowed = re.compile(r"^[A-Za-z0-9*/?,#L\-]+$")
    for part in parts:
        if not allowed.match(part):
            raise ValueError(f"unsafe cron field: {part!r}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate a cron entry for a scheduled $loop job.")
    parser.add_argument("--job-name", required=True)
    parser.add_argument("--schedule", required=True, help="Cron expression, e.g. '*/30 * * * *' or '@hourly'.")
    parser.add_argument("--repo", required=True, help="Repository root where Codex should run.")
    parser.add_argument("--prompt-file", required=True, help="Prompt file to feed to Codex.")
    parser.add_argument("--out-dir", default=".loop/jobs", help="Directory to write job artifacts.")
    parser.add_argument("--codex-command", default="codex exec -", help="Command that reads the loop prompt from stdin.")
    args = parser.parse_args()

    job = validate_job_name(args.job_name)
    validate_schedule(args.schedule)

    repo = Path(args.repo).expanduser().resolve()
    prompt_file = Path(args.prompt_file)
    if not prompt_file.is_absolute():
        prompt_file = (repo / prompt_file).resolve()
    out_root = Path(args.out_dir)
    if not out_root.is_absolute():
        out_root = (repo / out_root).resolve()
    job_dir = out_root / job
    log_dir = job_dir / "runs"
    job_dir.mkdir(parents=True, exist_ok=True)
    log_dir.mkdir(parents=True, exist_ok=True)

    if not prompt_file.exists():
        raise FileNotFoundError(f"prompt file does not exist: {prompt_file}")

    runner_source = repo / ".agents" / "skills" / "loop" / "scripts" / "loop_cron_runner.sh"
    if not runner_source.exists():
        raise FileNotFoundError(f"runner not found: {runner_source}")

    local_runner = job_dir / "run-loop.sh"
    local_runner.write_text(
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        f"export LOOP_CODEX_CMD={shlex.quote(args.codex_command)}\n"
        f"exec {shlex.quote(str(runner_source))} {shlex.quote(str(repo))} {shlex.quote(str(prompt_file))} {shlex.quote(str(log_dir))}\n",
        encoding="utf-8",
    )
    local_runner.chmod(local_runner.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

    crontab_line = f"{args.schedule.strip()} {shlex.quote(str(local_runner))} >> {shlex.quote(str(log_dir / 'cron-dispatch.log'))} 2>&1"

    job_payload = {
        "job_name": job,
        "schedule": args.schedule.strip(),
        "repo": str(repo),
        "prompt_file": str(prompt_file),
        "runner": str(local_runner),
        "log_dir": str(log_dir),
        "codex_command": args.codex_command,
        "installed": False,
    }
    (job_dir / "loop-job.json").write_text(json.dumps(job_payload, indent=2) + "\n", encoding="utf-8")
    (job_dir / "crontab.txt").write_text(crontab_line + "\n", encoding="utf-8")

    print(json.dumps({**job_payload, "crontab_file": str(job_dir / "crontab.txt"), "crontab_line": crontab_line}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
