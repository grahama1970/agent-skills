"""Provider registry and runner implementations for review-assurance-case."""
from __future__ import annotations
# --- dotenv (MUST be before any os.getenv / os.environ) ---
import sys
from pathlib import Path as _Path

def _resolve_skills_dir() -> _Path:
    p = _Path(__file__).resolve()
    for parent in [p, *p.parents]:
        if parent.name == "skills":
            return parent
    return p.parents[1]

_SKILLS_DIR = _resolve_skills_dir()
if str(_SKILLS_DIR) not in sys.path:
    sys.path.insert(0, str(_SKILLS_DIR))

try:
    from dotenv_helper import load_env as _load_env
except Exception:
    def _load_env() -> None:
        return

_load_env()


import asyncio
import os
import shutil
import sys
from pathlib import Path
from typing import Optional

# Handle both import modes
try:
    from ..config import PROVIDERS
except ImportError:
    from config import PROVIDERS


def find_provider_cli(provider: str) -> Optional[str]:
    """Find CLI executable for the given provider."""
    if provider not in PROVIDERS:
        return None
    return shutil.which(PROVIDERS[provider]["cli"])


def get_provider_model(provider: str, model: Optional[str] = None) -> str:
    """Get the actual model ID for a provider, resolving aliases."""
    cfg = PROVIDERS.get(provider)
    if not cfg:
        raise ValueError(f"Unknown provider: {provider}")
    if model is None:
        model = cfg["default_model"]
    return cfg["models"].get(model, model)


def build_provider_cmd(
    provider: str,
    model: str,
    add_dirs: Optional[list[str]] = None,
    continue_session: bool = False,
    reasoning: Optional[str] = None,
) -> list[str]:
    """Build command args for a given provider."""
    cfg = PROVIDERS[provider]
    cli = cfg["cli"]
    actual_model = get_provider_model(provider, model)
    effective_reasoning = reasoning or cfg.get("default_reasoning")

    if provider == "github":
        cmd = [cli]
        if continue_session:
            cmd.append("--continue")
        cmd.extend(["--allow-all-tools", "--allow-all-paths", "--model", actual_model, "--no-color"])
        if add_dirs:
            for d in add_dirs:
                cmd.extend(["--add-dir", d])

    elif provider == "anthropic":
        cmd = [cli, "--print"]
        if continue_session:
            cmd.append("--continue")
        cmd.extend(["--model", actual_model])
        if add_dirs:
            for d in add_dirs:
                cmd.extend(["--add-dir", d])

    elif provider == "openai":
        cmd = [cli, "exec", "--model", actual_model]
        if effective_reasoning:
            cmd.extend(["-c", f'reasoning_effort="{effective_reasoning}"'])
        if add_dirs:
            for d in add_dirs:
                cmd.extend(["--add-dir", d])

    elif provider == "google":
        cmd = [cli, "-m", actual_model, "--yolo"]
        if add_dirs:
            cmd.extend(["--include-directories", ",".join(add_dirs)])

    else:
        raise ValueError(f"Unknown provider: {provider}")

    return cmd


async def run_provider_async(
    prompt: str,
    model: str,
    add_dirs: Optional[list[str]] = None,
    log_file: Optional[Path] = None,
    continue_session: bool = False,
    provider: str = "github",
    step_name: str = "Processing",
    reasoning: Optional[str] = None,
) -> tuple[str, int]:
    """Run provider CLI with real-time output streaming.

    Returns: (output, return_code)
    """
    if provider not in PROVIDERS:
        return f"Unknown provider: {provider}", 1

    cli_path = find_provider_cli(provider)
    if not cli_path:
        return f"{PROVIDERS[provider]['cli']} CLI not found for provider {provider}", 1

    cmd = build_provider_cmd(provider, model, add_dirs, continue_session, reasoning)
    cmd[0] = str(cli_path)

    env = {**os.environ, **PROVIDERS[provider].get("env", {}), "PYTHONUNBUFFERED": "1"}

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            env=env,
        )
    except (FileNotFoundError, PermissionError, OSError) as e:
        return f"Failed to start provider CLI: {e}", 1

    # Send prompt via stdin
    try:
        proc.stdin.write(prompt.encode())
        await proc.stdin.drain()
        proc.stdin.close()
        await proc.stdin.wait_closed()
    except (BrokenPipeError, ConnectionResetError) as e:
        sys.stderr.write(f"Warning: stdin closed early: {e}\n")

    output_lines = []
    log_handle = open(log_file, "w", buffering=1) if log_file else None
    line_count = 0

    try:
        sys.stderr.write(f"[review-assurance-case] {step_name} started...\n")
        async for line in proc.stdout:
            text = line.decode(errors="replace")
            output_lines.append(text)
            line_count += 1
            if log_handle:
                log_handle.write(text)
                log_handle.flush()
            if line_count % 50 == 0:
                sys.stderr.write(f"\r[review-assurance-case] {step_name}: {line_count} lines...")
                sys.stderr.flush()
    except asyncio.CancelledError:
        proc.kill()
        await proc.wait()
        raise
    finally:
        if log_handle:
            log_handle.close()

    await proc.wait()
    sys.stderr.write(f"\r[review-assurance-case] {step_name}: Complete ({line_count} lines)\n")

    return "".join(output_lines), proc.returncode


__all__ = [
    "build_provider_cmd",
    "find_provider_cli",
    "get_provider_model",
    "run_provider_async",
]
