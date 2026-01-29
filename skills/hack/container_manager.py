"""
Docker container management for the hack skill.

This module handles:
- Building and managing the security Docker image
- Running commands in isolated containers
- Exploit environment setup and teardown
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

from rich.console import Console
from rich.table import Table

from hack.config import (
    SECURITY_IMAGE,
    SKILL_DIR,
    DOCKER_RUN_TIMEOUT,
    TOOLS_INFO,
    EXPLOIT_BASE_IMAGES,
)

console = Console()


def ensure_docker_image() -> bool:
    """
    Build the security Docker image if it doesn't exist.

    Returns:
        True if image is available, False if build failed
    """
    # Check if image exists
    result = subprocess.run(
        ["docker", "images", "-q", SECURITY_IMAGE], capture_output=True, text=True
    )

    if result.stdout.strip():
        return True  # Image exists

    # Build the image
    dockerfile = SKILL_DIR / "docker" / "Dockerfile.security"
    if not dockerfile.exists():
        console.print(f"[red]Dockerfile not found: {dockerfile}[/red]")
        return False

    console.print(
        "[cyan]Building security scanner Docker image (first time only)...[/cyan]"
    )
    build_result = subprocess.run(
        [
            "docker",
            "build",
            "-t",
            SECURITY_IMAGE,
            "-f",
            str(dockerfile),
            str(SKILL_DIR / "docker"),
        ],
        capture_output=True,
        text=True,
    )

    if build_result.returncode != 0:
        console.print(f"[red]Docker build failed:[/red]\n{build_result.stderr}")
        return False

    console.print("[green]Docker image built successfully.[/green]")
    return True


def run_in_docker(
    cmd: list[str], target_path: str | None = None, network: str = "host"
) -> subprocess.CompletedProcess:
    """
    Run a command inside the security Docker container.

    Args:
        cmd: Command and arguments to run
        target_path: Optional path to mount as /scan (read-only)
        network: Docker network mode (default: host)

    Returns:
        CompletedProcess with command results
    """
    docker_cmd = [
        "docker",
        "run",
        "--rm",
        f"--network={network}",
    ]

    # Mount target directory if specified
    if target_path:
        abs_path = Path(target_path).resolve()
        if abs_path.is_dir():
            docker_cmd.extend(["-v", f"{abs_path}:/scan:ro"])
        elif abs_path.is_file():
            docker_cmd.extend(["-v", f"{abs_path.parent}:/scan:ro"])

    docker_cmd.append(SECURITY_IMAGE)
    docker_cmd.extend(cmd)

    return subprocess.run(
        docker_cmd, capture_output=True, text=True, timeout=DOCKER_RUN_TIMEOUT
    )


def check_docker_status() -> tuple[bool, bool]:
    """
    Check Docker availability and image status.

    Returns:
        Tuple of (docker_available, image_exists)
    """
    docker_available = shutil.which("docker") is not None
    image_exists = False

    if docker_available:
        result = subprocess.run(
            ["docker", "images", "-q", SECURITY_IMAGE], capture_output=True, text=True
        )
        image_exists = bool(result.stdout.strip())

    return docker_available, image_exists


def display_tools_status():
    """Display available security tools and Docker image status."""
    docker_available, image_exists = check_docker_status()

    # Docker status
    console.print("\n[bold]Container Status:[/bold]")
    docker_status = (
        "[green]Available[/green]" if docker_available else "[red]Not Found[/red]"
    )
    image_status = (
        "[green]Built[/green]"
        if image_exists
        else "[yellow]Not Built (will build on first use)[/yellow]"
    )
    console.print(f"  Docker Engine: {docker_status}")
    console.print(f"  Security Image ({SECURITY_IMAGE}): {image_status}")

    # Tools in container
    table = Table(title="\nTools in Security Container")
    table.add_column("Tool", style="cyan")
    table.add_column("Type", style="dim")
    table.add_column("Command", style="green")
    table.add_column("Description")

    for tool, tool_type, command, desc in TOOLS_INFO:
        table.add_row(tool, tool_type, command, desc)

    console.print(table)

    console.print(
        "\n[dim]All tools run in isolated Docker containers - "
        "no local installation needed.[/dim]"
    )

    if not docker_available:
        console.print(
            "\n[bold red]Warning:[/bold red] Docker not found. "
            "Install Docker to use this skill."
        )
        console.print("  Install: https://docs.docker.com/engine/install/")


def setup_exploit_environment(
    target: str,
    env: str,
    payload: str | None = None,
    interactive: bool = False,
) -> tuple[str | None, str | None]:
    """
    Set up an isolated Docker environment for running exploits.

    Args:
        target: Target IP/hostname
        env: Environment type (python, c, ruby, node, kali)
        payload: Optional path to exploit script
        interactive: Whether to run interactively

    Returns:
        Tuple of (work_dir, error_message). work_dir is None on error.
    """
    if env not in EXPLOIT_BASE_IMAGES:
        return None, f"Unknown environment: {env}. Supported: {', '.join(EXPLOIT_BASE_IMAGES.keys())}"

    image = EXPLOIT_BASE_IMAGES[env]
    work_dir = os.path.join(os.getcwd(), f"hack_env_{env}_{os.getpid()}")
    os.makedirs(work_dir, exist_ok=True)

    # Generate Dockerfile
    dockerfile_content = f"""
FROM {image}
WORKDIR /app
RUN apt-get update && apt-get install -y iputils-ping netcat-openbsd curl wget
"""
    if env == "python":
        dockerfile_content += "RUN pip install requests scapy pwntools\n"

    # Copy payload if exists
    display_payload_name = "exploit_script"
    if payload:
        if os.path.exists(payload):
            shutil.copy(payload, os.path.join(work_dir, os.path.basename(payload)))
            dockerfile_content += f"COPY {os.path.basename(payload)} /app/\n"
            display_payload_name = os.path.basename(payload)
        else:
            console.print(
                f"[yellow]Payload {payload} not found, skipping copy.[/yellow]"
            )

    with open(os.path.join(work_dir, "Dockerfile"), "w") as f:
        f.write(dockerfile_content)

    # Generate compose file
    if interactive:
        command = "tail -f /dev/null"
    elif env == "python" and payload:
        command = f"python {display_payload_name}"
    else:
        command = 'echo "No payload provided, container ready."'

    compose_content = f"""
services:
  exploiter:
    build: .
    command: {command}
    volumes:
      - .:/app
    network_mode: host
"""
    with open(os.path.join(work_dir, "docker-compose.yml"), "w") as f:
        f.write(compose_content)

    return work_dir, None


def run_exploit(work_dir: str, interactive: bool = False):
    """
    Build and run the exploit environment.

    Args:
        work_dir: Working directory with Dockerfile and compose
        interactive: Whether to run interactively
    """
    try:
        # Build
        subprocess.run(["docker", "compose", "build"], cwd=work_dir, check=True)

        # Run
        if interactive:
            console.print("[bold]Entering interactive shell...[/bold]")
            subprocess.run(
                ["docker", "compose", "run", "--rm", "exploiter", "/bin/bash"],
                cwd=work_dir,
            )
        else:
            console.print("[bold]Running exploit...[/bold]")
            subprocess.run(
                ["docker", "compose", "run", "--rm", "exploiter"], cwd=work_dir
            )
    except subprocess.CalledProcessError as e:
        console.print(f"[bold red]Error during exploitation:[/bold red] {e}")
        raise


def cleanup_exploit_environment(work_dir: str):
    """
    Clean up an exploit environment.

    Args:
        work_dir: Working directory to clean up
    """
    console.print("[dim]Cleaning up environment...[/dim]")
    try:
        subprocess.run(
            ["docker", "compose", "down", "--rmi", "local", "-v"],
            cwd=work_dir,
            capture_output=True,
        )
    except Exception as e:
        console.print(f"[yellow]Warning: docker compose down failed: {e}[/yellow]")
    try:
        shutil.rmtree(work_dir)
    except Exception as e:
        console.print(f"[yellow]Warning: failed to remove {work_dir}: {e}[/yellow]")
        return
    console.print("[green]Cleanup complete.[/green]")

# Explicit module exports for clarity
__all__ = [
    "ensure_docker_image",
    "run_in_docker",
    "check_docker_status",
    "display_tools_status",
    "setup_exploit_environment",
    "run_exploit",
    "cleanup_exploit_environment",
    "require_docker_image",
]


def require_docker_image() -> bool:
    """
    Ensure Docker image is available or exit with error.

    Returns:
        True if image available, exits on failure
    """
    if not ensure_docker_image():
        console.print(
            "[red]Failed to build Docker image. Ensure Docker is running.[/red]"
        )
        sys.exit(1)
    return True
