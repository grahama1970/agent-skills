"""
Docker/Compose lifecycle manager for ACE-Step service.

- Idempotently brings up the service
- Waits for /healthz
- Supports persistent service mode
"""

from __future__ import annotations

import os
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

import httpx
from loguru import logger


@dataclass(frozen=True)
class DockerConfig:
    """Configuration for the ACE-Step Docker service."""

    compose_file: Path
    base_url: str
    health_path: str = "/healthz"
    startup_timeout_s: int = 300  # 5 minutes for model loading
    project_name: str = "create-score"


def _run(cmd: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess:
    """Run a command and log it."""
    logger.info("Running: {}", " ".join(cmd))
    return subprocess.run(cmd, check=True, cwd=cwd, capture_output=True, text=True)


def is_service_running(cfg: DockerConfig) -> bool:
    """Check if the ACE-Step service is already running."""
    try:
        result = subprocess.run(
            ["docker", "compose", "-f", str(cfg.compose_file), "-p", cfg.project_name, "ps", "-q"],
            capture_output=True,
            text=True,
            check=False,
        )
        return bool(result.stdout.strip())
    except Exception:
        return False


def docker_compose_up(cfg: DockerConfig, build: bool = False) -> None:
    """Start the ACE-Step Docker service (idempotent)."""
    if is_service_running(cfg):
        logger.info("Service already running, skipping docker compose up")
        return

    cmd = ["docker", "compose", "-f", str(cfg.compose_file), "-p", cfg.project_name, "up", "-d"]
    if build:
        cmd.append("--build")

    _run(cmd, cwd=cfg.compose_file.parent)


def docker_compose_down(cfg: DockerConfig) -> None:
    """Stop the ACE-Step Docker service."""
    cmd = ["docker", "compose", "-f", str(cfg.compose_file), "-p", cfg.project_name, "down"]
    _run(cmd, cwd=cfg.compose_file.parent)


def wait_for_health(cfg: DockerConfig) -> bool:
    """Wait for the service to become healthy."""
    deadline = time.time() + cfg.startup_timeout_s
    url = cfg.base_url.rstrip("/") + cfg.health_path
    logger.info("Waiting for health: {} (timeout: {}s)", url, cfg.startup_timeout_s)

    last_err: str | None = None
    while time.time() < deadline:
        try:
            with httpx.Client(timeout=5.0) as client:
                r = client.get(url)
                if r.status_code == 200:
                    logger.info("Service healthy")
                    return True
                last_err = f"HTTP {r.status_code}: {r.text[:200]}"
        except httpx.ConnectError:
            last_err = "Connection refused (service starting...)"
        except Exception as e:
            last_err = str(e)

        logger.debug("Health check failed: {}", last_err)
        time.sleep(2)

    logger.error("Service did not become healthy. Last error: {}", last_err)
    return False


def ensure_service_running(cfg: DockerConfig, build: bool = False) -> None:
    """Ensure the service is running and healthy. Raises on failure."""
    docker_compose_up(cfg, build=build)
    if not wait_for_health(cfg):
        raise RuntimeError(
            f"ACE-Step service did not become healthy within {cfg.startup_timeout_s}s. "
            "Check Docker logs: docker compose -f docker/compose.yml logs"
        )


def make_default_config(skill_root: Path | str) -> DockerConfig:
    """Create default DockerConfig for the skill."""
    skill_root = Path(skill_root)
    port = int(os.environ.get("ACE_STEP_PORT", "8015"))
    compose_file = skill_root / "docker" / "compose.yml"

    return DockerConfig(
        compose_file=compose_file,
        base_url=f"http://localhost:{port}",
    )


def get_service_logs(cfg: DockerConfig, tail: int = 50) -> str:
    """Get recent logs from the service."""
    try:
        result = subprocess.run(
            [
                "docker", "compose", "-f", str(cfg.compose_file),
                "-p", cfg.project_name, "logs", "--tail", str(tail)
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        return result.stdout + result.stderr
    except Exception as e:
        return f"Failed to get logs: {e}"
