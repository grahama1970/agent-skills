#!/usr/bin/env python3
"""Monitor a book-extractor controller run and manage its cron/tmux helpers."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml


TERMINAL_STATUSES = {"accepted", "complete", "blocked", "cancelled"}
RUNNING_STATUSES = {"running", "extracting", "verifying", "upserting", "reviewing"}


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def marker_begin(job_id: str) -> str:
    return f"# book-extractor-monitor begin job_id={job_id}"


def marker_end(job_id: str) -> str:
    return f"# book-extractor-monitor end job_id={job_id}"


def is_terminal_status(status: str) -> bool:
    return status in TERMINAL_STATUSES or status.startswith("accepted")


def append_jsonl(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, sort_keys=True) + "\n")


def append_line(path: Path, line: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(line.rstrip() + "\n")


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.exists():
        return rows
    with path.open(encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                rows.append({"__parse_error__": str(exc), "__line__": line_no})
                continue
            if isinstance(row, dict):
                row.setdefault("__line__", line_no)
                rows.append(row)
    return rows


def count_jsonl(path: Path) -> int:
    if not path.exists():
        return 0
    with path.open(encoding="utf-8") as handle:
        return sum(1 for line in handle if line.strip())


def pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def acquire_lock(controller_root: Path) -> tuple[Path, bool, dict[str, Any] | None]:
    path = controller_root / "monitor.lock"
    payload = {"pid": os.getpid(), "created_at": now()}
    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        existing = read_json(path)
        pid = int(existing.get("pid") or 0)
        if pid and pid_alive(pid):
            return path, False, existing
        path.unlink(missing_ok=True)
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    return path, True, None


def release_lock(path: Path, owned: bool) -> None:
    if owned:
        path.unlink(missing_ok=True)


def active_child_process(controller_root: Path) -> dict[str, Any]:
    pid_paths = {
        "worker": controller_root / "worker.pid",
        "monitor": controller_root / "chapter_step_progress_monitor.pid",
    }
    active: dict[str, Any] = {}
    for name, path in pid_paths.items():
        if not path.exists():
            continue
        try:
            pid = int(path.read_text(encoding="utf-8").strip())
        except ValueError:
            active[name] = {"pid_path": str(path), "parse_error": True}
            continue
        if pid_alive(pid):
            active[name] = {"pid": pid, "pid_path": str(path)}
    return active


def latest_jsonl(path: Path) -> dict[str, Any]:
    rows = load_jsonl(path)
    return rows[-1] if rows else {}


def parse_timestamp(value: object) -> float | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        normalized = value.replace("Z", "+00:00")
        return datetime.fromisoformat(normalized).timestamp()
    except ValueError:
        return None


def summarize_progress(controller_root: Path) -> dict[str, Any]:
    progress_path = controller_root / "chapter_step_progress.jsonl"
    rows = [row for row in load_jsonl(progress_path) if not row.get("__parse_error__")]
    step_rows = [row for row in rows if row.get("schema_version") == "book_extractor_chapter_step_progress.v1"]
    accepted_steps = [row for row in step_rows if row.get("accepted") is True]
    latest_step = step_rows[-1] if step_rows else {}
    chapters_seen = sorted({str(row.get("chapter_id")) for row in step_rows if row.get("chapter_id")})
    chunks_seen = sorted(
        {
            f"{row.get('chapter_id')}:{row.get('chunk_id')}"
            for row in step_rows
            if row.get("chapter_id") and row.get("chunk_id")
        }
    )
    latest_ts = parse_timestamp(latest_step.get("timestamp"))
    elapsed_since_progress_s = round(time.time() - latest_ts, 3) if latest_ts else None
    return {
        "chapter_step_progress_path": str(progress_path),
        "step_row_count": len(step_rows),
        "accepted_step_count": len(accepted_steps),
        "accepted_chapter_count": len(chapters_seen),
        "accepted_chunk_count": len(chunks_seen),
        "latest_chapter_id": latest_step.get("chapter_id"),
        "latest_chapter_index": latest_step.get("chapter_index"),
        "latest_chunk_id": latest_step.get("chunk_id"),
        "latest_progress_timestamp": latest_step.get("timestamp"),
        "elapsed_since_progress_s": elapsed_since_progress_s,
    }


def summarize_controller(controller_root: Path, state: dict[str, Any]) -> dict[str, Any]:
    latest_command = latest_jsonl(controller_root / "commands.jsonl")
    return {
        "state_status": state.get("status"),
        "state_phase": state.get("phase"),
        "current_artifact": state.get("current_artifact"),
        "next_action": state.get("next_action"),
        "last_command": state.get("last_command"),
        "latest_command_id": latest_command.get("command_id"),
        "latest_command_exit_code": latest_command.get("exit_code"),
        "command_count": count_jsonl(controller_root / "commands.jsonl"),
        "issue_count": count_jsonl(controller_root / "issues.jsonl"),
        "course_correction_count": count_jsonl(controller_root / "course_corrections.jsonl"),
    }


def render_monitor_log_line(row: dict[str, Any]) -> str:
    progress = row.get("progress") or {}
    return (
        f"{row.get('timestamp')} status={row.get('state_status')} phase={row.get('state_phase')} "
        f"steps={progress.get('accepted_step_count')}/{progress.get('step_row_count')} "
        f"chapter={progress.get('latest_chapter_index')} chunk={progress.get('latest_chunk_id')} "
        f"idle_s={progress.get('elapsed_since_progress_s')} active={sorted((row.get('active_child_processes') or {}).keys())}"
    )


def write_monitor_status(controller_root: Path, row: dict[str, Any]) -> None:
    progress = row.get("progress") or {}
    tmux_state = read_json(tmux_state_path(controller_root))
    lines = [
        "# Book Extractor Monitor",
        "",
        f"- Status: {row.get('state_status')}",
        f"- Phase: {row.get('state_phase')}",
        f"- Job: `{row.get('job_id')}`",
        f"- Controller root: `{row.get('controller_root')}`",
        f"- Active child processes: `{sorted((row.get('active_child_processes') or {}).keys())}`",
        f"- Latest chapter/chunk: `{progress.get('latest_chapter_id')}` / `{progress.get('latest_chunk_id')}`",
        f"- Accepted step rows: {progress.get('accepted_step_count')} of {progress.get('step_row_count')}",
        f"- Accepted chapters/chunks seen: {progress.get('accepted_chapter_count')} chapters, {progress.get('accepted_chunk_count')} chunks",
        f"- Last progress timestamp: `{progress.get('latest_progress_timestamp')}`",
        f"- Seconds since progress: {progress.get('elapsed_since_progress_s')}",
        f"- Latest command id: `{row.get('latest_command_id')}` exit `{row.get('latest_command_exit_code')}`",
        f"- Single tail log: `{controller_root / 'monitor.log'}`",
        f"- Tmux attach command: `{tmux_state.get('attach_command') or ''}`",
        f"- Updated: `{row.get('timestamp')}`",
        "",
    ]
    (controller_root / "monitor_status.md").write_text("\n".join(lines), encoding="utf-8")


def default_tick_command(*, controller_root: Path, job_id: str, crontab_file: Path | None = None) -> str:
    script = Path(__file__).resolve()
    parts = [
        sys.executable,
        str(script),
        "tick",
        "--controller-root",
        str(controller_root),
        "--job-id",
        job_id,
    ]
    if crontab_file:
        parts.extend(["--crontab-file", str(crontab_file)])
    return " ".join(shlex_quote(part) for part in parts)


def shlex_quote(value: str) -> str:
    if all(ch.isalnum() or ch in "._/-:=+" for ch in value):
        return value
    return "'" + value.replace("'", "'\\''") + "'"


def tmux_slug(value: str) -> str:
    slug = "".join(ch.lower() if ch.isalnum() else "-" for ch in value).strip("-")
    while "--" in slug:
        slug = slug.replace("--", "-")
    return slug[:80] or "job"


def default_tmux_session_name(job_id: str) -> str:
    return f"book-extractor-{tmux_slug(job_id)}"


def tmux_state_path(controller_root: Path) -> Path:
    return controller_root / "tmux_state.json"


def tmux_private_dir(controller_root: Path) -> Path:
    return controller_root / "tmux"


def tmux_socket_path(controller_root: Path) -> Path:
    return tmux_private_dir(controller_root) / "tmux.sock"


def tmux_base_cmd(socket_path: Path) -> list[str]:
    return ["tmux", "-S", str(socket_path), "-f", "/dev/null"]


def tmux_attach_command(socket_path: Path, session_name: str) -> str:
    return " ".join(shlex_quote(part) for part in ["tmux", "-S", str(socket_path), "attach-session", "-t", session_name])


def tmux_stop_command(socket_path: Path) -> str:
    return " ".join(shlex_quote(part) for part in ["tmux", "-S", str(socket_path), "kill-server"])


def tmux_session_alive(socket_path: Path, session_name: str) -> bool:
    if shutil.which("tmux") is None or not socket_path.exists():
        return False
    proc = subprocess.run(
        [*tmux_base_cmd(socket_path), "has-session", "-t", session_name],
        text=True,
        capture_output=True,
        check=False,
    )
    return proc.returncode == 0


def default_tmux_command(controller_root: Path) -> str:
    monitor_log = controller_root / "monitor.log"
    monitor_status = controller_root / "monitor_status.md"
    return (
        f"printf '%s\\n' {shlex_quote('Book extractor monitor')}; "
        f"printf '%s\\n' {shlex_quote('tail: ' + str(monitor_log))}; "
        f"printf '%s\\n\\n' {shlex_quote('status: ' + str(monitor_status))}; "
        f"touch {shlex_quote(str(monitor_log))}; "
        f"tail -n 80 -F {shlex_quote(str(monitor_log))}"
    )


def write_tmux_state(controller_root: Path, row: dict[str, Any]) -> None:
    path = tmux_state_path(controller_root)
    current = read_json(path)
    current.update(row)
    current["updated_at"] = now()
    path.write_text(json.dumps(current, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def launch_tmux(args: argparse.Namespace) -> dict[str, Any]:
    if shutil.which("tmux") is None:
        raise SystemExit("tmux is not installed or not on PATH")
    controller_root = args.controller_root
    private_dir = tmux_private_dir(controller_root)
    private_dir.mkdir(parents=True, exist_ok=True)
    socket_path = tmux_socket_path(controller_root)
    session_name = args.tmux_session or default_tmux_session_name(args.job_id)
    command = args.tmux_command or default_tmux_command(controller_root)
    running = tmux_session_alive(socket_path, session_name)
    if not running:
        proc = subprocess.run(
            [
                *tmux_base_cmd(socket_path),
                "new-session",
                "-d",
                "-s",
                session_name,
                "-n",
                "monitor",
                "bash",
                "-lc",
                command,
            ],
            text=True,
            capture_output=True,
            check=False,
        )
        if proc.returncode != 0:
            raise SystemExit(f"tmux launch failed: {proc.stderr.strip()}")
    state = {
        "schema_version": "book_extractor_tmux_state.v1",
        "job_id": args.job_id,
        "controller_root": str(controller_root),
        "session_name": session_name,
        "socket_path": str(socket_path),
        "target": session_name,
        "command": command,
        "attach_command": tmux_attach_command(socket_path, session_name),
        "stop_command": tmux_stop_command(socket_path),
        "running": True,
        "already_running": running,
        "launched_at": now(),
    }
    write_tmux_state(controller_root, state)
    write_monitor_state(controller_root, {"job_id": args.job_id, "controller_root": str(controller_root), "tmux_state_path": str(tmux_state_path(controller_root))})
    append_jsonl(controller_root / "monitor_events.jsonl", {"event": "tmux_launched", "timestamp": now(), **state})
    append_line(controller_root / "monitor.log", f"{now()} tmux_launched job_id={args.job_id} session={session_name} socket={socket_path}")
    return state


def attach_tmux(args: argparse.Namespace) -> dict[str, Any]:
    state = read_json(tmux_state_path(args.controller_root))
    socket_path = Path(state.get("socket_path") or tmux_socket_path(args.controller_root))
    session_name = str(state.get("session_name") or args.tmux_session or default_tmux_session_name(args.job_id))
    if not tmux_session_alive(socket_path, session_name):
        raise SystemExit(f"tmux session is not running: {tmux_attach_command(socket_path, session_name)}")
    if args.print_command:
        return {
            "schema_version": "book_extractor_tmux_attach.v1",
            "job_id": args.job_id,
            "controller_root": str(args.controller_root),
            "attach_command": tmux_attach_command(socket_path, session_name),
            "running": True,
        }
    proc = subprocess.run(["tmux", "-S", str(socket_path), "attach-session", "-t", session_name], check=False)
    return {
        "schema_version": "book_extractor_tmux_attach.v1",
        "job_id": args.job_id,
        "controller_root": str(args.controller_root),
        "attach_command": tmux_attach_command(socket_path, session_name),
        "attach_exit_code": proc.returncode,
        "running_after_attach": tmux_session_alive(socket_path, session_name),
    }


def stop_tmux(args: argparse.Namespace) -> dict[str, Any]:
    state = read_json(tmux_state_path(args.controller_root))
    socket_path = Path(state.get("socket_path") or tmux_socket_path(args.controller_root))
    session_name = str(state.get("session_name") or args.tmux_session or default_tmux_session_name(args.job_id))
    was_running = tmux_session_alive(socket_path, session_name)
    exit_code = 0
    stderr = ""
    if was_running:
        proc = subprocess.run([*tmux_base_cmd(socket_path), "kill-server"], text=True, capture_output=True, check=False)
        exit_code = proc.returncode
        stderr = proc.stderr.strip()
        if proc.returncode != 0:
            raise SystemExit(f"tmux stop failed: {stderr}")
    result = {
        "schema_version": "book_extractor_tmux_stop.v1",
        "job_id": args.job_id,
        "controller_root": str(args.controller_root),
        "session_name": session_name,
        "socket_path": str(socket_path),
        "stopped_at": now(),
        "was_running": was_running,
        "running": False,
        "exit_code": exit_code,
        "stderr": stderr,
    }
    write_tmux_state(args.controller_root, result)
    append_jsonl(args.controller_root / "monitor_events.jsonl", {"event": "tmux_stopped", "timestamp": now(), **result})
    append_line(args.controller_root / "monitor.log", f"{now()} tmux_stopped job_id={args.job_id} session={session_name} was_running={was_running}")
    return result


def render_cron_block(*, job_id: str, schedule: str, command: str) -> str:
    return "\n".join([marker_begin(job_id), f"{schedule} {command}", marker_end(job_id)])


def remove_cron_block_text(crontab_text: str, job_id: str) -> tuple[str, bool]:
    begin = marker_begin(job_id)
    end = marker_end(job_id)
    lines = crontab_text.splitlines()
    output: list[str] = []
    removed = False
    index = 0
    while index < len(lines):
        if lines[index].strip() == begin:
            removed = True
            index += 1
            while index < len(lines) and lines[index].strip() != end:
                index += 1
            if index < len(lines) and lines[index].strip() == end:
                index += 1
            continue
        output.append(lines[index])
        index += 1
    result = "\n".join(output).rstrip()
    if result:
        result += "\n"
    return result, removed


def install_cron_block_text(crontab_text: str, *, job_id: str, schedule: str, command: str) -> tuple[str, bool]:
    without, removed_existing = remove_cron_block_text(crontab_text, job_id)
    block = render_cron_block(job_id=job_id, schedule=schedule, command=command)
    prefix = without.rstrip()
    if prefix:
        return f"{prefix}\n{block}\n", removed_existing
    return f"{block}\n", removed_existing


def read_crontab(path: Path | None) -> str:
    if path is not None:
        return path.read_text(encoding="utf-8") if path.exists() else ""
    proc = subprocess.run(["crontab", "-l"], text=True, capture_output=True, check=False)
    if proc.returncode != 0:
        return ""
    return proc.stdout


def write_crontab(path: Path | None, content: str) -> None:
    if path is not None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return
    subprocess.run(["crontab", "-"], input=content, text=True, check=True)


def write_monitor_state(controller_root: Path, row: dict[str, Any]) -> None:
    path = controller_root / "monitor_state.json"
    current = read_json(path)
    current.update(row)
    current["updated_at"] = now()
    path.write_text(json.dumps(current, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def install_cron(args: argparse.Namespace) -> dict[str, Any]:
    controller_root = args.controller_root
    cron_command = args.cron_command or default_tick_command(
        controller_root=controller_root,
        job_id=args.job_id,
        crontab_file=args.crontab_file if args.embed_crontab_file_in_command else None,
    )
    text = read_crontab(args.crontab_file)
    updated, replaced_existing = install_cron_block_text(text, job_id=args.job_id, schedule=args.schedule, command=cron_command)
    write_crontab(args.crontab_file, updated)
    row = {
        "schema_version": "book_extractor_monitor_state.v1",
        "job_id": args.job_id,
        "controller_root": str(controller_root),
        "mode": "cron",
        "cron_installed": True,
        "cron_command": cron_command,
        "cron_replaced_existing": replaced_existing,
        "cron_marker_begin": marker_begin(args.job_id),
        "cron_marker_end": marker_end(args.job_id),
        "crontab_file": str(args.crontab_file) if args.crontab_file else None,
        "heartbeat_path": str(controller_root / "heartbeat.jsonl"),
        "monitor_events_path": str(controller_root / "monitor_events.jsonl"),
        "monitor_log_path": str(controller_root / "monitor.log"),
        "monitor_status_path": str(controller_root / "monitor_status.md"),
        "monitor_stop_report_path": str(controller_root / "monitor_stop_report.json"),
    }
    write_monitor_state(controller_root, row)
    append_jsonl(controller_root / "monitor_events.jsonl", {"event": "cron_installed", "timestamp": now(), **row})
    append_line(controller_root / "monitor.log", f"{now()} cron_installed job_id={args.job_id} schedule={args.schedule}")
    return row


def remove_cron(args: argparse.Namespace, *, reason: str = "manual") -> dict[str, Any]:
    controller_root = args.controller_root
    text = read_crontab(args.crontab_file)
    updated, removed = remove_cron_block_text(text, args.job_id)
    write_crontab(args.crontab_file, updated)
    report = {
        "schema_version": "book_extractor_monitor_stop_report.v1",
        "job_id": args.job_id,
        "controller_root": str(controller_root),
        "stopped_at": now(),
        "reason": reason,
        "cron_entry_removed": removed,
        "cron_marker_begin": marker_begin(args.job_id),
        "cron_marker_end": marker_end(args.job_id),
        "crontab_file": str(args.crontab_file) if args.crontab_file else None,
        "active_child_processes": active_child_process(controller_root),
    }
    (controller_root / "monitor_stop_report.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    write_monitor_state(controller_root, {"job_id": args.job_id, "controller_root": str(controller_root), "mode": "cron", "cron_installed": False, "last_stop_reason": reason})
    append_jsonl(controller_root / "monitor_events.jsonl", {"event": "monitor_stopped", "timestamp": now(), **report})
    append_line(controller_root / "monitor.log", f"{now()} monitor_stopped job_id={args.job_id} reason={reason} cron_entry_removed={removed}")
    return report


def restart_worker_if_configured(args: argparse.Namespace, row: dict[str, Any]) -> dict[str, Any] | None:
    state_status = str(row.get("state_status") or "")
    if is_terminal_status(state_status) or state_status not in RUNNING_STATUSES:
        return None
    if row.get("active_child_processes"):
        return None
    monitor_state = read_json(args.controller_root / "monitor_state.json")
    restart_command = args.restart_command or monitor_state.get("restart_command")
    if not restart_command:
        return None
    started = now()
    proc = subprocess.run(restart_command, shell=True, cwd=str(args.controller_root), text=True, capture_output=True, check=False)
    repair = {
        "schema_version": "book_extractor_monitor_repair_attempt.v1",
        "timestamp": started,
        "job_id": args.job_id,
        "controller_root": str(args.controller_root),
        "action": "restart_worker",
        "command": restart_command,
        "exit_code": proc.returncode,
        "stdout": proc.stdout[-4000:],
        "stderr": proc.stderr[-4000:],
    }
    append_jsonl(args.controller_root / "monitor_repair_attempts.jsonl", repair)
    append_jsonl(args.controller_root / "monitor_events.jsonl", {"event": "restart_worker_attempted", **repair})
    append_line(args.controller_root / "monitor.log", f"{now()} restart_worker_attempted exit_code={proc.returncode} command={restart_command}")
    return repair


def tick(args: argparse.Namespace) -> dict[str, Any]:
    controller_root = args.controller_root
    lock_path, owned, existing_lock = acquire_lock(controller_root)
    if not owned:
        row = {
            "schema_version": "book_extractor_monitor_heartbeat.v1",
            "timestamp": now(),
            "job_id": args.job_id,
            "controller_root": str(controller_root),
            "event": "monitor_lock_busy",
            "existing_lock": existing_lock,
        }
        append_jsonl(controller_root / "heartbeat.jsonl", row)
        append_line(controller_root / "monitor.log", f"{row['timestamp']} monitor_lock_busy job_id={args.job_id}")
        return row
    try:
        state = read_json(controller_root / "state.json")
        active_children = active_child_process(controller_root)
        row = {
            "schema_version": "book_extractor_monitor_heartbeat.v1",
            "timestamp": now(),
            "job_id": args.job_id,
            "controller_root": str(controller_root),
            "state_status": state.get("status"),
            "state_phase": state.get("phase"),
            "active_child_processes": active_children,
            "progress": summarize_progress(controller_root),
            **summarize_controller(controller_root, state),
        }
        append_jsonl(controller_root / "heartbeat.jsonl", row)
        write_monitor_state(
            controller_root,
            {
                "job_id": args.job_id,
                "controller_root": str(controller_root),
                "last_heartbeat": row["timestamp"],
                "last_state_status": state.get("status"),
                "last_state_phase": state.get("phase"),
                "last_progress": row["progress"],
                "monitor_log_path": str(controller_root / "monitor.log"),
                "monitor_status_path": str(controller_root / "monitor_status.md"),
            },
        )
        write_monitor_status(controller_root, row)
        append_line(controller_root / "monitor.log", render_monitor_log_line(row))
        repair = restart_worker_if_configured(args, row)
        if repair is not None:
            row["repair_attempt"] = repair
        if is_terminal_status(str(state.get("status") or "")) and not active_children:
            return remove_cron(args, reason=f"terminal_state:{state.get('status')}")
        append_jsonl(controller_root / "monitor_events.jsonl", {"event": "monitor_tick", **row})
        return row
    finally:
        release_lock(lock_path, owned)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Book-extractor job-local monitor and cron lifecycle helper.")
    sub = parser.add_subparsers(dest="action", required=True)
    for name in ("install-cron", "remove-cron", "tick", "launch-tmux", "attach-tmux", "stop-tmux"):
        child = sub.add_parser(name)
        child.add_argument("--job-file", type=Path, default=None, help="Book extractor YAML job; derives job id, controller root, and schedule.")
        child.add_argument("--controller-root", type=Path, default=None)
        child.add_argument("--job-id", default=None)
        child.add_argument("--crontab-file", type=Path, default=None, help="Test/controlled crontab file. Omit to use user crontab.")
        child.add_argument("--restart-command", default=None, help="Optional shell command used by tick to restart a resumable dead worker.")
        if name == "install-cron":
            child.add_argument("--schedule", default="* * * * *")
            child.add_argument("--command", dest="cron_command", default=None)
            child.add_argument("--embed-crontab-file-in-command", action="store_true")
        if name in {"launch-tmux", "attach-tmux", "stop-tmux"}:
            child.add_argument("--tmux-session", default=None, help="Override tmux session name. Defaults to a job-id-derived name.")
        if name == "launch-tmux":
            child.add_argument("--tmux-command", default=None, help="Shell command to run inside the tmux monitor pane.")
        if name == "attach-tmux":
            child.add_argument("--print-command", action="store_true", help="Print the attach command instead of attaching the current TTY.")
    return parser


def apply_job_file_defaults(args: argparse.Namespace) -> None:
    if not args.job_file:
        if args.controller_root is None or not args.job_id:
            raise SystemExit("--controller-root and --job-id are required unless --job-file is supplied")
        return
    job = yaml.safe_load(args.job_file.read_text(encoding="utf-8")) or {}
    if not args.job_id:
        args.job_id = str(job.get("job_id") or "")
    if args.controller_root is None:
        outputs = job.get("outputs") or {}
        root = outputs.get("root")
        if root:
            args.controller_root = Path(root) / "book_extractor"
    if getattr(args, "schedule", None) == "* * * * *":
        runtime = job.get("runtime") or {}
        args.schedule = str(runtime.get("self_monitor_schedule") or args.schedule)
    if args.controller_root is None or not args.job_id:
        raise SystemExit(f"job file missing required job_id or outputs.root: {args.job_file}")


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    apply_job_file_defaults(args)
    args.controller_root.mkdir(parents=True, exist_ok=True)
    if args.action == "install-cron":
        result = install_cron(args)
    elif args.action == "remove-cron":
        result = remove_cron(args)
    elif args.action == "tick":
        result = tick(args)
    elif args.action == "launch-tmux":
        result = launch_tmux(args)
    elif args.action == "attach-tmux":
        result = attach_tmux(args)
    else:
        result = stop_tmux(args)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
