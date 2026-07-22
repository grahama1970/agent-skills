"""Clone and constrained entry-point execution for GitHub repository evaluation."""
from __future__ import annotations

import json
import os
import re
import shlex
import shutil
import signal
import subprocess
import time
import tomllib
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

try:
    import resource
except ImportError:  # pragma: no cover - the skill targets Linux, but imports stay portable.
    resource = None  # type: ignore

from config import (
    DEFAULT_CLONE_TIMEOUT,
    DEFAULT_OUTPUT_LIMIT,
    DEFAULT_RUN_MEMORY_MB,
    DEFAULT_RUN_TIMEOUT,
)

_REPO_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
_RUNTIME_PATH = "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
_PYTHON_SCRIPT_RUNNER = """import importlib, sys
target = sys.argv[1]
name = sys.argv[2]
module_name, separator, attrs = target.partition(':')
obj = importlib.import_module(module_name)
if not separator:
    raise SystemExit(0)
for part in attrs.split('.'):
    obj = getattr(obj, part)
sys.argv = [name, '--help']
value = obj()
raise SystemExit(value if isinstance(value, int) else 0)
"""


def _slug(repo: str) -> str:
    return repo.replace("/", "__")


def _clip(text: str, limit: int = 4000) -> str:
    text = text or ""
    return text if len(text) <= limit else text[:limit] + "\n...[truncated]"


def clone_repository(
    candidate: Dict[str, Any],
    workspace: Path,
    timeout: int = DEFAULT_CLONE_TIMEOUT,
) -> Dict[str, Any]:
    """Clone one validated public repository beneath the evaluation workspace."""
    repo = str(candidate.get("repo") or "")
    if not _REPO_RE.fullmatch(repo):
        return {"status": "failed", "error": f"Unsafe repository name: {repo!r}"}
    target = workspace / "clones" / _slug(repo)
    target.parent.mkdir(parents=True, exist_ok=True)
    url = str(candidate.get("url") or f"https://github.com/{repo}.git")
    commands = [
        ["git", "clone", "--depth", "1", "--single-branch", "--no-tags", "--filter=blob:none", url, str(target)],
        ["git", "clone", "--depth", "1", "--single-branch", "--no-tags", url, str(target)],
    ]
    last_error = ""
    for index, command in enumerate(commands):
        if target.exists():
            shutil.rmtree(target, ignore_errors=True)
        try:
            completed = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=max(10, timeout),
                env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            last_error = str(exc)
            continue
        if completed.returncode == 0:
            return {
                "status": "passed",
                "path": str(target),
                "command": command,
                "filter_fallback": index == 1,
                "stderr": _clip(completed.stderr),
            }
        last_error = completed.stderr or completed.stdout
    return {"status": "failed", "path": str(target), "error": _clip(last_error)}


def _load_toml(path: Path) -> Dict[str, Any]:
    try:
        return tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, tomllib.TOMLDecodeError):
        return {}


def _safe_relative(repo_path: Path, value: str) -> Optional[str]:
    candidate = (repo_path / value).resolve(strict=False)
    try:
        candidate.relative_to(repo_path.resolve())
    except ValueError:
        return None
    return str(candidate.relative_to(repo_path.resolve()))


def detect_entrypoint(repo_path: Path, override: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Detect a conventional executable entry point without installing dependencies."""
    if override:
        command = shlex.split(override)
        return {"command": command, "source": "user override", "python_paths": [".", "src"]} if command else None

    pyproject = repo_path / "pyproject.toml"
    if pyproject.exists():
        data = _load_toml(pyproject)
        script_tables = [
            data.get("project", {}).get("scripts", {}),
            data.get("tool", {}).get("poetry", {}).get("scripts", {}),
        ]
        for scripts in script_tables:
            if isinstance(scripts, dict):
                for name, target in sorted(scripts.items()):
                    if isinstance(target, str) and target.strip():
                        target = target.split("[", 1)[0].strip()
                        return {
                            "command": ["python3", "-c", _PYTHON_SCRIPT_RUNNER, target, name],
                            "source": f"pyproject script: {name}",
                            "python_paths": [".", "src"],
                        }

    for base_name in (".", "src"):
        base = repo_path if base_name == "." else repo_path / base_name
        if not base.is_dir():
            continue
        for main_file in sorted(base.glob("*/__main__.py")):
            package = main_file.parent.name
            if package.isidentifier():
                return {
                    "command": ["python3", "-m", package, "--help"],
                    "source": f"Python module: {package}",
                    "python_paths": [base_name],
                }

    for filename in ("main.py", "cli.py", "app.py"):
        if (repo_path / filename).is_file():
            return {
                "command": ["python3", filename, "--help"],
                "source": filename,
                "python_paths": [".", "src"],
            }

    package_json = repo_path / "package.json"
    if package_json.exists():
        try:
            package = json.loads(package_json.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            package = {}
        binaries = package.get("bin")
        if isinstance(binaries, str):
            safe_path = _safe_relative(repo_path, binaries)
            if safe_path and (repo_path / safe_path).is_file():
                return {"command": ["node", safe_path, "--help"], "source": "package.json bin"}
        elif isinstance(binaries, dict):
            for name, value in sorted(binaries.items()):
                if isinstance(value, str):
                    safe_path = _safe_relative(repo_path, value)
                    if safe_path and (repo_path / safe_path).is_file():
                        return {"command": ["node", safe_path, "--help"], "source": f"package.json bin: {name}"}
        scripts = package.get("scripts") or {}
        for name in ("start", "cli", "demo"):
            if isinstance(scripts, dict) and scripts.get(name):
                return {"command": ["npm", "run", "--silent", name, "--", "--help"], "source": f"npm script: {name}"}

    if (repo_path / "Cargo.toml").exists():
        return {"command": ["cargo", "run", "--quiet", "--", "--help"], "source": "Cargo.toml"}
    if (repo_path / "go.mod").exists():
        return {"command": ["go", "run", ".", "--help"], "source": "go.mod"}
    if (repo_path / "run.sh").is_file():
        return {"command": ["bash", "run.sh", "--help"], "source": "run.sh"}
    bin_dir = repo_path / "bin"
    if bin_dir.is_dir():
        for path in sorted(bin_dir.iterdir()):
            if path.is_file() and os.access(path, os.X_OK):
                return {"command": [str(Path("bin") / path.name), "--help"], "source": f"executable: bin/{path.name}"}
    return None


def _execution_copy(source: Path, workspace: Path) -> Tuple[Path, List[str]]:
    target = workspace / "run" / source.name
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(source, target, symlinks=True, ignore=shutil.ignore_patterns(".git"))
    removed: List[str] = []
    root = target.resolve()
    for path in target.rglob("*"):
        if not path.is_symlink():
            continue
        try:
            path.resolve(strict=False).relative_to(root)
        except (OSError, ValueError):
            removed.append(str(path.relative_to(target)))
            path.unlink(missing_ok=True)
    return target, removed


def _resource_limits(timeout: int, memory_mb: int):
    def apply() -> None:
        if resource is None:
            return
        limits = [
            (resource.RLIMIT_CPU, max(2, timeout + 1)),
            (resource.RLIMIT_AS, max(256, memory_mb) * 1024 * 1024),
            (resource.RLIMIT_FSIZE, 10 * 1024 * 1024),
            (resource.RLIMIT_NOFILE, 128),
        ]
        if hasattr(resource, "RLIMIT_NPROC"):
            limits.append((resource.RLIMIT_NPROC, 64))
        for kind, value in limits:
            try:
                _, current_hard = resource.getrlimit(kind)
                hard = value if current_hard == resource.RLIM_INFINITY else min(value, current_hard)
                resource.setrlimit(kind, (min(value, hard), hard))
            except (OSError, ValueError):
                pass
    return apply


def _environment(run_path: Path, python_paths: Sequence[str], *, sandboxed: bool, allow_network: bool) -> Dict[str, str]:
    base = Path("/var/tmp/github-search-workspace") if sandboxed else run_path
    home = Path("/var/tmp/github-search-home") if sandboxed else run_path / ".sandbox-home"
    temp = Path("/tmp") if sandboxed else run_path / ".sandbox-tmp"
    if not sandboxed:
        home.mkdir(exist_ok=True)
        temp.mkdir(exist_ok=True)
    env = {
        "PATH": _RUNTIME_PATH,
        "HOME": str(home),
        "TMPDIR": str(temp),
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "CI": "1",
        "NO_COLOR": "1",
        "PYTHONNOUSERSITE": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONPATH": os.pathsep.join(str(base / item) for item in python_paths),
        "GIT_TERMINAL_PROMPT": "0",
        "PIP_DISABLE_PIP_VERSION_CHECK": "1",
        "npm_config_audit": "false",
        "npm_config_fund": "false",
    }
    if not allow_network:
        dead_proxy = "http://127.0.0.1:9"
        env.update({"HTTP_PROXY": dead_proxy, "HTTPS_PROXY": dead_proxy, "ALL_PROXY": dead_proxy, "NO_PROXY": ""})
    return env


def _bwrap_command(command: Sequence[str], run_path: Path, allow_network: bool) -> List[str]:
    args = [
        "bwrap", "--die-with-parent", "--new-session", "--unshare-pid", "--unshare-ipc",
        "--unshare-uts", "--ro-bind", "/", "/", "--tmpfs", "/var/tmp",
        "--dir", "/var/tmp/github-search-workspace", "--bind", str(run_path),
        "/var/tmp/github-search-workspace", "--dir", "/var/tmp/github-search-home",
        "--tmpfs", "/tmp", "--tmpfs", "/home", "--tmpfs", "/root",
        "--proc", "/proc", "--dev", "/dev",
    ]
    for hidden in ("/mnt", "/media", "/run"):
        if Path(hidden).exists():
            args.extend(["--tmpfs", hidden])
    if not allow_network:
        args.append("--unshare-net")
    args.extend(["--chdir", "/var/tmp/github-search-workspace", "--", *command])
    return args


def _execute_once(
    original_command: Sequence[str],
    actual_command: Sequence[str],
    run_path: Path,
    workspace: Path,
    *,
    mode: str,
    python_paths: Sequence[str],
    timeout: int,
    memory_mb: int,
    allow_network: bool,
) -> Dict[str, Any]:
    output_dir = workspace / "output"
    output_dir.mkdir(parents=True, exist_ok=True)
    stdout_path = output_dir / f"{run_path.name}-{mode}.stdout"
    stderr_path = output_dir / f"{run_path.name}-{mode}.stderr"
    started = time.monotonic()
    sandboxed = mode == "bubblewrap"
    try:
        with stdout_path.open("wb") as stdout_handle, stderr_path.open("wb") as stderr_handle:
            process = subprocess.Popen(
                list(actual_command), cwd=run_path, stdin=subprocess.DEVNULL,
                stdout=stdout_handle, stderr=stderr_handle,
                env=_environment(run_path, python_paths, sandboxed=sandboxed, allow_network=allow_network),
                start_new_session=True,
                preexec_fn=_resource_limits(timeout, memory_mb) if os.name == "posix" else None,
            )
            try:
                exit_code = process.wait(timeout=max(1, timeout))
                status = "passed" if exit_code == 0 else "failed"
            except subprocess.TimeoutExpired:
                status, exit_code = "timed_out", None
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                process.wait()
    except OSError as exc:
        return {"status": "skipped", "command": list(original_command), "sandbox": mode, "error": str(exc)}
    return {
        "status": status,
        "command": list(original_command),
        "executed_command": list(actual_command),
        "sandbox": mode,
        "allow_network": allow_network,
        "exit_code": exit_code,
        "duration_seconds": round(time.monotonic() - started, 3),
        "stdout": _clip(stdout_path.read_text(encoding="utf-8", errors="replace"), DEFAULT_OUTPUT_LIMIT),
        "stderr": _clip(stderr_path.read_text(encoding="utf-8", errors="replace"), DEFAULT_OUTPUT_LIMIT),
    }


def run_entrypoint(
    source_path: Path,
    entrypoint: Dict[str, Any],
    workspace: Path,
    *,
    timeout: int = DEFAULT_RUN_TIMEOUT,
    memory_mb: int = DEFAULT_RUN_MEMORY_MB,
    sandbox: str = "auto",
    allow_network: bool = False,
) -> Dict[str, Any]:
    """Run a detected entry point in a disposable copy with progressively weaker fallbacks."""
    if sandbox not in {"auto", "strict", "host"}:
        return {"status": "skipped", "error": f"Unknown sandbox mode: {sandbox}"}
    command = list(entrypoint.get("command") or [])
    if not command:
        return {"status": "skipped", "error": "Empty entry point command"}
    run_path, removed_symlinks = _execution_copy(source_path, workspace)
    python_paths = entrypoint.get("python_paths") or [".", "src"]
    attempts: List[Tuple[str, List[str]]] = []
    if sandbox in {"auto", "strict"} and shutil.which("bwrap"):
        attempts.append(("bubblewrap", _bwrap_command(command, run_path, allow_network)))
    elif sandbox == "strict":
        shutil.rmtree(run_path, ignore_errors=True)
        return {"status": "skipped", "error": "Strict mode requires bubblewrap (bwrap)", "sandbox": "strict"}
    if sandbox == "auto" and not allow_network and shutil.which("unshare"):
        attempts.append(("unshare-net", ["unshare", "--net", "--", *command]))
    if sandbox in {"auto", "host"}:
        attempts.append(("host-limited", command))

    final: Dict[str, Any] = {"status": "skipped", "error": "No execution mode available"}
    for mode, actual in attempts:
        final = _execute_once(
            command, actual, run_path, workspace, mode=mode, python_paths=python_paths,
            timeout=max(1, timeout), memory_mb=max(256, memory_mb), allow_network=allow_network,
        )
        wrapper_failed = (
            final.get("status") == "failed"
            and mode in {"bubblewrap", "unshare-net"}
            and str(final.get("stderr") or "").lstrip().startswith(("bwrap:", "unshare:"))
        )
        if not wrapper_failed or sandbox == "strict":
            break
    final["removed_external_symlinks"] = removed_symlinks
    if final.get("sandbox") == "host-limited":
        final["warning"] = "Filesystem and network isolation were unavailable; only env scrubbing and resource limits were applied."
    shutil.rmtree(run_path, ignore_errors=True)
    return final
