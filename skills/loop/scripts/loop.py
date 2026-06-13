#!/usr/bin/env python3
"""Executable harness for one bounded $loop artifact transaction."""
from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import os
import re
import signal
import shlex
import subprocess
import sys
import time
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any


FINAL_SCHEMA = "loop.final_receipt.v1"
VERDICTS = {"PASS", "NEEDS_CHANGES", "BLOCKED"}
STOP_CODE_REVIEWER_PASS = "CODE_REVIEWER_PASS"
TIMEOUT_RETURNCODE = -124
CHECK_TIMEOUT_RETURNCODE = -125
DEFAULT_IGNORES = (".loop/", "__pycache__/", ".pyc", ".pyo")
RESERVED_LOOP_ENV = {"LOOP_RUN_DIR", "LOOP_CHECKS_JSON", "LOOP_DIFF_PATH"}
INTENTIONAL_LOOP_ENV = {"LOOP_FIXTURE_MODE"}


class ArtifactWriteError(RuntimeError):
    pass


@dataclass(frozen=True)
class AgentConfig:
    name: str
    cmd: str | list[str]
    writes: bool
    timeout_seconds: int


def run_cmd(args: list[str], *, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, cwd=cwd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)


def git_lines(args: list[str], *, cwd: Path) -> list[str]:
    proc = run_cmd(args, cwd=cwd)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or f"{' '.join(args)} failed")
    return [line.strip() for line in proc.stdout.splitlines() if line.strip()]


def git_changed_files(repo: Path) -> list[str]:
    files: list[str] = []
    files.extend(git_lines(["git", "diff", "--no-renames", "--name-only"], cwd=repo))
    files.extend(git_lines(["git", "diff", "--cached", "--no-renames", "--name-only"], cwd=repo))
    files.extend(git_lines(["git", "ls-files", "--others", "--exclude-standard"], cwd=repo))
    return sorted({f for f in files if not ignored_path(f)})


def ignored_path(path: str) -> bool:
    normalized = path.replace("\\", "/")
    return (
        normalized.startswith(".loop/")
        or "/__pycache__/" in f"/{normalized}/"
        or normalized.endswith(".pyc")
        or normalized.endswith(".pyo")
    )


def match_any(path: str, patterns: list[str]) -> bool:
    return any(fnmatch.fnmatch(path.replace("\\", "/"), pat) for pat in patterns)


def disallowed_files(files: list[str], allowed: list[str]) -> list[str]:
    return [f for f in files if not match_any(f, allowed)]


def git_complete_diff(repo: Path) -> str:
    parts: list[str] = []
    for cmd in (["git", "diff", "--no-ext-diff", "--binary"], ["git", "diff", "--cached", "--no-ext-diff", "--binary"]):
        proc = run_cmd(cmd, cwd=repo)
        if proc.stdout:
            parts.append(proc.stdout)
    for path in git_lines(["git", "ls-files", "--others", "--exclude-standard"], cwd=repo):
        if ignored_path(path):
            continue
        proc = run_cmd(["git", "diff", "--no-index", "--", "/dev/null", path], cwd=repo)
        if proc.stdout:
            parts.append(proc.stdout)
    return "\n".join(part.rstrip("\n") for part in parts if part).rstrip("\n") + "\n"


def worktree_snapshot(repo: Path) -> str:
    """Hash tracked diffs plus untracked file content, excluding .loop artifacts."""
    h = hashlib.sha256()
    for cmd in (["git", "diff", "--no-ext-diff", "--binary"], ["git", "diff", "--cached", "--no-ext-diff", "--binary"]):
        proc = run_cmd(cmd, cwd=repo)
        h.update((" ".join(cmd) + "\0").encode())
        h.update(proc.stdout.encode())
        h.update(proc.stderr.encode())
    status = run_cmd(["git", "status", "--porcelain=v1", "--untracked-files=all"], cwd=repo)
    filtered_status = "\n".join(
        line for line in status.stdout.splitlines() if not ignored_path(line[3:])
    )
    h.update(b"git status --porcelain=v1 --untracked-files=all\0")
    h.update(filtered_status.encode())
    h.update(status.stderr.encode())
    for path in git_lines(["git", "ls-files", "--others", "--exclude-standard"], cwd=repo):
        if ignored_path(path):
            continue
        p = repo / path
        if p.is_file():
            h.update(path.encode())
            h.update(b"\0")
            h.update(p.read_bytes())
    return h.hexdigest()


def slug(text: str) -> str:
    value = re.sub(r"[^a-zA-Z0-9]+", "-", text.strip().lower()).strip("-")
    return (value or "loop")[:48]


def make_run_dir(repo: Path, run_root: str, objective: str) -> Path:
    root = repo / run_root
    root.mkdir(parents=True, exist_ok=True)
    base = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime()) + "-" + slug(objective)
    candidate = root / base
    idx = 2
    while candidate.exists():
        candidate = root / f"{base}-{idx}"
        idx += 1
    candidate.mkdir(parents=True)
    return candidate


def rel(path: Path, repo: Path) -> str:
    return path.relative_to(repo).as_posix()


def assert_artifact_path(path: Path, run_dir: Path) -> None:
    target = Path(os.path.abspath(path))
    root = Path(os.path.abspath(run_dir))
    try:
        common = os.path.commonpath([target, root])
    except ValueError as exc:
        raise ArtifactWriteError(f"artifact path is outside run dir: {path}") from exc
    if common != str(root):
        raise ArtifactWriteError(f"artifact path is outside run dir: {path}")
    current = target.parent
    parents: list[Path] = []
    while current != root:
        parents.append(current)
        if current == current.parent:
            raise ArtifactWriteError(f"artifact path is outside run dir: {path}")
        current = current.parent
    for parent in reversed(parents):
        if parent.is_symlink():
            raise ArtifactWriteError(f"artifact parent is a symlink: {parent}")


def safe_write_artifact(path: Path, data: str, *, run_dir: Path) -> None:
    assert_artifact_path(path, run_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.parent.is_symlink():
        raise ArtifactWriteError(f"artifact parent is a symlink: {path.parent}")
    tmp = path.with_name(f".{path.name}.tmp-{os.getpid()}-{time.time_ns()}")
    try:
        with tmp.open("x", encoding="utf-8") as handle:
            handle.write(data)
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            tmp.unlink()


def expand_cmd_template(cmd: str | list[str], *, config_dir: Path) -> str | list[str]:
    skill_dir = config_dir.parent
    mapping = {
        "python": sys.executable,
        "config_dir": config_dir.as_posix(),
        "skill_dir": skill_dir.as_posix(),
    }
    if isinstance(cmd, str):
        quoted = {key: shlex.quote(value) for key, value in mapping.items()}
        return cmd.format(**quoted)
    return [part.format(**mapping) for part in cmd]


def load_agent_config(path: Path) -> dict[str, AgentConfig]:
    path = path.resolve()
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    out: dict[str, AgentConfig] = {}
    for name in ("explorer", "coder", "code-reviewer"):
        block = data.get(name)
        if not isinstance(block, dict):
            raise ValueError(f"missing [{name}] in {path}")
        cmd = block.get("cmd")
        if not isinstance(cmd, (str, list)):
            raise ValueError(f"[{name}].cmd must be string or array")
        if isinstance(cmd, list) and not all(isinstance(x, str) for x in cmd):
            raise ValueError(f"[{name}].cmd array entries must be strings")
        writes = bool(block.get("writes", False))
        timeout = int(block.get("timeout_seconds", 300))
        out[name] = AgentConfig(
            name=name,
            cmd=expand_cmd_template(cmd, config_dir=path.parent),
            writes=writes,
            timeout_seconds=timeout,
        )
    if out["explorer"].writes:
        raise ValueError("explorer must be read-only")
    if not out["coder"].writes:
        raise ValueError("coder must be write-capable")
    if out["code-reviewer"].writes:
        raise ValueError("code-reviewer must be read-only")
    return out


def parse_json_or_none(text: str) -> Any | None:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def reviewer_findings(value: Any) -> list[str] | None:
    if value is None:
        return []
    if not isinstance(value, list):
        return None
    if not all(isinstance(item, str) for item in value):
        return None
    return value


def timeout_output(value: str | bytes | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode(errors="replace")
    return value


def agent_env(env_extra: dict[str, str]) -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if not k.startswith("LOOP_")}
    for key in INTENTIONAL_LOOP_ENV:
        if key in os.environ:
            env[key] = os.environ[key]
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    for key in RESERVED_LOOP_ENV:
        env.pop(key, None)
    env.update(env_extra)
    for key in RESERVED_LOOP_ENV:
        env.pop(key, None)
    return env


def run_agent(
    cfg: AgentConfig,
    *,
    repo: Path,
    prompt: str,
    out_dir: Path,
    prefix: str,
    env_extra: dict[str, str],
    run_dir: Path,
) -> tuple[int, Any | None]:
    out_dir.mkdir(parents=True, exist_ok=True)
    safe_write_artifact(out_dir / f"{prefix}-prompt.md", prompt, run_dir=run_dir)
    env = agent_env(env_extra)
    try:
        if isinstance(cfg.cmd, str):
            proc = subprocess.Popen(
                cfg.cmd,
                cwd=repo,
                text=True,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                shell=True,
                env=env,
                start_new_session=True,
            )
        else:
            proc = subprocess.Popen(
                cfg.cmd,
                cwd=repo,
                text=True,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                shell=False,
                env=env,
                start_new_session=True,
            )
        stdout, stderr = proc.communicate(prompt, timeout=cfg.timeout_seconds)
        returncode = proc.returncode
    except OSError as exc:
        stdout = ""
        stderr = f"AGENT_START_FAILED: {cfg.name}: {exc}\n"
        returncode = 127
    except subprocess.TimeoutExpired as exc:
        try:
            os.killpg(proc.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        except PermissionError:
            proc.terminate()
        try:
            stdout_after, stderr_after = proc.communicate(timeout=2)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            except PermissionError:
                proc.kill()
            stdout_after, stderr_after = proc.communicate()
        stdout = timeout_output(stdout_after) or timeout_output(exc.stdout)
        stderr = timeout_output(stderr_after) or timeout_output(exc.stderr)
        stderr += f"\nTIMEOUT: {cfg.name} exceeded {cfg.timeout_seconds} seconds\n"
        returncode = TIMEOUT_RETURNCODE
    safe_write_artifact(out_dir / f"{prefix}-stdout.txt", stdout, run_dir=run_dir)
    safe_write_artifact(out_dir / f"{prefix}-stderr.txt", stderr, run_dir=run_dir)
    parsed = parse_json_or_none(stdout.strip())
    if parsed is not None:
        safe_write_artifact(
            out_dir / f"{prefix}-result.json",
            json.dumps(parsed, indent=2) + "\n",
            run_dir=run_dir,
        )
    return returncode, parsed


def terminate_process_group(proc: subprocess.Popen[str]) -> None:
    try:
        os.killpg(proc.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    except PermissionError:
        proc.terminate()
    try:
        proc.communicate(timeout=2)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            return
        except PermissionError:
            proc.kill()
        proc.communicate()


def run_check(command: str, *, repo: Path, out_dir: Path, index: int, run_dir: Path, timeout_seconds: int) -> dict[str, Any]:
    env = agent_env({})
    timed_out = False
    try:
        proc = subprocess.Popen(
            command,
            cwd=repo,
            env=env,
            text=True,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            shell=True,
            start_new_session=True,
        )
        stdout, stderr = proc.communicate(timeout=timeout_seconds)
        returncode = proc.returncode
    except subprocess.TimeoutExpired as exc:
        stdout = timeout_output(exc.stdout)
        stderr = timeout_output(exc.stderr)
        stderr += f"\nTIMEOUT: check exceeded {timeout_seconds} seconds\n"
        timed_out = True
        terminate_process_group(proc)
        returncode = CHECK_TIMEOUT_RETURNCODE
    except OSError as exc:
        stdout = ""
        stderr = f"CHECK_START_FAILED: {exc}\n"
        returncode = 127
    checks_dir = out_dir / "checks"
    checks_dir.mkdir(parents=True, exist_ok=True)
    stem = f"{index:02d}"
    stdout_path = checks_dir / f"{stem}.stdout"
    stderr_path = checks_dir / f"{stem}.stderr"
    safe_write_artifact(stdout_path, stdout, run_dir=run_dir)
    safe_write_artifact(stderr_path, stderr, run_dir=run_dir)
    return {
        "command": command,
        "returncode": returncode,
        "stdout": stdout_path.as_posix(),
        "stderr": stderr_path.as_posix(),
        "stdout_excerpt": stdout[:2000],
        "stderr_excerpt": stderr[:2000],
        "timed_out": timed_out,
    }


def write_receipt(path: Path, receipt: dict[str, Any], *, run_dir: Path) -> None:
    safe_write_artifact(path, json.dumps(receipt, indent=2, sort_keys=True) + "\n", run_dir=run_dir)


def public_check_results(checks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "command": item.get("command", ""),
            "returncode": item.get("returncode"),
            "stdout_excerpt": item.get("stdout_excerpt", ""),
            "stderr_excerpt": item.get("stderr_excerpt", ""),
        }
        for item in checks
    ]


def final_receipt(
    *,
    run_id: str,
    objective: str,
    final_verdict: str,
    stop_reason: str,
    attempts_used: int,
    max_attempts: int,
    allowed_globs: list[str],
    changed_files: list[str],
    checks: list[dict[str, Any]],
    reviewer: dict[str, Any],
    run_dir: Path,
    repo: Path,
    final_diff: Path | None,
) -> dict[str, Any]:
    return {
        "schema": FINAL_SCHEMA,
        "run_id": run_id,
        "objective": objective,
        "final_verdict": final_verdict,
        "stop_reason": stop_reason,
        "attempts_used": attempts_used,
        "max_attempts": max_attempts,
        "allowed_globs": allowed_globs,
        "changed_files": changed_files,
        "checks": checks,
        "reviewer": reviewer,
        "artifacts": {
            "run_dir": rel(run_dir, repo),
            "final_diff": rel(final_diff, repo) if final_diff else "",
        },
    }


def disallowed_reviewer(findings: list[str], violations: list[str]) -> dict[str, Any]:
    return {
        "verdict": "BLOCKED",
        "edited_files": False,
        "findings": [f"disallowed file: {p}" for p in violations] + findings,
    }


def rewrite_final_diff(path: Path | None, repo: Path, run_dir: Path) -> None:
    if path is not None:
        safe_write_artifact(path, git_complete_diff(repo), run_dir=run_dir)


def build_prompt(objective: str, allowed: list[str], checks: list[str], extra: dict[str, Any]) -> str:
    return json.dumps(
        {
            "objective": objective,
            "allowed_globs": allowed,
            "checks": checks,
            **extra,
        },
        indent=2,
        sort_keys=True,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Run one bounded $loop executable harness.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--objective")
    group.add_argument("--objective-file")
    parser.add_argument("--agent-config", required=True)
    parser.add_argument("--allow", action="append", default=[], required=True)
    parser.add_argument("--check", action="append", default=[])
    parser.add_argument("--max-attempts", type=int, default=3)
    parser.add_argument("--check-timeout", type=int, default=300)
    parser.add_argument("--run-root", default=".loop/runs")
    parser.add_argument("--require-clean", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--print-json", action="store_true")
    args = parser.parse_args()

    repo = Path.cwd()
    objective = args.objective if args.objective is not None else Path(args.objective_file).read_text(encoding="utf-8").strip()
    if not objective:
        print("ERROR: objective must not be empty", file=sys.stderr)
        return 2
    if args.max_attempts < 1:
        print("ERROR: --max-attempts must be >= 1", file=sys.stderr)
        return 2
    if args.check_timeout < 1:
        print("ERROR: --check-timeout must be >= 1", file=sys.stderr)
        return 2
    agents = load_agent_config(repo / args.agent_config)
    if args.require_clean and git_changed_files(repo):
        print("ERROR: working tree is not clean before loop run", file=sys.stderr)
        return 2

    run_dir = make_run_dir(repo, args.run_root, objective)
    run_id = run_dir.name
    safe_write_artifact(
        run_dir / "request.json",
        json.dumps(
            {
                "objective": objective,
                "agent_config": args.agent_config,
                "allowed_globs": args.allow,
                "checks": args.check,
                "max_attempts": args.max_attempts,
                "check_timeout": args.check_timeout,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        run_dir=run_dir,
    )
    safe_write_artifact(run_dir / "objective.md", objective + "\n", run_dir=run_dir)

    def finish(
        final_verdict: str,
        stop_reason: str,
        attempt: int,
        checks: list[dict[str, Any]],
        reviewer: dict[str, Any],
        final_diff: Path | None,
    ) -> int:
        changed = git_changed_files(repo)
        violations = disallowed_files(changed, args.allow)
        terminal_verdict = final_verdict
        terminal_reason = stop_reason
        terminal_reviewer = {
            "verdict": reviewer.get("verdict", terminal_verdict),
            "edited_files": bool(reviewer.get("edited_files", False)),
            "findings": list(reviewer.get("findings") or []),
        }
        if violations:
            terminal_verdict = "BLOCKED"
            terminal_reason = "DISALLOWED_FILE_CHANGE"
            terminal_reviewer = disallowed_reviewer(terminal_reviewer["findings"], violations)
        if final_diff is not None:
            rewrite_final_diff(final_diff, repo, run_dir)
        receipt = final_receipt(
            run_id=run_id,
            objective=objective,
            final_verdict=terminal_verdict,
            stop_reason=terminal_reason,
            attempts_used=attempt,
            max_attempts=args.max_attempts,
            allowed_globs=args.allow,
            changed_files=changed,
            checks=checks,
            reviewer=terminal_reviewer,
            run_dir=run_dir,
            repo=repo,
            final_diff=final_diff,
        )
        write_receipt(run_dir / "final-receipt.json", receipt, run_dir=run_dir)
        print(json.dumps(receipt if args.print_json else {"final_verdict": terminal_verdict, "run_dir": rel(run_dir, repo)}, indent=2))
        return 0 if terminal_verdict == "PASS" else 1

    explorer_dir = run_dir / "explorer"
    before_explorer = worktree_snapshot(repo)
    try:
        explorer_code, explorer_result = run_agent(
            agents["explorer"],
            repo=repo,
            prompt=build_prompt(objective, args.allow, args.check, {"role": "explorer"}),
            out_dir=explorer_dir,
            prefix="explorer",
            env_extra={"LOOP_ROLE": "explorer", "LOOP_REPO": str(repo)},
            run_dir=run_dir,
        )
    except ArtifactWriteError as exc:
        return finish(
            "BLOCKED",
            "AGENT_FAILED",
            0,
            checks=[],
            reviewer={"verdict": "BLOCKED", "edited_files": False, "findings": [f"artifact write failed: {exc}"]},
            final_diff=None,
        )
    after_explorer = worktree_snapshot(repo)
    explorer_edited = before_explorer != after_explorer
    if explorer_code != 0 or explorer_edited:
        findings: list[str] = []
        if explorer_code == TIMEOUT_RETURNCODE:
            reason = "TIMEOUT"
        else:
            reason = "AGENT_FAILED"
        if explorer_code == TIMEOUT_RETURNCODE:
            findings.append("explorer timed out")
        elif explorer_code == 127:
            findings.append("explorer start failed")
        elif explorer_code != 0:
            findings.append("explorer failed")
        if explorer_edited:
            findings.append("explorer edited files")
        return finish(
            "BLOCKED",
            reason,
            0,
            checks=[],
            reviewer={"verdict": "BLOCKED", "edited_files": False, "findings": findings},
            final_diff=None,
        )

    previous_findings: list[str] = []
    latest_checks: list[dict[str, Any]] = []
    latest_diff: Path | None = None
    latest_reviewer: dict[str, Any] = {"verdict": "BLOCKED", "edited_files": False, "findings": []}

    for attempt in range(1, args.max_attempts + 1):
        attempt_dir = run_dir / "attempts" / f"{attempt:02d}"
        attempt_dir.mkdir(parents=True)
        coder_prompt = build_prompt(
            objective,
            args.allow,
            args.check,
            {
                "role": "coder",
                "attempt": attempt,
                "explorer_result": explorer_result,
                "previous_findings": previous_findings,
            },
        )
        try:
            coder_code, _coder_result = run_agent(
                agents["coder"],
                repo=repo,
                prompt=coder_prompt,
                out_dir=attempt_dir,
                prefix="coder",
                env_extra={
                    "LOOP_ROLE": "coder",
                    "LOOP_ATTEMPT": str(attempt),
                    "LOOP_REPO": str(repo),
                },
                run_dir=run_dir,
            )
        except ArtifactWriteError as exc:
            return finish(
                "BLOCKED",
                "AGENT_FAILED",
                attempt,
                checks=[],
                reviewer={"verdict": "BLOCKED", "edited_files": False, "findings": [f"artifact write failed: {exc}"]},
                final_diff=None,
            )
        changed = git_changed_files(repo)
        safe_write_artifact(
            attempt_dir / "changed-files.txt",
            "\n".join(changed) + ("\n" if changed else ""),
            run_dir=run_dir,
        )
        violations = disallowed_files(changed, args.allow)
        if coder_code != 0 or violations:
            if violations:
                reason = "DISALLOWED_FILE_CHANGE"
                findings = []
                if coder_code == TIMEOUT_RETURNCODE:
                    findings.append("coder timed out")
                elif coder_code == 127:
                    findings.append("coder start failed")
                elif coder_code != 0:
                    findings.append("coder failed")
            elif coder_code == TIMEOUT_RETURNCODE:
                reason = "TIMEOUT"
                findings = ["coder timed out"]
            elif coder_code == 127:
                reason = "AGENT_FAILED"
                findings = ["coder start failed"]
            else:
                reason = "AGENT_FAILED"
                findings = ["coder failed"]
            return finish(
                "BLOCKED",
                reason,
                attempt,
                checks=[],
                reviewer={"verdict": "BLOCKED", "edited_files": False, "findings": findings},
                final_diff=None,
            )

        latest_checks = [
            run_check(command, repo=repo, out_dir=attempt_dir, index=i, run_dir=run_dir, timeout_seconds=args.check_timeout)
            for i, command in enumerate(args.check, start=1)
        ]
        safe_write_artifact(attempt_dir / "checks.json", json.dumps(latest_checks, indent=2) + "\n", run_dir=run_dir)
        latest_diff = attempt_dir / "diff.patch"
        safe_write_artifact(latest_diff, git_complete_diff(repo), run_dir=run_dir)
        if any(item.get("timed_out") for item in latest_checks):
            return finish(
                "BLOCKED",
                "TIMEOUT",
                attempt,
                checks=latest_checks,
                reviewer={
                    "verdict": "BLOCKED",
                    "edited_files": False,
                    "findings": ["deterministic check timed out"],
                },
                final_diff=latest_diff,
            )
        changed = git_changed_files(repo)
        violations = disallowed_files(changed, args.allow)
        if violations:
            return finish(
                "BLOCKED",
                "DISALLOWED_FILE_CHANGE",
                attempt,
                checks=latest_checks,
                reviewer={
                    "verdict": "BLOCKED",
                    "edited_files": False,
                    "findings": [],
                },
                final_diff=latest_diff,
            )

        before_review = worktree_snapshot(repo)
        diff_text = git_complete_diff(repo)
        reviewer_prompt = build_prompt(
            objective,
            args.allow,
            args.check,
            {
                "role": "code-reviewer",
                "attempt": attempt,
                "changed_files": changed,
                "diff_text": diff_text,
                "check_results": public_check_results(latest_checks),
            },
        )
        try:
            reviewer_code, reviewer_result = run_agent(
                agents["code-reviewer"],
                repo=repo,
                prompt=reviewer_prompt,
                out_dir=attempt_dir,
                prefix="code-reviewer",
                env_extra={
                    "LOOP_ROLE": "code-reviewer",
                    "LOOP_ATTEMPT": str(attempt),
                    "LOOP_REPO": str(repo),
                },
                run_dir=run_dir,
            )
        except ArtifactWriteError as exc:
            return finish(
                "BLOCKED",
                "AGENT_FAILED",
                attempt,
                checks=latest_checks,
                reviewer={"verdict": "BLOCKED", "edited_files": False, "findings": [f"artifact write failed: {exc}"]},
                final_diff=latest_diff,
            )
        after_review = worktree_snapshot(repo)
        rewrite_final_diff(latest_diff, repo, run_dir)
        reviewer_edited = before_review != after_review
        checks_passed = bool(latest_checks) and all(item["returncode"] == 0 for item in latest_checks)

        findings = reviewer_findings(reviewer_result.get("findings") if isinstance(reviewer_result, dict) else None)
        if reviewer_code != 0:
            latest_reviewer = {
                "verdict": "BLOCKED",
                "edited_files": reviewer_edited,
                "findings": [
                    "code-reviewer timed out"
                    if reviewer_code == TIMEOUT_RETURNCODE
                    else "code-reviewer start failed"
                    if reviewer_code == 127
                    else "code-reviewer failed"
                ],
            }
            stop_reason = "TIMEOUT" if reviewer_code == TIMEOUT_RETURNCODE else "AGENT_FAILED"
        elif reviewer_edited:
            latest_reviewer = {"verdict": "BLOCKED", "edited_files": True, "findings": ["code-reviewer edited files"]}
            stop_reason = "REVIEWER_EDITED_FILES"
        elif not isinstance(reviewer_result, dict) or reviewer_result.get("verdict") not in VERDICTS or findings is None:
            latest_reviewer = {"verdict": "BLOCKED", "edited_files": False, "findings": ["invalid code-reviewer JSON"]}
            stop_reason = "INVALID_REVIEWER_OUTPUT"
        else:
            latest_reviewer = {
                "verdict": reviewer_result["verdict"],
                "edited_files": False,
                "findings": findings,
            }
            stop_reason = ""

        if stop_reason:
            return finish(
                "BLOCKED",
                stop_reason,
                attempt,
                checks=latest_checks,
                reviewer=latest_reviewer,
                final_diff=latest_diff,
            )

        if checks_passed and latest_reviewer["verdict"] == "PASS":
            return finish(
                "PASS",
                STOP_CODE_REVIEWER_PASS,
                attempt,
                checks=latest_checks,
                reviewer=latest_reviewer,
                final_diff=latest_diff,
            )

        if latest_reviewer["verdict"] == "BLOCKED":
            return finish(
                "BLOCKED",
                "CODE_REVIEWER_BLOCKED",
                attempt,
                checks=latest_checks,
                reviewer=latest_reviewer,
                final_diff=latest_diff,
            )

        previous_findings = list(latest_reviewer.get("findings") or [])
        if not checks_passed:
            previous_findings.append("deterministic checks failed")

    return finish(
        "NEEDS_CHANGES",
        "MAX_ATTEMPTS",
        args.max_attempts,
        checks=latest_checks,
        reviewer=latest_reviewer,
        final_diff=latest_diff,
    )


if __name__ == "__main__":
    raise SystemExit(main())
