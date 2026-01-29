#!/usr/bin/env python3
"""
Battle Skill - Red vs Blue Team Security Competition Orchestrator

Based on research into:
- RvB Framework (arXiv 2601.19726)
- DARPA AIxCC scoring system
- Microsoft PyRIT multi-turn orchestration
- DeepTeam async batch processing

CONCURRENT EXECUTION:
- Red and Blue teams run in separate threads
- Shared state protected by locks
- Dynamic interaction via message queues
"""

from __future__ import annotations

import asyncio
import json
import os
import queue
import re
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

import typer
from rich.console import Console
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.panel import Panel
from rich.live import Live
from rich.layout import Layout

app = typer.Typer(help="Red vs Blue Team Security Competition Orchestrator")
console = Console()

# Paths
SKILL_DIR = Path(__file__).parent.resolve()
SKILLS_DIR = SKILL_DIR.parent
BATTLES_DIR = SKILL_DIR / "battles"
REPORTS_DIR = SKILL_DIR / "reports"
WORKTREES_DIR = SKILL_DIR / "worktrees"

# Sibling skills
HACK_SKILL = SKILLS_DIR / "hack"
ANVIL_SKILL = SKILLS_DIR / "anvil"
MEMORY_SKILL = SKILLS_DIR.parent.parent / ".agent" / "skills" / "memory"
TASK_MONITOR_SKILL = SKILLS_DIR / "task-monitor"
DOGPILE_SKILL = SKILLS_DIR.parent.parent / ".agent" / "skills" / "dogpile"
TAXONOMY_SKILL = SKILLS_DIR.parent.parent / ".agent" / "skills" / "taxonomy"


# ============================================================================
# Battle Memory - Team-Isolated Learning System
# ============================================================================

class BattleMemory:
    """
    Team-specific memory system for accumulating learnings across rounds.

    Each team (Red, Blue) gets an isolated memory collection that the opponent
    cannot access. This enables:
    - Strategic knowledge accumulation
    - Learning from past attacks/defenses
    - Cross-round strategy evolution

    Uses the memory skill with team-specific scopes:
    - battle_red_{battle_id}: Red team learnings
    - battle_blue_{battle_id}: Blue team learnings
    """

    def __init__(
        self,
        battle_id: str,
        team: str,
        max_research_calls_per_round: int = 3
    ):
        """
        Initialize team-specific memory.

        Args:
            battle_id: Unique battle identifier
            team: Team name ('red' or 'blue')
            max_research_calls_per_round: Research budget per round (default: 3)
        """
        self.battle_id = battle_id
        self.team = team.lower()
        self.scope = f"battle_{self.team}_{battle_id}"
        self.memory_script = MEMORY_SKILL / "run.sh"

        # Research budget tracking (Task 18)
        self.max_research_calls = max_research_calls_per_round
        self.research_calls_this_round = 0
        self.current_round = 0

    def recall(self, query: str, k: int = 5, threshold: float = 0.3) -> dict[str, Any]:
        """
        Query team memory for prior learnings.

        Args:
            query: The problem/task to search for
            k: Number of results to return
            threshold: Minimum confidence threshold

        Returns:
            Dict with 'found', 'items', 'confidence' keys
        """
        if not self.memory_script.exists():
            console.print("[yellow]Memory skill not available[/yellow]")
            return {"found": False, "items": [], "confidence": 0.0}

        try:
            result = subprocess.run(
                [str(self.memory_script), "recall",
                 "--q", query,
                 "--scope", self.scope,
                 "--k", str(k),
                 "--threshold", str(threshold)],
                capture_output=True, text=True, timeout=30
            )

            if result.returncode == 0:
                # Parse JSON output from memory skill
                try:
                    return json.loads(result.stdout)
                except json.JSONDecodeError:
                    # Non-JSON output, check for found/not found
                    if "found=true" in result.stdout.lower():
                        return {"found": True, "items": [result.stdout], "confidence": 0.5}
                    return {"found": False, "items": [], "confidence": 0.0}
            else:
                return {"found": False, "items": [], "confidence": 0.0, "error": result.stderr}

        except subprocess.TimeoutExpired:
            return {"found": False, "items": [], "confidence": 0.0, "error": "timeout"}
        except Exception as e:
            return {"found": False, "items": [], "confidence": 0.0, "error": str(e)}

    def learn(
        self,
        problem: str,
        solution: str,
        tags: list[str] | None = None
    ) -> bool:
        """
        Store a new learning in team memory.

        Args:
            problem: The problem that was encountered
            solution: How it was solved
            tags: Optional tags for classification (CWE numbers, attack types, etc.)

        Returns:
            True if learning was stored successfully
        """
        if not self.memory_script.exists():
            console.print("[yellow]Memory skill not available[/yellow]")
            return False

        cmd = [
            str(self.memory_script), "learn",
            "--problem", problem,
            "--solution", solution,
            "--scope", self.scope,
        ]

        # Add tags
        if tags:
            for tag in tags:
                cmd.extend(["--tag", tag])

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            return result.returncode == 0
        except Exception as e:
            console.print(f"[red]Failed to store learning: {e}[/red]")
            return False

    def start_new_round(self, round_num: int) -> None:
        """
        Start a new round - reset research budget.

        Args:
            round_num: The new round number
        """
        self.current_round = round_num
        self.research_calls_this_round = 0
        console.print(f"[cyan]Round {round_num}: Research budget reset ({self.max_research_calls} calls)[/cyan]")

    def get_research_budget_remaining(self) -> int:
        """Get remaining research calls for this round."""
        return max(0, self.max_research_calls - self.research_calls_this_round)

    def research(self, query: str, force: bool = False) -> dict[str, Any]:
        """
        Research a topic using dogpile (multi-source search).

        Subject to per-round budget limits to prevent infinite loops.

        Args:
            query: Research query
            force: If True, bypass budget check (use sparingly)

        Returns:
            Dict with research results from multiple sources
        """
        # Check budget (Task 18)
        if not force and self.research_calls_this_round >= self.max_research_calls:
            console.print(f"[yellow]Research budget exceeded ({self.max_research_calls} calls/round)[/yellow]")
            console.print(f"[dim]Query '{query}' not executed. Use force=True to override.[/dim]")
            return {
                "success": False,
                "error": "budget_exceeded",
                "budget_remaining": 0,
                "query": query
            }

        dogpile_script = DOGPILE_SKILL / "run.sh"
        if not dogpile_script.exists():
            console.print("[yellow]Dogpile skill not available[/yellow]")
            return {"success": False, "error": "dogpile not available"}

        # Increment counter BEFORE the call
        self.research_calls_this_round += 1
        remaining = self.get_research_budget_remaining()
        console.print(f"[dim]Research call {self.research_calls_this_round}/{self.max_research_calls} ({remaining} remaining)[/dim]")

        try:
            result = subprocess.run(
                [str(dogpile_script), "search", query],
                capture_output=True, text=True, timeout=300  # 5 min timeout for research
            )

            if result.returncode == 0:
                return {
                    "success": True,
                    "results": result.stdout,
                    "budget_remaining": remaining
                }
            else:
                return {"success": False, "error": result.stderr, "budget_remaining": remaining}

        except subprocess.TimeoutExpired:
            return {"success": False, "error": "research timeout", "budget_remaining": remaining}
        except Exception as e:
            return {"success": False, "error": str(e), "budget_remaining": remaining}

    def classify(self, finding: str) -> dict[str, Any]:
        """
        Classify a finding using taxonomy skill.

        Returns CWE, severity, mitigation type tags.

        Args:
            finding: The finding to classify

        Returns:
            Dict with classification tags
        """
        taxonomy_script = TAXONOMY_SKILL / "run.sh"
        if not taxonomy_script.exists():
            console.print("[yellow]Taxonomy skill not available[/yellow]")
            return {"success": False, "tags": []}

        try:
            result = subprocess.run(
                [str(taxonomy_script), "classify", finding],
                capture_output=True, text=True, timeout=60
            )

            if result.returncode == 0:
                # Parse taxonomy output
                try:
                    return json.loads(result.stdout)
                except json.JSONDecodeError:
                    return {"success": True, "tags": result.stdout.strip().split("\n")}
            else:
                return {"success": False, "tags": [], "error": result.stderr}

        except Exception as e:
            return {"success": False, "tags": [], "error": str(e)}

    def store_round_episode(
        self,
        round_num: int,
        actions: list[str],
        outcomes: list[str],
        learnings: list[str],
        taxonomy_tags: list[str] | None = None
    ) -> bool:
        """
        Archive a complete round episode for semantic recall.

        This implements the episodic archiver pattern:
        - Full round transcript with embeddings
        - Queryable for "what worked", "what failed", etc.

        Args:
            round_num: The round number
            actions: List of actions taken this round
            outcomes: Results of each action
            learnings: Key learnings from the round
            taxonomy_tags: Classification tags

        Returns:
            True if episode was stored successfully
        """
        # Format episode as a structured learning
        episode_problem = f"Round {round_num} for {self.team} team"
        episode_solution = json.dumps({
            "round": round_num,
            "actions": actions,
            "outcomes": outcomes,
            "learnings": learnings,
            "timestamp": datetime.now().isoformat()
        }, indent=2)

        tags = [f"round_{round_num}", f"team_{self.team}"]
        if taxonomy_tags:
            tags.extend(taxonomy_tags)

        return self.learn(
            problem=episode_problem,
            solution=episode_solution,
            tags=tags
        )

    def query_strategy_evolution(self, last_n_rounds: int = 3) -> list[dict]:
        """
        Query past rounds to understand strategy evolution.

        Used for cross-round learning:
        - "last 3 rounds, buffer overflows failed - try format strings"

        Args:
            last_n_rounds: Number of recent rounds to analyze

        Returns:
            List of round episodes with analysis
        """
        episodes = []
        for i in range(last_n_rounds):
            round_query = f"Round {i} {self.team} team"
            result = self.recall(round_query, k=1, threshold=0.1)
            if result.get("found"):
                episodes.append(result)

        return episodes


# ============================================================================
# Digital Twin (Code + Hardware Emulation)
# ============================================================================

class TwinMode(str, Enum):
    """Digital twin mode - how the twin is created and isolated."""
    GIT_WORKTREE = "git_worktree"  # Source code: git worktree isolation
    DOCKER = "docker"              # Container: Docker-based isolation
    QEMU = "qemu"                  # Hardware: QEMU emulation for firmware/MCU
    COPY = "copy"                  # Fallback: simple file copy


class DigitalTwin:
    """
    Creates isolated copies of the target for Red/Blue team battles.

    Supports multiple isolation modes:

    1. **GIT_WORKTREE** (source code targets):
       - Creates git worktrees for each team
       - Red attacks on arena copy
       - Blue patches on separate worktree
       - Changes cherry-picked to arena for testing

    2. **DOCKER** (containerized applications):
       - Spins up separate containers for each team
       - Red attacks arena container
       - Blue modifies defense container
       - Containers networked for interaction

    3. **QEMU** (firmware/microprocessor targets):
       - Boots target image in QEMU emulator
       - Red probes running emulation
       - Blue patches firmware image
       - Re-boots to test patches

    4. **COPY** (fallback):
       - Simple file copy for non-git projects
    """

    def __init__(
        self,
        source_path: str,
        battle_id: str,
        mode: TwinMode | None = None,
        qemu_machine: str | None = None,  # e.g., "arm", "riscv64", "x86_64"
        docker_image: str | None = None,   # e.g., "nginx:latest"
    ):
        self.source_path = Path(source_path).resolve()
        self.battle_id = battle_id
        self.worktree_base = WORKTREES_DIR / battle_id

        # Mode configuration
        self.qemu_machine = qemu_machine
        self.docker_image = docker_image

        # Auto-detect mode if not specified
        self.mode = mode or self._detect_mode()

        # Workspace paths (set during setup)
        self.red_worktree: Path | None = None    # Red team's attack surface
        self.blue_worktree: Path | None = None   # Blue team's defense workspace
        self.arena_worktree: Path | None = None  # Combined battle arena

        # Docker container IDs (if using Docker mode)
        self.red_container: str | None = None
        self.blue_container: str | None = None
        self.arena_container: str | None = None

        # QEMU process handles (if using QEMU mode)
        self.qemu_processes: dict[str, subprocess.Popen] = {}

        self._is_git_repo = self._check_git_repo()

    def _check_git_repo(self) -> bool:
        """Check if source is a git repository."""
        # Use parent directory if source is a file
        check_dir = self.source_path if self.source_path.is_dir() else self.source_path.parent
        result = subprocess.run(
            ["git", "rev-parse", "--git-dir"],
            cwd=check_dir,
            capture_output=True
        )
        return result.returncode == 0

    def _detect_mode(self) -> TwinMode:
        """Auto-detect the appropriate twin mode based on target."""
        # If Docker image specified, use Docker mode
        if self.docker_image:
            return TwinMode.DOCKER

        # If QEMU machine specified, use QEMU mode
        if self.qemu_machine:
            return TwinMode.QEMU

        # Check for firmware/binary files suggesting hardware target
        firmware_extensions = {'.bin', '.hex', '.elf', '.img', '.rom', '.fw'}
        if self.source_path.is_file():
            if self.source_path.suffix.lower() in firmware_extensions:
                return TwinMode.QEMU

        # Check for Dockerfile suggesting container target
        if (self.source_path / "Dockerfile").exists():
            return TwinMode.DOCKER

        # Check if it's a git repo
        if self._check_git_repo():
            return TwinMode.GIT_WORKTREE

        # Fallback to copy mode
        return TwinMode.COPY

    def _run_git(self, *args, cwd: Path | None = None) -> subprocess.CompletedProcess:
        """Run a git command."""
        return subprocess.run(
            ["git", *args],
            cwd=cwd or self.source_path,
            capture_output=True,
            text=True
        )

    def setup(self) -> bool:
        """Create the digital twin based on detected/configured mode."""
        console.print(f"[cyan]Creating digital twin (mode: {self.mode.value})...[/cyan]")

        if self.mode == TwinMode.DOCKER:
            return self._setup_docker_mode()
        elif self.mode == TwinMode.QEMU:
            return self._setup_qemu_mode()
        elif self.mode == TwinMode.GIT_WORKTREE and self._is_git_repo:
            return self._setup_git_mode()
        else:
            return self._setup_copy_mode()

    def _setup_git_mode(self) -> bool:
        """Create git worktree-based digital twin (for source code targets)."""
        console.print("[cyan]Creating git worktrees...[/cyan]")
        self.worktree_base.mkdir(parents=True, exist_ok=True)

        # Get current branch
        result = self._run_git("rev-parse", "--abbrev-ref", "HEAD")
        base_branch = result.stdout.strip() or "main"

        # Create battle branches
        battle_branch_red = f"battle/{self.battle_id}/red"
        battle_branch_blue = f"battle/{self.battle_id}/blue"
        battle_branch_arena = f"battle/{self.battle_id}/arena"

        try:
            # Create branches from current HEAD
            for branch in [battle_branch_red, battle_branch_blue, battle_branch_arena]:
                self._run_git("branch", branch)

            # Create worktrees
            self.red_worktree = self.worktree_base / "red"
            self.blue_worktree = self.worktree_base / "blue"
            self.arena_worktree = self.worktree_base / "arena"

            self._run_git("worktree", "add", str(self.red_worktree), battle_branch_red)
            self._run_git("worktree", "add", str(self.blue_worktree), battle_branch_blue)
            self._run_git("worktree", "add", str(self.arena_worktree), battle_branch_arena)

            console.print(f"  [green]Red worktree:[/green] {self.red_worktree}")
            console.print(f"  [green]Blue worktree:[/green] {self.blue_worktree}")
            console.print(f"  [green]Arena worktree:[/green] {self.arena_worktree}")

            return True

        except Exception as e:
            console.print(f"[red]Failed to create worktrees: {e}[/red]")
            return False

    def _setup_copy_mode(self) -> bool:
        """Fallback: create copies instead of worktrees."""
        import shutil

        self.worktree_base.mkdir(parents=True, exist_ok=True)

        self.red_worktree = self.worktree_base / "red"
        self.blue_worktree = self.worktree_base / "blue"
        self.arena_worktree = self.worktree_base / "arena"

        # Ignore patterns including our own worktrees/battles directories
        ignore_patterns = shutil.ignore_patterns(
            '.git', '__pycache__', '*.pyc', 'worktrees', 'battles', 'reports'
        )

        try:
            for worktree in [self.red_worktree, self.blue_worktree, self.arena_worktree]:
                if worktree.exists():
                    shutil.rmtree(worktree)
                shutil.copytree(self.source_path, worktree, ignore=ignore_patterns)

            console.print(f"  [green]Created copies in {self.worktree_base}[/green]")
            return True

        except Exception as e:
            console.print(f"[red]Failed to create copies: {e}[/red]")
            return False

    def _setup_docker_mode(self) -> bool:
        """
        Create Docker container-based digital twin.

        For containerized applications (e.g., web services, APIs):
        - Builds/pulls the image
        - Creates 3 isolated containers: red (attack), blue (defense), arena (test)
        - Containers share a battle network for interaction
        """
        console.print("[cyan]Creating Docker-based digital twin...[/cyan]")

        try:
            # Create battle network
            network_name = f"battle_{self.battle_id}"
            subprocess.run(
                ["docker", "network", "create", network_name],
                capture_output=True, check=False
            )

            # Determine image to use
            if self.docker_image:
                image = self.docker_image
            elif (self.source_path / "Dockerfile").exists():
                # Build from Dockerfile
                image = f"battle_{self.battle_id}:latest"
                result = subprocess.run(
                    ["docker", "build", "-t", image, str(self.source_path)],
                    capture_output=True, text=True
                )
                if result.returncode != 0:
                    console.print(f"[red]Docker build failed: {result.stderr}[/red]")
                    return False
            else:
                console.print("[red]No Docker image or Dockerfile found[/red]")
                return False

            # Create containers for each team
            # SECURITY: Complete isolation - no host filesystem access
            seccomp_profile = SKILL_DIR / "docker" / "seccomp-battle.json"

            for team, container_var in [
                ("red", "red_container"),
                ("blue", "blue_container"),
                ("arena", "arena_container"),
            ]:
                container_name = f"battle_{self.battle_id}_{team}"

                run_args = [
                    "docker", "run", "-d",
                    "--name", container_name,
                    "--network", network_name,
                    # Security hardening - COMPLETE ISOLATION FROM HOST
                    "--cap-drop", "ALL",
                    "--security-opt", "no-new-privileges",
                    "--pids-limit", "256",
                    "--memory", "512m",
                    "--memory-swap", "512m",
                    "--cpus", "1.0",
                    # Read-only root filesystem
                    "--read-only",
                    "--tmpfs", "/tmp:rw,noexec,nosuid,nodev,size=64m",
                    "--tmpfs", "/workspace:rw,exec,size=256m",
                    # NO VOLUME MOUNTS - prevents host filesystem access
                    "--label", f"battle_id={self.battle_id}",
                    "--label", f"battle_team={team}",
                ]

                # Add seccomp profile if it exists
                if seccomp_profile.exists():
                    run_args.extend(["--security-opt", f"seccomp={seccomp_profile}"])

                run_args.append(image)

                result = subprocess.run(run_args, capture_output=True, text=True)
                if result.returncode == 0:
                    setattr(self, container_var, result.stdout.strip())
                    console.print(f"  [green]{team.title()} container: {container_name} (ISOLATED)[/green]")
                else:
                    console.print(f"[red]Failed to create {team} container: {result.stderr}[/red]")
                    return False

            # Set worktree paths to container exec entry points (for compatibility)
            self.worktree_base.mkdir(parents=True, exist_ok=True)
            self.red_worktree = self.worktree_base / "red"
            self.blue_worktree = self.worktree_base / "blue"
            self.arena_worktree = self.worktree_base / "arena"

            for worktree in [self.red_worktree, self.blue_worktree, self.arena_worktree]:
                worktree.mkdir(exist_ok=True)
                # Write container info for skills to use
                (worktree / ".docker_container").write_text(
                    getattr(self, f"{worktree.name}_container") or ""
                )

            return True

        except Exception as e:
            console.print(f"[red]Docker setup failed: {e}[/red]")
            return False

    def _setup_qemu_mode(self) -> bool:
        """
        Create QEMU emulation-based digital twin using Docker containers.

        Based on dogpile research: QEMU should run inside Docker for:
        - Reproducibility (deterministic environment)
        - Isolation (each team in separate container)
        - Portability (no host QEMU dependency)

        For firmware/microprocessor targets:
        - Boots firmware image in QEMU emulator inside Docker
        - Creates 3 isolated containers: red (attack), blue (defense), arena (test)
        - Each container runs independently with its own QEMU instance

        Common microprocessor targets:
        - ARM Cortex-M (STM32, etc.)
        - RISC-V
        - x86 (BIOS/UEFI)
        - MIPS (routers, embedded)
        """
        console.print("[cyan]Creating QEMU emulation-based digital twin (Docker mode)...[/cyan]")

        # Detect QEMU machine type
        machine = self.qemu_machine or self._detect_qemu_machine()
        if not machine:
            console.print("[red]Cannot determine QEMU machine type[/red]")
            console.print("[yellow]Hint: Specify --qemu-machine (e.g., arm, riscv64, x86_64)[/yellow]")
            return False

        # Check Docker is available
        if subprocess.run(["docker", "info"], capture_output=True).returncode != 0:
            console.print("[red]Docker not available[/red]")
            console.print("[yellow]Install Docker or start the daemon[/yellow]")
            return False

        # Check battle-qemu-twin image exists
        result = subprocess.run(
            ["docker", "images", "-q", "battle-qemu-twin"],
            capture_output=True, text=True
        )
        if not result.stdout.strip():
            console.print("[yellow]Building battle-qemu-twin Docker image...[/yellow]")
            docker_dir = SKILL_DIR / "docker"
            if docker_dir.exists():
                build_result = subprocess.run(
                    ["docker", "build", "-t", "battle-qemu-twin", str(docker_dir)],
                    capture_output=True, text=True
                )
                if build_result.returncode != 0:
                    console.print(f"[red]Failed to build Docker image: {build_result.stderr}[/red]")
                    return False
            else:
                console.print("[red]Docker directory not found[/red]")
                return False

        self.worktree_base.mkdir(parents=True, exist_ok=True)

        try:
            import shutil

            # Create network for battle containers
            network_name = f"battle_{self.battle_id}"
            subprocess.run(
                ["docker", "network", "create", network_name],
                capture_output=True, check=False
            )

            # Copy firmware and create containers for each team
            for team in ["red", "blue", "arena"]:
                team_dir = self.worktree_base / team
                team_dir.mkdir(exist_ok=True)

                # Copy firmware file(s)
                if self.source_path.is_file():
                    dest = team_dir / self.source_path.name
                    shutil.copy2(self.source_path, dest)
                    firmware_name = self.source_path.name
                else:
                    fw_dest = team_dir / "firmware"
                    if fw_dest.exists():
                        shutil.rmtree(fw_dest)
                    shutil.copytree(self.source_path, fw_dest,
                                    ignore=shutil.ignore_patterns('.git'))
                    firmware_name = "firmware"

                # Calculate ports for this team
                gdb_port = 5000 + hash(f'{self.battle_id}_{team}') % 1000
                qmp_port = 6000 + hash(f'{self.battle_id}_{team}') % 1000

                # Write QEMU config
                qemu_config = team_dir / "qemu.conf"
                qemu_config.write_text(f"""# QEMU Configuration for {team} team
machine={machine}
firmware={firmware_name}
gdb_port={gdb_port}
qmp_port={qmp_port}
docker_image=battle-qemu-twin
network={network_name}
""")

                # Create container (stopped, will start on-demand)
                # SECURITY: No volume mounts - use docker cp instead to prevent host access
                container_name = f"battle_{self.battle_id}_{team}"
                seccomp_profile = SKILL_DIR / "docker" / "seccomp-battle.json"

                create_args = [
                    "docker", "create",
                    "--name", container_name,
                    "--network", network_name,
                    # Security hardening - COMPLETE ISOLATION FROM HOST
                    "--cap-drop", "ALL",
                    "--security-opt", "no-new-privileges",
                    "--pids-limit", "256",
                    "--memory", "512m",
                    "--memory-swap", "512m",  # No swap
                    "--cpus", "1.0",
                    # Read-only root filesystem with specific writable tmpfs
                    "--read-only",
                    "--tmpfs", "/tmp:rw,noexec,nosuid,nodev,size=64m",
                    "--tmpfs", "/battle/firmware:rw,exec,size=128m",
                    "--tmpfs", "/battle/corpus:rw,exec,size=64m",
                    "--tmpfs", "/battle/findings:rw,exec,size=128m",
                    "--tmpfs", "/battle/crashes:rw,exec,size=64m",
                    "--tmpfs", "/battle/snapshots:rw,exec,size=256m",
                    # NO VOLUME MOUNTS - prevents host filesystem access
                    "-p", f"{gdb_port}:{gdb_port}",
                    "-p", f"{qmp_port}:{qmp_port}",
                    "--label", f"battle_id={self.battle_id}",
                    "--label", f"battle_team={team}",
                    "--label", f"battle_machine={machine}",
                    "-e", f"GDB_PORT={gdb_port}",
                    "-e", f"ARCH={machine}",
                ]

                # Add seccomp profile if it exists
                if seccomp_profile.exists():
                    create_args.extend(["--security-opt", f"seccomp={seccomp_profile}"])

                create_args.extend([
                    "battle-qemu-twin",
                    "sleep", "infinity"  # Keep container alive
                ])

                result = subprocess.run(create_args, capture_output=True, text=True)

                if result.returncode == 0:
                    container_id = result.stdout.strip()
                    # Store container ID
                    (team_dir / ".docker_container").write_text(container_id)

                    # Copy firmware files INTO container via docker cp (no volume mount)
                    # This prevents container from accessing host filesystem
                    subprocess.run(
                        ["docker", "start", container_name],
                        capture_output=True, text=True
                    )

                    # Copy firmware files
                    for item in team_dir.iterdir():
                        if item.name.startswith('.'):
                            continue  # Skip hidden files
                        subprocess.run(
                            ["docker", "cp", str(item), f"{container_name}:/battle/firmware/"],
                            capture_output=True, text=True, timeout=30
                        )

                    console.print(f"  [green]{team.title()} container: {container_name} (ISOLATED)[/green]")
                    console.print(f"    GDB port: {gdb_port}, QMP port: {qmp_port}")
                    console.print(f"    [dim]No host filesystem access - files copied via docker cp[/dim]")
                else:
                    console.print(f"[red]Failed to create {team} container: {result.stderr}[/red]")
                    return False

            self.red_worktree = self.worktree_base / "red"
            self.blue_worktree = self.worktree_base / "blue"
            self.arena_worktree = self.worktree_base / "arena"

            console.print(f"\n  [green]QEMU machine: {machine}[/green]")
            console.print(f"  [green]Docker network: {network_name}[/green]")
            console.print(f"  [green]Firmware directories: {self.worktree_base}[/green]")
            console.print("[dim]Note: Containers created (stopped). Start with docker start <name>[/dim]")

            return True

        except Exception as e:
            console.print(f"[red]QEMU Docker setup failed: {e}[/red]")
            return False

    def _detect_qemu_machine(self) -> str | None:
        """Detect appropriate QEMU machine type from firmware file."""
        if not self.source_path.exists():
            return None

        # Read first bytes to detect architecture
        try:
            with open(self.source_path, 'rb') as f:
                header = f.read(64)

            # ELF magic check
            if header[:4] == b'\x7fELF':
                # ELF file - check machine type
                ei_class = header[4]  # 32 or 64 bit
                e_machine = int.from_bytes(header[18:20], 'little')

                machine_map = {
                    0x03: "i386",      # x86
                    0x3E: "x86_64",    # x86-64
                    0x28: "arm",       # ARM
                    0xB7: "aarch64",   # ARM64
                    0xF3: "riscv64" if ei_class == 2 else "riscv32",  # RISC-V
                    0x08: "mips",      # MIPS
                }
                return machine_map.get(e_machine)

            # Intel HEX files typically for ARM embedded
            if header.startswith(b':'):
                return "arm"

            # Binary files - could be anything, default to ARM (common for MCU)
            if self.source_path.suffix.lower() in {'.bin', '.fw', '.rom'}:
                return "arm"

        except Exception:
            pass

        return None

    def start_qemu_instance(self, team: str, wait_boot: bool = True) -> bool:
        """
        Start a QEMU instance for the specified team inside Docker container.

        Args:
            team: Team name (red, blue, arena)
            wait_boot: Wait for QEMU to boot before returning

        Returns:
            True if QEMU started successfully
        """
        if self.mode != TwinMode.QEMU:
            console.print("[yellow]Not in QEMU mode[/yellow]")
            return False

        team_dir = self.worktree_base / team
        if not team_dir.exists():
            console.print(f"[red]Team directory not found: {team_dir}[/red]")
            return False

        container_name = f"battle_{self.battle_id}_{team}"

        # Read QEMU config
        qemu_config = team_dir / "qemu.conf"
        if not qemu_config.exists():
            console.print(f"[red]QEMU config not found for {team}[/red]")
            return False

        config = {}
        for line in qemu_config.read_text().strip().split('\n'):
            if '=' in line and not line.startswith('#'):
                key, val = line.split('=', 1)
                config[key] = val

        machine = config.get('machine', 'arm')
        firmware_name = config.get('firmware', 'firmware')
        gdb_port = config.get('gdb_port', '5000')
        qmp_port = config.get('qmp_port', '6000')

        # Start the container
        result = subprocess.run(
            ["docker", "start", container_name],
            capture_output=True, text=True
        )
        if result.returncode != 0:
            console.print(f"[red]Failed to start container: {result.stderr}[/red]")
            return False

        # Create QCOW2 disk for snapshot support (required for savevm/loadvm)
        disk_path = f"/battle/firmware/{team}_disk.qcow2"
        subprocess.run(
            ["docker", "exec", container_name,
             "qemu-img", "create", "-f", "qcow2", disk_path, "64M"],
            capture_output=True
        )

        # Read peripheral stub configuration (Task 11)
        enable_stubs = True
        enable_mmio_log = False
        mmio_log_path = f"/battle/firmware/{team}_mmio.log"

        stub_file = team_dir / "peripheral_stubs.json"
        if stub_file.exists():
            try:
                stub_config = json.loads(stub_file.read_text())
                enable_stubs = stub_config.get("uart", True) or stub_config.get("timer", True)
                enable_mmio_log = stub_config.get("mmio_log", False)
                # Sanitize mmio_log_path to prevent path traversal (code review fix)
                cfg_path = stub_config.get("mmio_log_path", mmio_log_path)
                if isinstance(cfg_path, str) and cfg_path.startswith("/battle/"):
                    mmio_log_path = cfg_path
            except Exception:
                pass

        # Start QEMU inside the container with QMP socket for snapshot control
        # Returns list[str] to avoid shell injection (code review fix)
        qemu_args = self._build_qemu_command(
            machine, firmware_name, gdb_port, qmp_port, disk_path,
            enable_peripheral_stubs=enable_stubs,
            enable_mmio_log=enable_mmio_log,
            mmio_log_path=mmio_log_path
        )

        # Execute directly without shell (security hardening)
        result = subprocess.run(
            ["docker", "exec", "-d", container_name, *qemu_args],
            capture_output=True, text=True
        )

        if result.returncode != 0:
            console.print(f"[red]Failed to start QEMU in container: {result.stderr}[/red]")
            return False

        console.print(f"  [green]{team.title()} QEMU started in container {container_name}[/green]")
        console.print(f"    GDB: localhost:{gdb_port}, QMP: localhost:{qmp_port}")
        if enable_mmio_log:
            console.print(f"    MMIO log: {mmio_log_path}")

        if wait_boot:
            # Wait for QMP socket to be ready (indicates QEMU is running)
            time.sleep(2)  # Give QEMU time to start

        return True

    def _build_qemu_command(
        self,
        machine: str,
        firmware_name: str,
        gdb_port: str,
        qmp_port: str,
        disk_path: str,
        enable_peripheral_stubs: bool = True,
        enable_mmio_log: bool = False,
        mmio_log_path: str = "/battle/firmware/mmio.log"
    ) -> list[str]:
        """
        Build QEMU command as argument list for running inside container.

        Returns a list of arguments (not a string) to avoid shell injection.

        Args:
            machine: Architecture (arm, aarch64, riscv64, x86_64, etc.)
            firmware_name: Name of firmware file in /battle/firmware/
            gdb_port: GDB remote debug port
            qmp_port: QMP control port
            disk_path: Path to QCOW2 disk for snapshots
            enable_peripheral_stubs: Add P2IM-style peripheral stubs (Task 11)
            enable_mmio_log: Enable MMIO access logging (Task 12)
            mmio_log_path: Path for MMIO log file
        """
        # Machine configuration based on architecture
        machine_configs = {
            'arm': (['-M', 'virt', '-cpu', 'cortex-a15'], '-kernel'),
            'aarch64': (['-M', 'virt', '-cpu', 'cortex-a53'], '-kernel'),
            'riscv64': (['-M', 'virt', '-cpu', 'rv64'], '-kernel'),
            'x86_64': (['-M', 'q35', '-cpu', 'qemu64'], '-bios'),
            'i386': (['-M', 'q35', '-cpu', 'qemu32'], '-bios'),
            'mips': (['-M', 'malta', '-cpu', '24Kc'], '-kernel'),
        }

        machine_opts, fw_opt = machine_configs.get(machine, (['-M', 'virt'], '-kernel'))
        qemu_binary = f"qemu-system-{machine}"

        # Build command with QMP socket for snapshot management
        # Using argument list (not string) to prevent shell injection
        cmd_parts: list[str] = [
            qemu_binary,
            *machine_opts,
            "-m", "64M",
            "-nographic",
            "-gdb", f"tcp::{gdb_port}",
            "-qmp", f"tcp::{qmp_port},server,nowait",
            "-drive", f"file={disk_path},format=qcow2,if=virtio",
            fw_opt, f"/battle/firmware/{firmware_name}",
        ]

        # Task 11: Add peripheral stubs to prevent boot hangs
        if enable_peripheral_stubs:
            stub_opts = self._get_peripheral_stub_options(machine)
            cmd_parts.extend(stub_opts)

        # Task 12: Enable MMIO logging for debugging
        if enable_mmio_log:
            mmio_opts = self._get_mmio_log_options(mmio_log_path)
            cmd_parts.extend(mmio_opts)

        return cmd_parts

    def _get_peripheral_stub_options(self, machine: str) -> list[str]:
        """
        Get QEMU options for P2IM-style peripheral stubbing (Task 11).

        These stubs prevent firmware from hanging when it tries to access
        peripherals that don't exist in the emulated environment.

        Common stubbed peripherals:
        - UART: Serial communication
        - Timer: System timers
        - IRQ: Interrupt controller
        - GPIO: General purpose I/O
        """
        opts = []

        if machine in ['arm', 'aarch64']:
            # ARM virt machine already has basic peripherals
            # Add serial console for output capture
            opts.extend([
                "-serial", "mon:stdio",  # Redirect serial to console
            ])

            # For bare-metal firmware, we might need additional stubs
            # The 'virt' machine provides:
            # - GICv2/v3 interrupt controller
            # - PL011 UART
            # - PL031 RTC
            # - Generic timer

        elif machine in ['x86_64', 'i386']:
            # x86 q35 machine has most peripherals
            opts.extend([
                "-serial", "mon:stdio",
            ])

        elif machine == 'riscv64':
            # RISC-V virt machine provides:
            # - PLIC (interrupt controller)
            # - UART (16550)
            # - VirtIO devices
            opts.extend([
                "-serial", "mon:stdio",
            ])

        elif machine == 'mips':
            # MIPS malta board provides:
            # - 8259 PIC
            # - 16550 UART
            # - Bonito north bridge
            opts.extend([
                "-serial", "mon:stdio",
            ])

        # Add a watchdog to prevent infinite loops
        # (disabled by default as it can cause false terminations)
        # opts.extend(["-watchdog", "i6300esb", "-watchdog-action", "pause"])

        return opts

    def _get_mmio_log_options(self, log_path: str) -> list[str]:
        """
        Get QEMU options for MMIO access logging (Task 12).

        Logs all memory-mapped I/O accesses to help debug firmware
        boot failures caused by accessing non-existent peripherals.

        The log shows:
        - Address of access
        - Size (1/2/4/8 bytes)
        - Direction (read/write)
        - Value (for writes)
        """
        # QEMU trace events for MMIO logging
        # Note: These require QEMU built with --enable-trace-backends
        trace_events = [
            "memory_region_ops_read",
            "memory_region_ops_write",
        ]

        opts = [
            # Enable tracing to file
            "-D", log_path,
            "-d", "guest_errors,unimp",  # Log unimplemented device accesses
        ]

        # Add trace events (may not work on all QEMU builds)
        # for event in trace_events:
        #     opts.extend(["--trace", event])

        return opts

    def configure_peripheral_stubs(self, team: str, stub_config: dict[str, Any] | None = None) -> bool:
        """
        Configure peripheral stubs for a team's QEMU instance (Task 11).

        Args:
            team: Team name (red, blue, arena)
            stub_config: Optional custom stub configuration

        Returns:
            True if configuration was written successfully
        """
        if self.mode != TwinMode.QEMU:
            return False

        team_dir = self.worktree_base / team

        # Default stub configuration
        default_config = {
            "uart": True,       # Enable UART output
            "timer": True,      # Enable system timer
            "irq": True,        # Enable interrupt controller
            "watchdog": False,  # Disable watchdog by default
            "mmio_log": False,  # Disable MMIO logging by default
        }

        config = {**default_config, **(stub_config or {})}

        # Write stub configuration
        stub_file = team_dir / "peripheral_stubs.json"
        stub_file.write_text(json.dumps(config, indent=2))

        console.print(f"  [green]Configured peripheral stubs for {team}[/green]")
        return True

    def enable_mmio_logging(self, team: str) -> Path | None:
        """
        Enable MMIO logging for a team's QEMU instance (Task 12).

        Logs all memory-mapped I/O accesses to help debug boot failures.

        Args:
            team: Team name

        Returns:
            Path to MMIO log file, or None if failed
        """
        if self.mode != TwinMode.QEMU:
            return None

        team_dir = self.worktree_base / team
        mmio_log = team_dir / "mmio.log"

        # Update stub config to enable MMIO logging
        stub_file = team_dir / "peripheral_stubs.json"
        if stub_file.exists():
            config = json.loads(stub_file.read_text())
        else:
            config = {}

        config["mmio_log"] = True
        config["mmio_log_path"] = str(mmio_log)
        stub_file.write_text(json.dumps(config, indent=2))

        console.print(f"  [green]MMIO logging enabled for {team}: {mmio_log}[/green]")
        return mmio_log

    def read_mmio_log(self, team: str, tail_lines: int = 50) -> str:
        """
        Read MMIO log entries for a team.

        Args:
            team: Team name
            tail_lines: Number of recent lines to return

        Returns:
            MMIO log content
        """
        if self.mode != TwinMode.QEMU:
            return ""

        team_dir = self.worktree_base / team
        mmio_log = team_dir / "mmio.log"

        if not mmio_log.exists():
            return "MMIO log not found (enable with enable_mmio_logging first)"

        container_name = f"battle_{self.battle_id}_{team}"

        try:
            result = subprocess.run(
                ["docker", "exec", container_name, "tail", f"-{tail_lines}", str(mmio_log)],
                capture_output=True, text=True, timeout=10
            )
            return result.stdout if result.returncode == 0 else result.stderr
        except Exception as e:
            return f"Error reading MMIO log: {e}"

    # ========================================================================
    # AFL++ Fuzzing Integration (Tasks 8-10)
    # ========================================================================

    def start_afl_fuzzing(
        self,
        team: str,
        target_binary: str,
        input_corpus: str | None = None,
        timeout_ms: int = 1000,
        memory_limit_mb: int = 256
    ) -> bool:
        """
        Start AFL++ fuzzing for a team's target (Task 8).

        Uses AFL++ QEMU mode for coverage-guided fuzzing without source.

        Args:
            team: Team name (typically 'red' for attacks)
            target_binary: Path to binary inside container
            input_corpus: Path to initial corpus (or None for empty)
            timeout_ms: Timeout per execution in milliseconds
            memory_limit_mb: Memory limit for fuzzed process

        Returns:
            True if fuzzing started successfully
        """
        if self.mode != TwinMode.QEMU:
            console.print("[yellow]AFL++ fuzzing only available in QEMU mode[/yellow]")
            return False

        container_name = f"battle_{self.battle_id}_{team}"
        team_dir = self.worktree_base / team

        # Ensure directories exist in container
        for dir_name in ["corpus", "crashes", "findings"]:
            subprocess.run(
                ["docker", "exec", container_name, "mkdir", "-p", f"/battle/{dir_name}"],
                capture_output=True
            )

        # Create initial corpus if needed (security: no shell, use docker cp)
        if not input_corpus:
            input_corpus = "/battle/corpus"
            # Check if corpus is empty without shell
            list_res = subprocess.run(
                ["docker", "exec", container_name, "ls", "-A", "/battle/corpus"],
                capture_output=True, text=True, timeout=10
            )
            if list_res.returncode != 0 or not list_res.stdout.strip():
                # Create seed file via docker cp (no shell injection)
                with tempfile.NamedTemporaryFile(mode='wb', delete=False) as tf:
                    tf.write(b"AAAA")
                    host_seed = tf.name
                try:
                    subprocess.run(
                        ["docker", "cp", host_seed, f"{container_name}:/battle/corpus/seed_0"],
                        capture_output=True, text=True, timeout=10
                    )
                finally:
                    try:
                        os.unlink(host_seed)
                    except Exception:
                        pass

        # Build AFL++ command as argument list (no shell)
        # Using QEMU mode (-Q) for binary-only fuzzing
        afl_cmd = [
            "afl-fuzz",
            "-Q",  # QEMU mode
            "-i", input_corpus,
            "-o", "/battle/findings",
            "-t", str(timeout_ms),
            "-m", str(memory_limit_mb),
            "--", target_binary
        ]

        console.print(f"[red]Starting AFL++ fuzzing for {team}...[/red]")
        console.print(f"  Target: {target_binary}")
        console.print(f"  Corpus: {input_corpus}")

        # Start AFL++ in background inside container (no shell)
        result = subprocess.run(
            ["docker", "exec", "-d", container_name, *afl_cmd],
            capture_output=True, text=True
        )

        if result.returncode == 0:
            console.print(f"  [green]AFL++ started in container {container_name}[/green]")
            # Save fuzzing state
            (team_dir / ".afl_running").write_text(json.dumps({
                "target": target_binary,
                "started": datetime.now().isoformat(),
                "container": container_name
            }))
            return True
        else:
            console.print(f"[red]Failed to start AFL++: {result.stderr}[/red]")
            return False

    def stop_afl_fuzzing(self, team: str) -> bool:
        """Stop AFL++ fuzzing for a team."""
        container_name = f"battle_{self.battle_id}_{team}"
        team_dir = self.worktree_base / team

        result = subprocess.run(
            ["docker", "exec", container_name, "pkill", "-f", "afl-fuzz"],
            capture_output=True
        )

        # Clean up state file
        state_file = team_dir / ".afl_running"
        if state_file.exists():
            state_file.unlink()

        console.print(f"[red]AFL++ stopped for {team}[/red]")
        return True

    def get_fuzzing_stats(self, team: str) -> dict[str, Any]:
        """
        Get AFL++ fuzzing statistics (Task 8).

        Returns coverage %, execs/sec, crash count, etc.
        """
        container_name = f"battle_{self.battle_id}_{team}"

        try:
            # Read AFL++ stats file
            result = subprocess.run(
                ["docker", "exec", container_name, "cat", "/battle/findings/default/fuzzer_stats"],
                capture_output=True, text=True, timeout=10
            )

            if result.returncode != 0:
                return {"error": "Fuzzer not running or stats unavailable"}

            # Parse stats
            stats = {}
            for line in result.stdout.strip().split('\n'):
                if ':' in line:
                    key, val = line.split(':', 1)
                    key = key.strip()
                    val = val.strip()
                    # Try to convert to number
                    try:
                        stats[key] = int(val)
                    except ValueError:
                        try:
                            stats[key] = float(val)
                        except ValueError:
                            stats[key] = val

            # Calculate coverage metrics
            if "bitmap_cvg" in stats:
                stats["coverage_percent"] = float(stats["bitmap_cvg"].rstrip('%'))

            return stats

        except Exception as e:
            return {"error": str(e)}

    def collect_crashes(self, team: str) -> list[dict[str, Any]]:
        """
        Collect crash files from AFL++ output (Task 9).

        Returns list of crash info with paths and metadata.
        """
        container_name = f"battle_{self.battle_id}_{team}"
        team_dir = self.worktree_base / team
        crashes = []

        try:
            # List crash files
            result = subprocess.run(
                ["docker", "exec", container_name, "ls", "-la", "/battle/findings/default/crashes/"],
                capture_output=True, text=True, timeout=10
            )

            if result.returncode != 0:
                return []

            # Parse file listing
            for line in result.stdout.strip().split('\n'):
                parts = line.split()
                if len(parts) >= 9 and parts[-1].startswith('id:'):
                    filename = parts[-1]
                    size = parts[4]
                    crashes.append({
                        "filename": filename,
                        "path": f"/battle/findings/default/crashes/{filename}",
                        "size": size,
                        "team": team,
                    })

            console.print(f"[red]Found {len(crashes)} crashes for {team}[/red]")
            return crashes

        except Exception as e:
            console.print(f"[red]Error collecting crashes: {e}[/red]")
            return []

    def triage_crash(self, team: str, crash_path: str) -> dict[str, Any]:
        """
        Triage a crash using GDB to get backtrace (Task 9).

        Restores QEMU snapshot, feeds crash input, attaches GDB for analysis.
        """
        container_name = f"battle_{self.battle_id}_{team}"
        team_dir = self.worktree_base / team

        console.print(f"[cyan]Triaging crash: {crash_path}[/cyan]")

        try:
            # Use GDB to analyze the crash
            gdb_script = f"""set pagination off
set confirm off
run < {crash_path}
bt full
info registers
quit
"""
            # Write GDB script via docker cp (no shell injection)
            with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.gdb') as tf:
                tf.write(gdb_script)
                host_gdb_path = tf.name
            try:
                subprocess.run(
                    ["docker", "cp", host_gdb_path, f"{container_name}:/tmp/triage.gdb"],
                    capture_output=True, text=True, timeout=10
                )
            finally:
                try:
                    os.unlink(host_gdb_path)
                except Exception:
                    pass

            # Run GDB with crash input
            result = subprocess.run(
                ["docker", "exec", container_name, "timeout", "30",
                 "gdb-multiarch", "-batch", "-x", "/tmp/triage.gdb"],
                capture_output=True, text=True, timeout=60
            )

            # Parse backtrace
            triage_result = {
                "crash_path": crash_path,
                "backtrace": "",
                "registers": "",
                "crash_address": None,
                "crash_function": None,
            }

            if result.stdout:
                lines = result.stdout.split('\n')
                bt_start = False
                reg_start = False

                for line in lines:
                    if line.startswith('#'):
                        bt_start = True
                        triage_result["backtrace"] += line + '\n'
                        if triage_result["crash_function"] is None and ' in ' in line:
                            # Extract function name
                            triage_result["crash_function"] = line.split(' in ')[1].split()[0]
                    elif any(reg in line.lower() for reg in ['r0', 'rax', 'eax', 'pc', 'rip']):
                        triage_result["registers"] += line + '\n'

            console.print(f"  [green]Crash function: {triage_result.get('crash_function', 'unknown')}[/green]")
            return triage_result

        except Exception as e:
            console.print(f"[red]Triage failed: {e}[/red]")
            return {"error": str(e)}

    def add_to_corpus(self, team: str, input_data: bytes, name: str | None = None) -> bool:
        """
        Add a new input to the fuzzing corpus (Task 10).

        Args:
            team: Team name
            input_data: The input bytes to add
            name: Optional name for the corpus file

        Returns:
            True if added successfully
        """
        container_name = f"battle_{self.battle_id}_{team}"

        if name is None:
            name = f"seed_{int(time.time())}"

        # Sanitize filename to prevent path traversal (code review fix)
        if not re.fullmatch(r"[A-Za-z0-9._-]{1,128}", name):
            console.print(f"[red]Invalid corpus filename: {name}[/red]")
            return False

        try:
            # Write input via docker cp (no shell injection)
            with tempfile.NamedTemporaryFile(mode='wb', delete=False) as tf:
                tf.write(input_data)
                host_path = tf.name
            try:
                result = subprocess.run(
                    ["docker", "cp", host_path, f"{container_name}:/battle/corpus/{name}"],
                    capture_output=True, text=True, timeout=10
                )
            finally:
                try:
                    os.unlink(host_path)
                except Exception:
                    pass

            if result.returncode == 0:
                console.print(f"  [green]Added to corpus: {name}[/green]")
                return True
            return False

        except Exception as e:
            console.print(f"[red]Failed to add to corpus: {e}[/red]")
            return False

    def get_corpus_stats(self, team: str) -> dict[str, Any]:
        """
        Get corpus statistics (Task 10).

        Returns count, total size, and file list.
        """
        container_name = f"battle_{self.battle_id}_{team}"

        try:
            # Count files without shell (code review fix)
            list_res = subprocess.run(
                ["docker", "exec", container_name, "ls", "-1", "/battle/corpus"],
                capture_output=True, text=True, timeout=10
            )
            count = 0
            if list_res.returncode == 0 and list_res.stdout:
                count = len([ln for ln in list_res.stdout.strip().split("\n") if ln.strip()])

            # Get size without shell
            size_res = subprocess.run(
                ["docker", "exec", container_name, "du", "-sh", "/battle/corpus"],
                capture_output=True, text=True, timeout=10
            )
            size = "0"
            if size_res.returncode == 0 and size_res.stdout:
                size = size_res.stdout.strip().split()[0]

            return {
                "count": count,
                "total_size": size,
                "team": team
            }

        except Exception as e:
            return {"error": str(e)}

    def sync_corpus_from_findings(self, team: str) -> int:
        """
        Sync interesting inputs from AFL++ findings to corpus (Task 10).

        This transfers new coverage-improving inputs to the corpus
        for future fuzzing runs.

        Returns:
            Number of new inputs synced
        """
        container_name = f"battle_{self.battle_id}_{team}"

        try:
            # List queue files without shell (code review fix)
            q_list = subprocess.run(
                ["docker", "exec", container_name, "ls", "-1", "/battle/findings/default/queue/"],
                capture_output=True, text=True, timeout=15
            )
            if q_list.returncode != 0:
                return 0

            # List existing corpus files
            c_list = subprocess.run(
                ["docker", "exec", container_name, "ls", "-1", "/battle/corpus/"],
                capture_output=True, text=True, timeout=15
            )

            queue_files = [ln for ln in q_list.stdout.strip().split("\n") if ln.strip()]
            corpus_files = set()
            if c_list.returncode == 0 and c_list.stdout:
                corpus_files = set(ln for ln in c_list.stdout.strip().split("\n") if ln.strip())

            # Copy new files one by one (no shell glob)
            count = 0
            for fname in queue_files:
                if fname not in corpus_files:
                    src = f"/battle/findings/default/queue/{fname}"
                    dst = f"/battle/corpus/{fname}"
                    cp_res = subprocess.run(
                        ["docker", "exec", container_name, "cp", src, dst],
                        capture_output=True, text=True, timeout=15
                    )
                    if cp_res.returncode == 0:
                        count += 1

            console.print(f"[green]Synced {count} new inputs to corpus for {team}[/green]")
            return count

        except Exception as e:
            console.print(f"[red]Failed to sync corpus: {e}[/red]")
            return 0

    def stop_qemu_instance(self, team: str) -> bool:
        """Stop a QEMU instance inside Docker container."""
        if self.mode != TwinMode.QEMU:
            return False

        container_name = f"battle_{self.battle_id}_{team}"

        # Kill QEMU process inside container
        subprocess.run(
            ["docker", "exec", container_name, "pkill", "-f", "qemu-system"],
            capture_output=True
        )

        # Stop the container
        result = subprocess.run(
            ["docker", "stop", "-t", "5", container_name],
            capture_output=True
        )
        return result.returncode == 0

    def create_golden_snapshot(self, team: str, snapshot_name: str = "golden") -> bool:
        """
        Create a golden snapshot of the QEMU state after boot.

        This is the critical optimization for fuzzing:
        - Boot once to a stable state
        - Save snapshot
        - Restore in <500ms for each fuzz iteration

        Args:
            team: Team name (red, blue, arena)
            snapshot_name: Name for the snapshot (default: golden)

        Returns:
            True if snapshot created successfully
        """
        if self.mode != TwinMode.QEMU:
            console.print("[yellow]Snapshots only available in QEMU mode[/yellow]")
            return False

        team_dir = self.worktree_base / team
        qemu_config = team_dir / "qemu.conf"

        if not qemu_config.exists():
            console.print(f"[red]QEMU config not found for {team}[/red]")
            return False

        # Read QMP port from config
        config = {}
        for line in qemu_config.read_text().strip().split('\n'):
            if '=' in line and not line.startswith('#'):
                key, val = line.split('=', 1)
                config[key] = val

        qmp_port = config.get('qmp_port', '6000')
        container_name = f"battle_{self.battle_id}_{team}"

        console.print(f"[cyan]Creating golden snapshot '{snapshot_name}' for {team}...[/cyan]")

        try:
            # QMP requires capabilities handshake before commands
            # Script that handles the full QMP protocol
            qmp_script = f'''
import socket
import json
import sys

sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
sock.settimeout(10)
sock.connect(("localhost", {qmp_port}))

# Read greeting
greeting = sock.recv(4096)

# Send capabilities
sock.send(b'{{"execute": "qmp_capabilities"}}\\n')
response = sock.recv(4096)

# Send savevm command
cmd = {{"execute": "human-monitor-command", "arguments": {{"command-line": "savevm {snapshot_name}"}}}}
sock.send((json.dumps(cmd) + "\\n").encode())
response = sock.recv(4096)

sock.close()
print("OK")
'''
            result = subprocess.run(
                ["docker", "exec", container_name, "python3", "-c", qmp_script],
                capture_output=True, text=True, timeout=30
            )

            if result.returncode != 0 or "error" in result.stdout.lower():
                console.print(f"[red]Snapshot failed: {result.stdout} {result.stderr}[/red]")
                return False

            # Record snapshot metadata
            snapshot_meta = team_dir / f".snapshot_{snapshot_name}"
            snapshot_meta.write_text(f"created={time.time()}\nname={snapshot_name}\n")

            console.print(f"  [green]Snapshot '{snapshot_name}' created for {team}[/green]")
            return True

        except subprocess.TimeoutExpired:
            console.print("[red]Snapshot creation timed out[/red]")
            return False
        except Exception as e:
            console.print(f"[red]Snapshot creation failed: {e}[/red]")
            return False

    def restore_snapshot(self, team: str, snapshot_name: str = "golden") -> bool:
        """
        Restore QEMU to a previously saved snapshot.

        Target: <500ms restore time for fast fuzzing loops.

        Args:
            team: Team name (red, blue, arena)
            snapshot_name: Name of snapshot to restore (default: golden)

        Returns:
            True if snapshot restored successfully
        """
        if self.mode != TwinMode.QEMU:
            return False

        team_dir = self.worktree_base / team
        qemu_config = team_dir / "qemu.conf"

        if not qemu_config.exists():
            return False

        # Read QMP port from config
        config = {}
        for line in qemu_config.read_text().strip().split('\n'):
            if '=' in line and not line.startswith('#'):
                key, val = line.split('=', 1)
                config[key] = val

        qmp_port = config.get('qmp_port', '6000')
        container_name = f"battle_{self.battle_id}_{team}"

        try:
            start_time = time.time()

            # QMP requires capabilities handshake before commands
            qmp_script = f'''
import socket
import json

sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
sock.settimeout(10)
sock.connect(("localhost", {qmp_port}))

# Read greeting
greeting = sock.recv(4096)

# Send capabilities
sock.send(b'{{"execute": "qmp_capabilities"}}\\n')
response = sock.recv(4096)

# Send loadvm command
cmd = {{"execute": "human-monitor-command", "arguments": {{"command-line": "loadvm {snapshot_name}"}}}}
sock.send((json.dumps(cmd) + "\\n").encode())
response = sock.recv(4096)

sock.close()
print("OK")
'''
            result = subprocess.run(
                ["docker", "exec", container_name, "python3", "-c", qmp_script],
                capture_output=True, text=True, timeout=10
            )

            restore_time_ms = (time.time() - start_time) * 1000

            if result.returncode != 0 or "error" in result.stdout.lower():
                console.print(f"[red]Restore failed: {result.stdout}[/red]")
                return False

            console.print(f"  [green]Snapshot restored in {restore_time_ms:.1f}ms[/green]")
            return True

        except Exception as e:
            console.print(f"[red]Restore failed: {e}[/red]")
            return False

    def create_qcow2_overlay(self, team: str, overlay_name: str = "patched") -> Path | None:
        """
        Create a QCOW2 overlay for Blue team patching.

        Overlays allow non-destructive modifications:
        - Original firmware preserved
        - Patches stored in overlay
        - Easy to discard/reset patches

        Args:
            team: Team name (typically "blue")
            overlay_name: Name for the overlay file

        Returns:
            Path to overlay file, or None on failure
        """
        if self.mode != TwinMode.QEMU:
            return None

        team_dir = self.worktree_base / team
        base_disk = team_dir / f"{team}_disk.qcow2"
        overlay_path = team_dir / f"{overlay_name}.qcow2"

        container_name = f"battle_{self.battle_id}_{team}"

        try:
            # Create overlay pointing to base disk
            result = subprocess.run(
                ["docker", "exec", container_name,
                 "qemu-img", "create", "-f", "qcow2",
                 "-b", str(base_disk), "-F", "qcow2",
                 str(overlay_path)],
                capture_output=True, text=True
            )

            if result.returncode == 0:
                console.print(f"  [green]Created overlay: {overlay_path.name}[/green]")
                return overlay_path
            else:
                console.print(f"[red]Overlay creation failed: {result.stderr}[/red]")
                return None

        except Exception as e:
            console.print(f"[red]Overlay creation failed: {e}[/red]")
            return None

    def get_gdb_connection_info(self, team: str) -> dict[str, Any] | None:
        """
        Get GDB connection information for a team's QEMU instance.

        Returns:
            Dict with host, port, and optional symbol file path
        """
        if self.mode != TwinMode.QEMU:
            return None

        team_dir = self.worktree_base / team
        qemu_config = team_dir / "qemu.conf"

        if not qemu_config.exists():
            return None

        # Parse config
        config = {}
        for line in qemu_config.read_text().strip().split('\n'):
            if '=' in line and not line.startswith('#'):
                key, val = line.split('=', 1)
                config[key] = val

        gdb_port = int(config.get('gdb_port', '5000'))
        machine = config.get('machine', 'arm')

        # Look for ELF file with debug symbols
        symbol_file = None
        for ext in ['.elf', '.axf', '.out']:
            candidates = list(team_dir.glob(f"*{ext}"))
            if candidates:
                symbol_file = candidates[0]
                break

        return {
            'host': 'localhost',
            'port': gdb_port,
            'machine': machine,
            'symbol_file': str(symbol_file) if symbol_file else None,
            'container': f"battle_{self.battle_id}_{team}",
        }

    def generate_gdb_script(
        self, team: str, symbol_file: Path | None = None, breakpoints: list[str] | None = None
    ) -> str:
        """
        Generate a GDB script for connecting to a team's QEMU instance.

        Args:
            team: Team name
            symbol_file: Optional ELF file with debug symbols
            breakpoints: Optional list of breakpoint locations (function names or addresses)

        Returns:
            GDB script content that can be run with 'gdb -x script.gdb'
        """
        info = self.get_gdb_connection_info(team)
        if not info:
            return ""

        # Select appropriate GDB based on architecture
        gdb_arch_map = {
            'arm': 'arm-none-eabi-gdb',
            'aarch64': 'aarch64-linux-gnu-gdb',
            'riscv64': 'riscv64-unknown-elf-gdb',
            'x86_64': 'gdb',
            'i386': 'gdb',
            'mips': 'mips-linux-gnu-gdb',
        }

        script_lines = [
            "# Auto-generated GDB script for battle skill",
            f"# Team: {team}",
            f"# Architecture: {info['machine']}",
            "",
            "set pagination off",
            "set confirm off",
            "",
            f"target remote {info['host']}:{info['port']}",
        ]

        # Load symbols if available
        sym_file = symbol_file or info.get('symbol_file')
        if sym_file:
            script_lines.extend([
                "",
                f"# Load debug symbols",
                f"file {sym_file}",
            ])

        # Add breakpoints
        if breakpoints:
            script_lines.append("")
            script_lines.append("# Breakpoints")
            for bp in breakpoints:
                script_lines.append(f"break {bp}")

        # Add useful commands
        script_lines.extend([
            "",
            "# Useful commands:",
            "# info registers - show CPU registers",
            "# x/10i $pc - disassemble at program counter",
            "# continue - resume execution",
            "# stepi - single step instruction",
        ])

        return "\n".join(script_lines)

    def test_gdb_connection(self, team: str) -> bool:
        """
        Test GDB connection to a team's QEMU instance.

        This verifies Task 6's Definition of Done:
        - GDB connects successfully
        - Registers are readable

        Returns:
            True if connection successful and registers readable
        """
        info = self.get_gdb_connection_info(team)
        if not info:
            console.print(f"[red]No GDB info for {team}[/red]")
            return False

        console.print(f"[cyan]Testing GDB connection for {team}...[/cyan]")
        console.print(f"  Target: localhost:{info['port']} (inside container)")

        container_name = info['container']

        # Run GDB inside the container where it's available
        # Connect to localhost since QEMU is in the same container
        # Using argument list instead of shell (code review fix)
        gdb_args = [
            "gdb-multiarch", "-batch",
            "-ex", f"target remote localhost:{info['port']}",
            "-ex", "info registers",
        ]

        try:
            result = subprocess.run(
                ["docker", "exec", container_name, *gdb_args],
                capture_output=True, text=True, timeout=30
            )

            if result.stdout:
                # Check if we got register output
                if any(reg in result.stdout.lower() for reg in ['r0', 'sp', 'pc', 'rax', 'eax', 'ra']):
                    console.print(f"  [green]GDB connected, registers readable[/green]")
                    # Show a sample of register output
                    lines = result.stdout.strip().split('\n')[:5]
                    for line in lines:
                        console.print(f"    {line}")
                    return True

            console.print(f"[red]GDB connection failed: {result.stderr}[/red]")
            return False

        except subprocess.TimeoutExpired:
            console.print("[red]GDB connection timed out[/red]")
            return False
        except Exception as e:
            console.print(f"[red]GDB test failed: {e}[/red]")
            return False

    def set_gdb_breakpoint(
        self, team: str, location: str, symbol_file: Path | None = None
    ) -> bool:
        """
        Set a GDB breakpoint in a team's QEMU instance.

        This supports Task 7's symbol loading:
        - Load ELF symbols if available
        - Set breakpoint on function or address
        - Verify breakpoint was set

        Args:
            team: Team name
            location: Breakpoint location (function name or address like '0x8000')
            symbol_file: Optional ELF file with symbols

        Returns:
            True if breakpoint set successfully
        """
        info = self.get_gdb_connection_info(team)
        if not info:
            return False

        container_name = info['container']

        # Build GDB command as argument list (code review fix - no shell)
        gdb_args = [
            "gdb-multiarch", "-batch",
            "-ex", f"target remote localhost:{info['port']}",
        ]

        # Load symbols if provided
        sym_file = symbol_file or info.get('symbol_file')
        if sym_file:
            # Map symbol file path to container path if needed
            container_sym = f"/battle/firmware/{Path(sym_file).name}" if sym_file else None
            if container_sym:
                gdb_args.extend(["-ex", f"file {container_sym}"])

        # Set breakpoint
        gdb_args.extend(["-ex", f"break {location}"])

        # Show breakpoints
        gdb_args.extend(["-ex", "info breakpoints"])

        try:
            result = subprocess.run(
                ["docker", "exec", container_name, *gdb_args],
                capture_output=True, text=True, timeout=30
            )

            if "Breakpoint" in result.stdout:
                console.print(f"  [green]Breakpoint set at {location}[/green]")
                return True
            else:
                console.print(f"[yellow]Breakpoint may not have been set: {result.stdout}[/yellow]")
                return False

        except Exception as e:
            console.print(f"[red]Failed to set breakpoint: {e}[/red]")
            return False

    def sync_blue_to_arena(self) -> bool:
        """Sync Blue team's patches to the arena for testing."""
        import shutil

        if self.mode == TwinMode.DOCKER:
            # Docker mode: commit blue container and recreate arena from it
            try:
                if self.blue_container and self.arena_container:
                    # Commit blue container's changes
                    new_image = f"battle_{self.battle_id}_patched:latest"
                    subprocess.run(
                        ["docker", "commit", self.blue_container, new_image],
                        capture_output=True, check=True
                    )
                    # Stop old arena
                    subprocess.run(
                        ["docker", "stop", self.arena_container],
                        capture_output=True
                    )
                    # Start new arena from patched image
                    # SECURITY: Same isolation as initial containers
                    seccomp_profile = SKILL_DIR / "docker" / "seccomp-battle.json"
                    arena_args = [
                        "docker", "run", "-d",
                        "--name", f"battle_{self.battle_id}_arena_patched",
                        "--network", f"battle_{self.battle_id}",
                        # Security hardening - COMPLETE ISOLATION FROM HOST
                        "--cap-drop", "ALL",
                        "--security-opt", "no-new-privileges",
                        "--pids-limit", "256",
                        "--memory", "512m",
                        "--memory-swap", "512m",
                        "--cpus", "1.0",
                        "--read-only",
                        "--tmpfs", "/tmp:rw,noexec,nosuid,nodev,size=64m",
                        "--tmpfs", "/workspace:rw,exec,size=256m",
                    ]
                    if seccomp_profile.exists():
                        arena_args.extend(["--security-opt", f"seccomp={seccomp_profile}"])
                    arena_args.append(new_image)

                    result = subprocess.run(arena_args, capture_output=True, text=True)
                    if result.returncode == 0:
                        self.arena_container = result.stdout.strip()
                        return True
                return False
            except Exception:
                return False

        elif self.mode == TwinMode.QEMU:
            # QEMU mode: copy patched firmware to arena
            try:
                for item in self.blue_worktree.rglob("*"):
                    if item.is_file() and not item.name.startswith('.'):
                        rel_path = item.relative_to(self.blue_worktree)
                        dest = self.arena_worktree / rel_path
                        dest.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(item, dest)
                # Restart arena QEMU if running
                self.stop_qemu_instance("arena")
                return True
            except Exception:
                return False

        elif self.mode == TwinMode.GIT_WORKTREE:
            # Git mode: cherry-pick commits
            try:
                result = self._run_git("rev-parse", "HEAD", cwd=self.blue_worktree)
                blue_commit = result.stdout.strip()
                self._run_git("cherry-pick", blue_commit, cwd=self.arena_worktree)
                return True
            except Exception:
                return False

        else:
            # Copy mode: rsync changes
            try:
                for item in self.blue_worktree.rglob("*"):
                    if item.is_file():
                        rel_path = item.relative_to(self.blue_worktree)
                        dest = self.arena_worktree / rel_path
                        dest.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(item, dest)
                return True
            except Exception:
                return False

    def cleanup(self):
        """Remove all digital twin resources."""
        import shutil
        console.print("[dim]Cleaning up digital twin...[/dim]")

        if self.mode == TwinMode.DOCKER:
            # Stop and remove containers
            for container in [self.red_container, self.blue_container, self.arena_container]:
                if container:
                    subprocess.run(["docker", "stop", container], capture_output=True)
                    subprocess.run(["docker", "rm", container], capture_output=True)
            # Remove network
            subprocess.run(
                ["docker", "network", "rm", f"battle_{self.battle_id}"],
                capture_output=True
            )
            # Remove battle images
            subprocess.run(
                ["docker", "rmi", f"battle_{self.battle_id}:latest",
                 f"battle_{self.battle_id}_patched:latest"],
                capture_output=True
            )

        elif self.mode == TwinMode.QEMU:
            # Stop all QEMU instances
            for team in list(self.qemu_processes.keys()):
                self.stop_qemu_instance(team)

        elif self.mode == TwinMode.GIT_WORKTREE:
            # Remove git worktrees
            for worktree in [self.red_worktree, self.blue_worktree, self.arena_worktree]:
                if worktree and worktree.exists():
                    self._run_git("worktree", "remove", str(worktree), "--force")
            # Remove branches
            for suffix in ["red", "blue", "arena"]:
                self._run_git("branch", "-D", f"battle/{self.battle_id}/{suffix}")

        # Remove worktree directory
        if self.worktree_base.exists():
            shutil.rmtree(self.worktree_base)

        console.print("[dim]Cleanup complete[/dim]")

    def get_red_target(self) -> Path:
        """Get the path Red team should attack."""
        return self.arena_worktree or self.source_path

    def get_blue_workspace(self) -> Path:
        """Get the path Blue team should patch."""
        return self.blue_worktree or self.source_path

    def get_arena(self) -> Path:
        """Get the arena path for testing."""
        return self.arena_worktree or self.source_path


# ============================================================================
# State Management (Externalized Memory Pattern)
# ============================================================================

class AttackType(str, Enum):
    SCAN = "scan"
    AUDIT = "audit"
    EXPLOIT = "exploit"
    INJECTION = "injection"


class DefenseType(str, Enum):
    PATCH = "patch"
    HARDEN = "harden"
    BLOCK = "block"
    VALIDATE = "validate"


@dataclass
class Finding:
    """A vulnerability or security issue found by Red Team."""
    id: str
    type: AttackType
    severity: str  # critical, high, medium, low
    description: str
    file_path: str | None = None
    line_number: int | None = None
    exploit_proof: str | None = None
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class Patch:
    """A fix generated by Blue Team."""
    id: str
    finding_id: str
    type: DefenseType
    diff: str
    verified: bool = False
    functionality_preserved: bool = False
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class RoundResult:
    """Result of a single battle round."""
    round_number: int
    red_findings: list[Finding] = field(default_factory=list)
    blue_patches: list[Patch] = field(default_factory=list)
    red_score: float = 0.0
    blue_score: float = 0.0
    duration_seconds: float = 0.0
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class BattleState:
    """Complete state of a battle - externalized memory with thread-safe access."""
    battle_id: str
    target_path: str
    max_rounds: int
    current_round: int = 0
    status: str = "pending"  # pending, running, paused, completed

    # Cumulative scores
    red_total_score: float = 0.0
    blue_total_score: float = 0.0

    # History
    rounds: list[RoundResult] = field(default_factory=list)
    all_findings: list[Finding] = field(default_factory=list)
    all_patches: list[Patch] = field(default_factory=list)

    # Metrics
    tdsr: float = 0.0  # True Defense Success Rate
    fdsr: float = 0.0  # Fake Defense Success Rate
    asc: int = 0       # Attack Success Count

    # Timestamps
    started_at: str | None = None
    completed_at: str | None = None
    last_checkpoint: str | None = None

    # Concurrent execution state
    red_active: bool = False
    blue_active: bool = False
    red_action: str = "idle"
    blue_action: str = "idle"

    # Thread safety
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def to_dict(self) -> dict:
        """Serialize to dict for JSON storage."""
        return {
            "battle_id": self.battle_id,
            "target_path": self.target_path,
            "max_rounds": self.max_rounds,
            "current_round": self.current_round,
            "status": self.status,
            "red_total_score": self.red_total_score,
            "blue_total_score": self.blue_total_score,
            "rounds": [vars(r) for r in self.rounds],
            "all_findings": [vars(f) for f in self.all_findings],
            "all_patches": [vars(p) for p in self.all_patches],
            "tdsr": self.tdsr,
            "fdsr": self.fdsr,
            "asc": self.asc,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "last_checkpoint": self.last_checkpoint,
        }

    @classmethod
    def from_dict(cls, data: dict) -> BattleState:
        """Deserialize from dict."""
        state = cls(
            battle_id=data["battle_id"],
            target_path=data["target_path"],
            max_rounds=data["max_rounds"],
            current_round=data["current_round"],
            status=data["status"],
            red_total_score=data["red_total_score"],
            blue_total_score=data["blue_total_score"],
            tdsr=data.get("tdsr", 0.0),
            fdsr=data.get("fdsr", 0.0),
            asc=data.get("asc", 0),
            started_at=data.get("started_at"),
            completed_at=data.get("completed_at"),
            last_checkpoint=data.get("last_checkpoint"),
        )
        # Reconstruct objects
        state.rounds = [RoundResult(**r) for r in data.get("rounds", [])]
        state.all_findings = [Finding(**f) for f in data.get("all_findings", [])]
        state.all_patches = [Patch(**p) for p in data.get("all_patches", [])]
        return state

    def save(self) -> Path:
        """Save state to checkpoint file."""
        BATTLES_DIR.mkdir(parents=True, exist_ok=True)
        self.last_checkpoint = datetime.now().isoformat()
        path = BATTLES_DIR / f"{self.battle_id}.json"
        path.write_text(json.dumps(self.to_dict(), indent=2))
        return path

    @classmethod
    def load(cls, battle_id: str) -> BattleState | None:
        """Load state from checkpoint file."""
        path = BATTLES_DIR / f"{battle_id}.json"
        if not path.exists():
            return None
        return cls.from_dict(json.loads(path.read_text()))


# ============================================================================
# Scoring System (AIxCC-style)
# ============================================================================

class Scorer:
    """AIxCC-style scoring system."""

    # Weights from AIxCC
    VULN_DISCOVERY = 1.0
    EXPLOIT_PROOF = 0.5
    SUCCESSFUL_PATCH = 3.0
    TIME_DECAY_FACTOR = 0.1

    SEVERITY_MULTIPLIERS = {
        "critical": 2.0,
        "high": 1.5,
        "medium": 1.0,
        "low": 0.5,
    }

    @classmethod
    def score_finding(cls, finding: Finding, round_number: int) -> float:
        """Score a Red Team finding."""
        base = cls.VULN_DISCOVERY

        # Severity multiplier
        mult = cls.SEVERITY_MULTIPLIERS.get(finding.severity, 1.0)

        # Exploit proof bonus
        if finding.exploit_proof:
            base += cls.EXPLOIT_PROOF

        # Time decay (earlier findings worth more)
        decay = 1.0 / (1.0 + cls.TIME_DECAY_FACTOR * round_number)

        return base * mult * decay

    @classmethod
    def score_patch(cls, patch: Patch, finding: Finding, round_number: int) -> float:
        """Score a Blue Team patch."""
        if not patch.verified:
            return 0.0

        base = cls.SUCCESSFUL_PATCH

        # Severity multiplier (fixing critical vulns worth more)
        mult = cls.SEVERITY_MULTIPLIERS.get(finding.severity, 1.0)

        # Functionality preserved bonus
        if patch.functionality_preserved:
            base *= 1.2

        # Time decay (faster patches worth more)
        decay = 1.0 / (1.0 + cls.TIME_DECAY_FACTOR * round_number)

        return base * mult * decay

    @classmethod
    def calculate_metrics(cls, state: BattleState) -> dict:
        """Calculate TDSR, FDSR, ASC metrics."""
        total_findings = len(state.all_findings)
        verified_patches = [p for p in state.all_patches if p.verified]
        functional_patches = [p for p in verified_patches if p.functionality_preserved]

        # TDSR: True Defense Success Rate
        tdsr = len(functional_patches) / total_findings if total_findings > 0 else 0.0

        # FDSR: Fake Defense Success Rate (patched but broke functionality)
        broken_patches = [p for p in verified_patches if not p.functionality_preserved]
        fdsr = len(broken_patches) / total_findings if total_findings > 0 else 0.0

        # ASC: Attack Success Count
        asc = total_findings

        return {"tdsr": tdsr, "fdsr": fdsr, "asc": asc}


# ============================================================================
# Red Team Agent
# ============================================================================

class RedAgent:
    """
    Red Team agent - attacks using hack skill with learning loop.

    Learning Loop (Task 19):
    1. RECALL: Query team memory for prior attack strategies
    2. RESEARCH: Use dogpile to find new attack techniques (budget limited)
    3. ATTACK: Execute attacks against the target
    4. REFLECT: Analyze what worked and what didn't
    5. STORE: Save learnings to team memory for future rounds
    """

    def __init__(self, target_path: str, state: BattleState, battle_id: str):
        self.target_path = target_path
        self.state = state
        self.hack_script = HACK_SKILL / "run.sh"

        # Team-isolated memory (Task 13)
        self.memory = BattleMemory(
            battle_id=battle_id,
            team="red",
            max_research_calls_per_round=3
        )

        # Round tracking
        self.current_round = 0
        self.round_actions: list[str] = []
        self.round_outcomes: list[str] = []
        self.round_learnings: list[str] = []

    def start_round(self, round_number: int) -> None:
        """Start a new attack round - reset tracking and budget."""
        self.current_round = round_number
        self.round_actions = []
        self.round_outcomes = []
        self.round_learnings = []
        self.memory.start_new_round(round_number)
        console.print(f"[red]Red Team: Starting round {round_number}[/red]")

    def recall_phase(self) -> dict[str, Any]:
        """
        Phase 1: RECALL - Query memory for prior attack strategies.

        Returns context from past successful attacks.
        """
        console.print("[red]Red Team: RECALL phase - checking prior strategies[/red]")

        result = self.memory.recall(
            "successful attack strategies security vulnerabilities exploits",
            k=5, threshold=0.3
        )

        if result.get("found"):
            self.round_actions.append("Recalled prior attack strategies")
            return result
        else:
            self.round_actions.append("No prior strategies found")
            return {"found": False, "items": []}

    def research_phase(self, target_info: str = "") -> dict[str, Any]:
        """
        Phase 2: RESEARCH - Use dogpile to find new attack techniques.

        Subject to per-round budget limits (Task 18).
        """
        if self.memory.get_research_budget_remaining() <= 0:
            console.print("[yellow]Red Team: Research budget exhausted[/yellow]")
            self.round_actions.append("Research skipped - budget exhausted")
            return {"success": False, "error": "budget_exhausted"}

        console.print("[red]Red Team: RESEARCH phase - finding attack techniques[/red]")

        # Construct research query based on target
        query = f"exploit techniques vulnerability {target_info}"
        result = self.memory.research(query)

        if result.get("success"):
            self.round_actions.append(f"Researched: {query}")
            # Store research results in memory
            self.memory.learn(
                problem=f"Research for round {self.current_round}: {query}",
                solution=result.get("results", "")[:2000],
                tags=["research", f"round_{self.current_round}"]
            )
        else:
            self.round_actions.append(f"Research failed: {result.get('error')}")

        return result

    def attack_phase(self, round_number: int, prior_context: dict | None = None) -> list[Finding]:
        """
        Phase 3: ATTACK - Execute attacks against the target.
        """
        console.print("[red]Red Team: ATTACK phase - executing attacks[/red]")
        findings = []

        # Run audit via hack skill
        if self.hack_script.exists():
            try:
                self.round_actions.append("Running security audit")
                result = subprocess.run(
                    [str(self.hack_script), "audit", self.target_path,
                     "--tool", "all", "--severity", "low"],
                    capture_output=True, text=True, timeout=300
                )

                # Parse findings from output
                if "Issue:" in result.stdout or "Severity:" in result.stdout:
                    finding = Finding(
                        id=f"finding_{round_number}_{len(findings)}",
                        type=AttackType.AUDIT,
                        severity="medium",
                        description=result.stdout[:500],
                        file_path=self.target_path,
                    )
                    findings.append(finding)
                    self.round_outcomes.append(f"Found vulnerability: {finding.id}")

                    # Classify finding with taxonomy (Task 15)
                    classification = self.memory.classify(finding.description)
                    if classification.get("success"):
                        finding.tags = classification.get("tags", [])

            except subprocess.TimeoutExpired:
                console.print("[yellow]Red Team: Audit timed out[/yellow]")
                self.round_outcomes.append("Audit timed out")
            except Exception as e:
                console.print(f"[red]Red Team error: {e}[/red]")
                self.round_outcomes.append(f"Error: {e}")
        else:
            self.round_actions.append("Hack skill not available")
            self.round_outcomes.append("No attacks executed")

        return findings

    def reflect_phase(self, findings: list[Finding]) -> None:
        """
        Phase 4: REFLECT - Analyze what worked and what didn't.
        """
        console.print("[red]Red Team: REFLECT phase - analyzing results[/red]")

        if findings:
            for finding in findings:
                self.round_learnings.append(
                    f"Attack {finding.type.value} succeeded: {finding.description[:100]}"
                )
        else:
            self.round_learnings.append("No vulnerabilities found this round")
            self.round_learnings.append("Consider: different attack vectors, deeper fuzzing")

    def store_phase(self, findings: list[Finding]) -> None:
        """
        Phase 5: STORE - Save learnings to team memory for future rounds.
        """
        console.print("[red]Red Team: STORE phase - saving learnings[/red]")

        # Store individual findings
        for finding in findings:
            tags = ["attack", "success", f"round_{self.current_round}"]
            if hasattr(finding, 'tags') and finding.tags:
                tags.extend(finding.tags)

            self.memory.learn(
                problem=f"Attack in round {self.current_round}",
                solution=f"{finding.type.value}: {finding.description}",
                tags=tags
            )

        # Archive complete round episode (Task 16)
        self.memory.store_round_episode(
            round_num=self.current_round,
            actions=self.round_actions,
            outcomes=self.round_outcomes,
            learnings=self.round_learnings,
            taxonomy_tags=[f"round_{self.current_round}", "red_team"]
        )

    def execute_learning_loop(self, round_number: int) -> list[Finding]:
        """
        Execute full learning loop for a round (Task 19).

        Sequence: recall → research → attack → reflect → store
        """
        self.start_round(round_number)

        # Phase 1: Recall
        prior_context = self.recall_phase()

        # Phase 2: Research (budget limited)
        research_context = self.research_phase(target_info=self.target_path)

        # Phase 3: Attack
        findings = self.attack_phase(round_number, prior_context)

        # Phase 4: Reflect
        self.reflect_phase(findings)

        # Phase 5: Store
        self.store_phase(findings)

        console.print(f"[red]Red Team: Round {round_number} complete - {len(findings)} findings[/red]")
        return findings

    # Backwards compatibility
    def recall_strategies(self) -> str | None:
        """Recall prior attack strategies from memory (legacy method)."""
        result = self.memory.recall(
            "successful attack strategies security vulnerabilities exploits"
        )
        if result.get("found"):
            return str(result.get("items", []))
        return None

    def attack(self, round_number: int) -> list[Finding]:
        """Execute attack phase (legacy method - use execute_learning_loop instead)."""
        return self.execute_learning_loop(round_number)

    def store_successful_attack(self, finding: Finding):
        """Store successful attack in memory (legacy method)."""
        self.memory.learn(
            problem=f"Successful attack: {finding.type.value}",
            solution=finding.description,
            tags=["attack", "success"]
        )


# ============================================================================
# Blue Team Agent
# ============================================================================

class BlueAgent:
    """
    Blue Team agent - defends using anvil skill with learning loop.

    Learning Loop (Task 20):
    1. RECALL: Query team memory for prior defense strategies
    2. RESEARCH: Use dogpile to find patching/hardening techniques
    3. DEFEND: Generate and apply patches for findings
    4. REFLECT: Analyze patch effectiveness
    5. STORE: Save learnings to team memory for future rounds
    """

    def __init__(self, target_path: str, state: BattleState, battle_id: str):
        self.target_path = target_path
        self.state = state
        self.anvil_script = ANVIL_SKILL / "run.sh"

        # Team-isolated memory (Task 13)
        self.memory = BattleMemory(
            battle_id=battle_id,
            team="blue",
            max_research_calls_per_round=3
        )

        # Round tracking
        self.current_round = 0
        self.round_actions: list[str] = []
        self.round_outcomes: list[str] = []
        self.round_learnings: list[str] = []

    def start_round(self, round_number: int) -> None:
        """Start a new defense round - reset tracking and budget."""
        self.current_round = round_number
        self.round_actions = []
        self.round_outcomes = []
        self.round_learnings = []
        self.memory.start_new_round(round_number)
        console.print(f"[blue]Blue Team: Starting round {round_number}[/blue]")

    def recall_phase(self, findings: list[Finding]) -> dict[str, Any]:
        """
        Phase 1: RECALL - Query memory for prior defense strategies.

        Returns context from past successful patches.
        """
        console.print("[blue]Blue Team: RECALL phase - checking prior defenses[/blue]")

        # Build query based on finding types
        finding_types = set(f.type.value for f in findings) if findings else {"vulnerability"}
        query = f"successful patches security fixes defense strategies {' '.join(finding_types)}"

        result = self.memory.recall(query, k=5, threshold=0.3)

        if result.get("found"):
            self.round_actions.append("Recalled prior defense strategies")
            return result
        else:
            self.round_actions.append("No prior defenses found")
            return {"found": False, "items": []}

    def research_phase(self, findings: list[Finding]) -> dict[str, Any]:
        """
        Phase 2: RESEARCH - Use dogpile to find patching techniques.

        Subject to per-round budget limits (Task 18).
        """
        if self.memory.get_research_budget_remaining() <= 0:
            console.print("[yellow]Blue Team: Research budget exhausted[/yellow]")
            self.round_actions.append("Research skipped - budget exhausted")
            return {"success": False, "error": "budget_exhausted"}

        console.print("[blue]Blue Team: RESEARCH phase - finding defense techniques[/blue]")

        # Construct research query based on findings
        if findings:
            finding_desc = findings[0].description[:100]
            query = f"patch fix mitigate {finding_desc}"
        else:
            query = "software hardening security best practices"

        result = self.memory.research(query)

        if result.get("success"):
            self.round_actions.append(f"Researched: {query}")
            # Store research results in memory
            self.memory.learn(
                problem=f"Defense research for round {self.current_round}",
                solution=result.get("results", "")[:2000],
                tags=["research", "defense", f"round_{self.current_round}"]
            )
        else:
            self.round_actions.append(f"Research failed: {result.get('error')}")

        return result

    def defend_phase(self, findings: list[Finding], round_number: int) -> list[Patch]:
        """
        Phase 3: DEFEND - Generate and apply patches for findings.
        """
        console.print("[blue]Blue Team: DEFEND phase - generating patches[/blue]")
        patches = []

        for finding in findings:
            self.round_actions.append(f"Patching: {finding.id}")

            if self.anvil_script.exists():
                try:
                    result = subprocess.run(
                        [str(self.anvil_script), "debug", "run",
                         "--issue", finding.description[:200]],
                        capture_output=True, text=True, timeout=300,
                        cwd=self.target_path
                    )

                    # Classify the fix with taxonomy (Task 15)
                    classification = self.memory.classify(finding.description)
                    fix_tags = classification.get("tags", []) if classification.get("success") else []

                    patch = Patch(
                        id=f"patch_{round_number}_{finding.id}",
                        finding_id=finding.id,
                        type=DefenseType.PATCH,
                        diff=result.stdout[:1000] if result.returncode == 0 else "",
                        verified=result.returncode == 0,
                        functionality_preserved=True,
                    )
                    patches.append(patch)

                    if patch.verified:
                        self.round_outcomes.append(f"Patched {finding.id} successfully")
                    else:
                        self.round_outcomes.append(f"Patch for {finding.id} needs verification")

                except subprocess.TimeoutExpired:
                    console.print("[yellow]Blue Team: Patch generation timed out[/yellow]")
                    self.round_outcomes.append(f"Patch timeout for {finding.id}")
                except Exception as e:
                    console.print(f"[red]Blue Team error: {e}[/red]")
                    self.round_outcomes.append(f"Error patching {finding.id}: {e}")
            else:
                # Fallback: create unverified patch placeholder
                patch = Patch(
                    id=f"patch_{round_number}_{finding.id}",
                    finding_id=finding.id,
                    type=DefenseType.PATCH,
                    diff="",
                    verified=False,
                )
                patches.append(patch)
                self.round_outcomes.append(f"Placeholder patch for {finding.id}")

        return patches

    def reflect_phase(self, patches: list[Patch]) -> None:
        """
        Phase 4: REFLECT - Analyze patch effectiveness.
        """
        console.print("[blue]Blue Team: REFLECT phase - analyzing patches[/blue]")

        verified_count = sum(1 for p in patches if p.verified)
        total = len(patches)

        self.round_learnings.append(f"Verified {verified_count}/{total} patches")

        if verified_count < total:
            self.round_learnings.append("Some patches need manual review")
            self.round_learnings.append("Consider: better test coverage, more research")
        else:
            self.round_learnings.append("All patches verified successfully")

    def store_phase(self, patches: list[Patch], findings: list[Finding]) -> None:
        """
        Phase 5: STORE - Save learnings to team memory for future rounds.
        """
        console.print("[blue]Blue Team: STORE phase - saving learnings[/blue]")

        # Store individual successful patches
        for patch in patches:
            if patch.verified:
                tags = ["defense", "success", f"round_{self.current_round}"]
                self.memory.learn(
                    problem=f"Vulnerability patched: {patch.finding_id}",
                    solution=f"Patch applied: {patch.diff[:500]}",
                    tags=tags
                )

        # Archive complete round episode (Task 16)
        self.memory.store_round_episode(
            round_num=self.current_round,
            actions=self.round_actions,
            outcomes=self.round_outcomes,
            learnings=self.round_learnings,
            taxonomy_tags=[f"round_{self.current_round}", "blue_team"]
        )

    def execute_learning_loop(self, findings: list[Finding], round_number: int) -> list[Patch]:
        """
        Execute full learning loop for a round (Task 20).

        Sequence: recall → research → defend → reflect → store
        """
        self.start_round(round_number)

        # Phase 1: Recall
        prior_context = self.recall_phase(findings)

        # Phase 2: Research (budget limited)
        research_context = self.research_phase(findings)

        # Phase 3: Defend
        patches = self.defend_phase(findings, round_number)

        # Phase 4: Reflect
        self.reflect_phase(patches)

        # Phase 5: Store
        self.store_phase(patches, findings)

        verified = sum(1 for p in patches if p.verified)
        console.print(f"[blue]Blue Team: Round {round_number} complete - {verified}/{len(patches)} patches verified[/blue]")
        return patches

    # Backwards compatibility
    def recall_defenses(self) -> str | None:
        """Recall prior defense strategies from memory (legacy method)."""
        result = self.memory.recall(
            "successful patches security fixes defense strategies"
        )
        if result.get("found"):
            return str(result.get("items", []))
        return None

    def defend(self, findings: list[Finding], round_number: int) -> list[Patch]:
        """Generate patches for findings (legacy method - use execute_learning_loop instead)."""
        return self.execute_learning_loop(findings, round_number)

    def store_successful_defense(self, patch: Patch):
        """Store successful defense in memory (legacy method)."""
        self.memory.learn(
            problem=f"Successful defense: {patch.finding_id}",
            solution=f"Patch: {patch.diff[:500]}",
            tags=["defense", "success"]
        )


# ============================================================================
# Task Monitor Integration
# ============================================================================

class TaskMonitor:
    """Integration with task-monitor skill."""

    def __init__(self, battle_id: str, total_rounds: int):
        self.battle_id = battle_id
        self.total_rounds = total_rounds
        self.monitor_script = TASK_MONITOR_SKILL / "run.sh"
        self.state_file = BATTLES_DIR / f"{battle_id}_progress.json"

    def register(self) -> bool:
        """Register battle with task-monitor."""
        if not self.monitor_script.exists():
            return False

        try:
            result = subprocess.run(
                [str(self.monitor_script), "register",
                 "--name", f"battle:{self.battle_id}",
                 "--total", str(self.total_rounds),
                 "--state", str(self.state_file)],
                capture_output=True, text=True, timeout=30
            )
            return result.returncode == 0
        except Exception:
            return False

    def update(self, current_round: int, red_score: float, blue_score: float):
        """Update progress in task-monitor."""
        # Write state file that task-monitor polls
        BATTLES_DIR.mkdir(parents=True, exist_ok=True)
        state = {
            "current": current_round,
            "total": self.total_rounds,
            "red_score": red_score,
            "blue_score": blue_score,
            "leader": "Red" if red_score > blue_score else "Blue",
            "updated": datetime.now().isoformat(),
        }
        self.state_file.write_text(json.dumps(state))


# ============================================================================
# Game Loop Orchestrator
# ============================================================================

class BattleOrchestrator:
    """Main game loop orchestrator with concurrent Red/Blue team execution."""

    def __init__(
        self,
        target_path: str,
        max_rounds: int = 1000,
        concurrent: bool = True,
        twin_mode: TwinMode | None = None,
        qemu_machine: str | None = None,
        docker_image: str | None = None,
    ):
        self.battle_id = f"battle_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        self.target_path = str(Path(target_path).resolve())
        self.max_rounds = max_rounds
        self.concurrent = concurrent

        # Initialize state
        self.state = BattleState(
            battle_id=self.battle_id,
            target_path=self.target_path,
            max_rounds=max_rounds,
        )

        # Create digital twin with specified mode
        self.digital_twin = DigitalTwin(
            self.target_path,
            self.battle_id,
            mode=twin_mode,
            qemu_machine=qemu_machine,
            docker_image=docker_image,
        )

        # Initialize agents (will be set after twin setup)
        self.red_agent: RedAgent | None = None
        self.blue_agent: BlueAgent | None = None

        # Initialize task monitor
        self.monitor = TaskMonitor(self.battle_id, max_rounds)

        # Termination tracking
        self.null_rounds = 0
        self.stable_rounds = 0
        self.last_scores = (0.0, 0.0)

        # Concurrent execution
        self.finding_queue: queue.Queue[Finding] = queue.Queue()
        self.patch_queue: queue.Queue[Patch] = queue.Queue()
        self.stop_event = threading.Event()

    def setup_digital_twin(self) -> bool:
        """Set up the digital twin and initialize agents."""
        if not self.digital_twin.setup():
            console.print("[red]Failed to create digital twin[/red]")
            return False

        # Red team attacks the arena
        red_target = str(self.digital_twin.get_red_target())
        # Blue team patches their workspace
        blue_workspace = str(self.digital_twin.get_blue_workspace())

        self.red_agent = RedAgent(red_target, self.state, self.battle_id)
        self.blue_agent = BlueAgent(blue_workspace, self.state, self.battle_id)

        console.print(f"[green]Digital twin ready[/green]")
        console.print(f"  Red attacks: {red_target}")
        console.print(f"  Blue defends: {blue_workspace}")

        return True

    def save_full_checkpoint(self, round_num: int) -> bool:
        """
        Save full battle checkpoint including QEMU snapshots AND team memories (Task 22).

        Checkpoint includes:
        - Battle state (scores, findings, patches)
        - QEMU snapshots for all teams (if QEMU mode)
        - Team memory states are already in memory skill collections

        This allows resuming battles from any checkpoint.
        """
        console.print(f"[cyan]Creating full checkpoint at round {round_num}...[/cyan]")

        # 1. Save battle state
        self.state.save()

        # 2. Save QEMU snapshots if in QEMU mode
        if self.digital_twin.mode == TwinMode.QEMU:
            snapshot_name = f"checkpoint_round_{round_num}"
            for team in ["red", "blue", "arena"]:
                try:
                    success = self.digital_twin.create_golden_snapshot(team, snapshot_name)
                    if success:
                        console.print(f"  [green]Saved {team} QEMU snapshot[/green]")
                    else:
                        console.print(f"  [yellow]Could not save {team} snapshot (QEMU may not be running)[/yellow]")
                except Exception as e:
                    console.print(f"  [red]Error saving {team} snapshot: {e}[/red]")

        # 3. Save checkpoint metadata
        checkpoint_meta = {
            "battle_id": self.battle_id,
            "round": round_num,
            "timestamp": datetime.now().isoformat(),
            "mode": self.digital_twin.mode.value,
            "red_score": self.state.red_total_score,
            "blue_score": self.state.blue_total_score,
            "findings_count": len(self.state.all_findings),
            "patches_count": len(self.state.all_patches),
        }

        checkpoint_file = BATTLES_DIR / f"{self.battle_id}_checkpoint_{round_num}.json"
        checkpoint_file.write_text(json.dumps(checkpoint_meta, indent=2))

        console.print(f"  [green]Checkpoint saved: {checkpoint_file.name}[/green]")
        return True

    def restore_from_checkpoint(self, checkpoint_file: Path) -> bool:
        """
        Restore battle from a checkpoint file.

        Restores:
        - Battle state
        - QEMU snapshots (if QEMU mode)
        - Team memories are already in memory skill (no restore needed)

        Args:
            checkpoint_file: Path to checkpoint metadata JSON

        Returns:
            True if restore successful
        """
        if not checkpoint_file.exists():
            console.print(f"[red]Checkpoint not found: {checkpoint_file}[/red]")
            return False

        console.print(f"[cyan]Restoring from checkpoint: {checkpoint_file.name}[/cyan]")

        # Load checkpoint metadata
        checkpoint_meta = json.loads(checkpoint_file.read_text())
        round_num = checkpoint_meta["round"]

        # Restore QEMU snapshots if in QEMU mode
        if checkpoint_meta.get("mode") == "qemu":
            snapshot_name = f"checkpoint_round_{round_num}"
            for team in ["red", "blue", "arena"]:
                try:
                    success = self.digital_twin.restore_snapshot(team, snapshot_name)
                    if success:
                        console.print(f"  [green]Restored {team} QEMU snapshot[/green]")
                except Exception as e:
                    console.print(f"  [yellow]Could not restore {team} snapshot: {e}[/yellow]")

        # Load battle state
        state_file = BATTLES_DIR / f"{checkpoint_meta['battle_id']}.json"
        if state_file.exists():
            self.state = BattleState.load(checkpoint_meta['battle_id'])
            console.print(f"  [green]Battle state restored at round {self.state.current_round}[/green]")
        else:
            console.print(f"  [yellow]State file not found, using checkpoint metadata[/yellow]")

        # Note: Team memories don't need restoration - they're already in memory skill
        console.print(f"  [dim]Team memories preserved in memory skill collections[/dim]")

        return True

    def should_terminate(self) -> tuple[bool, str]:
        """Check termination conditions."""
        if self.null_rounds >= 3:
            return True, "Null production (no new findings for 3 rounds)"
        if self.state.current_round >= self.max_rounds:
            return True, "Maximum rounds reached"
        if self.stable_rounds >= 5:
            return True, "Metric convergence (scores stable for 5 rounds)"
        return False, ""

    def red_team_worker(self, round_num: int) -> list[Finding]:
        """Red team thread worker - continuous attack."""
        with self.state._lock:
            self.state.red_active = True
            self.state.red_action = "scanning"

        findings = self.red_agent.attack(round_num)

        with self.state._lock:
            self.state.red_action = f"found {len(findings)} vulns"
            for finding in findings:
                self.state.all_findings.append(finding)
                self.finding_queue.put(finding)  # Send to Blue team

        with self.state._lock:
            self.state.red_active = False
            self.state.red_action = "idle"

        return findings

    def blue_team_worker(self, findings: list[Finding], round_num: int) -> list[Patch]:
        """Blue team thread worker - continuous defense."""
        with self.state._lock:
            self.state.blue_active = True
            self.state.blue_action = "analyzing"

        patches = self.blue_agent.defend(findings, round_num)

        with self.state._lock:
            self.state.blue_action = f"patched {len([p for p in patches if p.verified])}"
            for patch in patches:
                self.state.all_patches.append(patch)

        with self.state._lock:
            self.state.blue_active = False
            self.state.blue_action = "idle"

        return patches

    def run_round_concurrent(self, round_num: int) -> RoundResult:
        """Execute a single battle round with concurrent Red/Blue execution."""
        start_time = time.time()

        # Run both teams concurrently
        with ThreadPoolExecutor(max_workers=2, thread_name_prefix="battle") as executor:
            # Start Red team attack
            red_future = executor.submit(self.red_team_worker, round_num)

            # Wait for Red to find something, then Blue responds
            findings = red_future.result(timeout=300)

            # Blue team responds to findings
            if findings:
                blue_future = executor.submit(self.blue_team_worker, findings, round_num)
                patches = blue_future.result(timeout=300)

                # Sync Blue's patches to arena for testing
                if patches:
                    self.digital_twin.sync_blue_to_arena()
            else:
                patches = []

        # Scoring
        red_score = sum(Scorer.score_finding(f, round_num) for f in findings)
        blue_score = sum(
            Scorer.score_patch(p, next((f for f in findings if f.id == p.finding_id), findings[0]), round_num)
            for p in patches if patches
        ) if findings else 0.0

        # Update state (thread-safe)
        with self.state._lock:
            self.state.red_total_score += red_score
            self.state.blue_total_score += blue_score
            self.state.current_round = round_num

        # Track termination conditions
        if not findings:
            self.null_rounds += 1
        else:
            self.null_rounds = 0

        current_scores = (red_score, blue_score)
        if abs(red_score - self.last_scores[0]) < 0.01 and abs(blue_score - self.last_scores[1]) < 0.01:
            self.stable_rounds += 1
        else:
            self.stable_rounds = 0
        self.last_scores = current_scores

        result = RoundResult(
            round_number=round_num,
            red_findings=findings,
            blue_patches=patches,
            red_score=red_score,
            blue_score=blue_score,
            duration_seconds=time.time() - start_time,
        )

        with self.state._lock:
            self.state.rounds.append(result)

        return result

    def run_round_sequential(self, round_num: int) -> RoundResult:
        """Execute a single battle round sequentially (fallback)."""
        start_time = time.time()

        # Red Team Attack
        findings = self.red_agent.attack(round_num)
        for finding in findings:
            self.state.all_findings.append(finding)

        # Blue Team Defense
        patches = self.blue_agent.defend(findings, round_num)
        for patch in patches:
            self.state.all_patches.append(patch)

        # Scoring
        red_score = sum(Scorer.score_finding(f, round_num) for f in findings)
        blue_score = sum(
            Scorer.score_patch(p, next((f for f in findings if f.id == p.finding_id), findings[0]), round_num)
            for p in patches if patches
        ) if findings else 0.0

        self.state.red_total_score += red_score
        self.state.blue_total_score += blue_score
        self.state.current_round = round_num

        if not findings:
            self.null_rounds += 1
        else:
            self.null_rounds = 0

        result = RoundResult(
            round_number=round_num,
            red_findings=findings,
            blue_patches=patches,
            red_score=red_score,
            blue_score=blue_score,
            duration_seconds=time.time() - start_time,
        )
        self.state.rounds.append(result)

        return result

    def generate_live_display(self) -> Table:
        """Generate live battle status display."""
        table = Table(title=f"Battle: {self.battle_id}", expand=True)
        table.add_column("Team", style="bold")
        table.add_column("Status")
        table.add_column("Action")
        table.add_column("Score", justify="right")

        red_status = "[green]ACTIVE[/green]" if self.state.red_active else "[dim]idle[/dim]"
        blue_status = "[green]ACTIVE[/green]" if self.state.blue_active else "[dim]idle[/dim]"

        table.add_row(
            "[red]Red Team[/red]",
            red_status,
            self.state.red_action,
            f"{self.state.red_total_score:.1f}"
        )
        table.add_row(
            "[blue]Blue Team[/blue]",
            blue_status,
            self.state.blue_action,
            f"{self.state.blue_total_score:.1f}"
        )

        return table

    def run(self, checkpoint_interval: int = 10) -> BattleState:
        """Run the full battle with concurrent Red/Blue team execution."""
        console.print(Panel(
            f"[bold]Battle: {self.battle_id}[/bold]\n"
            f"Target: {self.target_path}\n"
            f"Max Rounds: {self.max_rounds}\n"
            f"Mode: {'Concurrent' if self.concurrent else 'Sequential'}\n"
            f"Twin Mode: {self.digital_twin.mode.value}",
            title="Battle Starting"
        ))

        # Set up digital twin (creates isolated copies for each team)
        if not self.setup_digital_twin():
            self.state.status = "failed"
            self.state.save()
            console.print("[red]Battle aborted: Failed to create digital twin[/red]")
            return self.state

        # Register with task monitor
        self.monitor.register()

        # Set start time
        self.state.started_at = datetime.now().isoformat()
        self.state.status = "running"
        self.state.save()

        try:
            with Live(self.generate_live_display(), refresh_per_second=2, console=console) as live:
                while True:
                    # Check termination
                    should_stop, reason = self.should_terminate()
                    if should_stop:
                        live.stop()
                        console.print(f"\n[yellow]Battle ending: {reason}[/yellow]")
                        break

                    round_num = self.state.current_round + 1

                    # Run round (concurrent or sequential)
                    if self.concurrent:
                        result = self.run_round_concurrent(round_num)
                    else:
                        result = self.run_round_sequential(round_num)

                    # Update live display
                    live.update(self.generate_live_display())

                    # Log round summary
                    console.print(
                        f"[dim]Round {round_num}: "
                        f"Red +{result.red_score:.1f} ({len(result.red_findings)} finds) | "
                        f"Blue +{result.blue_score:.1f} ({len(result.blue_patches)} patches)[/dim]"
                    )

                    # Update task monitor
                    self.monitor.update(
                        self.state.current_round,
                        self.state.red_total_score,
                        self.state.blue_total_score
                    )

                    # Checkpoint (Task 22: includes QEMU snapshots + memories)
                    if self.state.current_round % checkpoint_interval == 0:
                        self.save_full_checkpoint(self.state.current_round)

        except KeyboardInterrupt:
            console.print("\n[yellow]Battle paused by user[/yellow]")
            self.state.status = "paused"
            self.state.save()
            return self.state

        # Battle complete
        self.state.status = "completed"
        self.state.completed_at = datetime.now().isoformat()

        # Calculate final metrics
        metrics = Scorer.calculate_metrics(self.state)
        self.state.tdsr = metrics["tdsr"]
        self.state.fdsr = metrics["fdsr"]
        self.state.asc = metrics["asc"]

        self.state.save()

        # Declare winner
        winner = "Red Team" if self.state.red_total_score > self.state.blue_total_score else "Blue Team"
        margin = abs(self.state.red_total_score - self.state.blue_total_score)

        console.print(Panel(
            f"[bold green]Winner: {winner}[/bold green] (margin: {margin:.1f})\n\n"
            f"[red]Red Total: {self.state.red_total_score:.1f}[/red]\n"
            f"[blue]Blue Total: {self.state.blue_total_score:.1f}[/blue]\n\n"
            f"TDSR: {self.state.tdsr:.1%}\n"
            f"Total Findings: {len(self.state.all_findings)}\n"
            f"Verified Patches: {len([p for p in self.state.all_patches if p.verified])}\n"
            f"Rounds: {self.state.current_round}",
            title="Battle Complete"
        ))

        # Cleanup digital twin (remove worktrees, containers, etc.)
        self.digital_twin.cleanup()

        return self.state


# ============================================================================
# Report Generation
# ============================================================================

def generate_report(state: BattleState) -> str:
    """Generate battle report."""
    winner = "Red Team" if state.red_total_score > state.blue_total_score else "Blue Team"
    margin = abs(state.red_total_score - state.blue_total_score)

    report = f"""# Battle Report: {state.battle_id}

## Executive Summary

**Winner: {winner}** (margin: {margin:.1f} points)

| Metric | Value |
|--------|-------|
| Total Rounds | {state.current_round} |
| Red Team Score | {state.red_total_score:.1f} |
| Blue Team Score | {state.blue_total_score:.1f} |
| TDSR (True Defense Success Rate) | {state.tdsr:.1%} |
| FDSR (Fake Defense Success Rate) | {state.fdsr:.1%} |
| ASC (Attack Success Count) | {state.asc} |

## Battle Timeline

| Started | Completed | Duration |
|---------|-----------|----------|
| {state.started_at or 'N/A'} | {state.completed_at or 'N/A'} | {state.current_round} rounds |

## Vulnerability Summary

Total Vulnerabilities Found: {len(state.all_findings)}
Total Patches Generated: {len(state.all_patches)}
Verified Patches: {len([p for p in state.all_patches if p.verified])}

### By Severity

| Severity | Count |
|----------|-------|
| Critical | {len([f for f in state.all_findings if f.severity == 'critical'])} |
| High | {len([f for f in state.all_findings if f.severity == 'high'])} |
| Medium | {len([f for f in state.all_findings if f.severity == 'medium'])} |
| Low | {len([f for f in state.all_findings if f.severity == 'low'])} |

## Round-by-Round Summary

| Round | Red Findings | Blue Patches | Red Score | Blue Score |
|-------|--------------|--------------|-----------|------------|
"""

    for r in state.rounds[:20]:  # First 20 rounds
        report += f"| {r.round_number} | {len(r.red_findings)} | {len(r.blue_patches)} | {r.red_score:.1f} | {r.blue_score:.1f} |\n"

    if len(state.rounds) > 20:
        report += f"| ... | ({len(state.rounds) - 20} more rounds) | ... | ... | ... |\n"

    report += f"""

## Recommendations

1. **{"Improve defenses" if state.red_total_score > state.blue_total_score else "Maintain defensive posture"}** - {"Red team dominated, consider security hardening" if state.red_total_score > state.blue_total_score else "Blue team successfully defended most attacks"}

2. **Focus Areas**: Based on findings, prioritize fixes for {state.all_findings[0].type.value if state.all_findings else "N/A"} vulnerabilities

3. **Next Steps**: {"Run another battle after implementing fixes" if state.red_total_score > state.blue_total_score else "Consider expanding attack surface for Red team"}

---
Generated: {datetime.now().isoformat()}
"""

    return report


# ============================================================================
# CLI Commands
# ============================================================================

@app.command()
def battle(
    target: str = typer.Argument(".", help="Target directory, firmware file, or Docker image"),
    rounds: int = typer.Option(100, help="Maximum number of rounds"),
    overnight: bool = typer.Option(False, help="Run as overnight job (1000 rounds, checkpoints every 50)"),
    checkpoint_interval: int = typer.Option(10, help="Checkpoint every N rounds"),
    mode: str = typer.Option(None, help="Digital twin mode: git_worktree, docker, qemu, copy"),
    docker_image: str = typer.Option(None, help="Docker image for container battles (e.g., nginx:latest)"),
    qemu_machine: str = typer.Option(None, help="QEMU machine type (e.g., arm, riscv64, x86_64)"),
):
    """
    Start a Red vs Blue team battle.

    DIGITAL TWIN MODES:

    1. Source Code (git_worktree): Battle over a git repository
       ./run.sh battle /path/to/repo

    2. Docker Container (docker): Battle over a containerized app
       ./run.sh battle --docker-image nginx:latest
       ./run.sh battle /path/with/Dockerfile

    3. Firmware/MCU (qemu): Battle over microprocessor firmware
       ./run.sh battle firmware.bin --qemu-machine arm
       ./run.sh battle firmware.elf

    Red Team attacks using hack skill.
    Blue Team defends using anvil skill.
    Both teams leverage memory for strategy recall.
    """
    if overnight:
        rounds = 1000
        checkpoint_interval = 50
        console.print("[yellow]Overnight mode: 1000 rounds, checkpoints every 50[/yellow]")

    # Parse mode
    twin_mode = None
    if mode:
        try:
            twin_mode = TwinMode(mode)
        except ValueError:
            console.print(f"[red]Invalid mode: {mode}[/red]")
            console.print(f"[yellow]Valid modes: {', '.join(m.value for m in TwinMode)}[/yellow]")
            raise typer.Exit(1)

    # Handle Docker image as target
    if docker_image and target == ".":
        # Use ops-docker skill directory as placeholder
        target_path = Path.cwd()
    else:
        target_path = Path(target).resolve()
        if not target_path.exists():
            console.print(f"[red]Target not found: {target}[/red]")
            raise typer.Exit(1)

    orchestrator = BattleOrchestrator(
        str(target_path),
        rounds,
        twin_mode=twin_mode,
        qemu_machine=qemu_machine,
        docker_image=docker_image,
    )
    state = orchestrator.run(checkpoint_interval)

    # Generate and save report
    report = generate_report(state)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    report_path = REPORTS_DIR / f"{state.battle_id}.md"
    report_path.write_text(report)
    console.print(f"\n[green]Report saved: {report_path}[/green]")


@app.command()
def status():
    """Check status of running or recent battles."""
    BATTLES_DIR.mkdir(parents=True, exist_ok=True)

    battles = list(BATTLES_DIR.glob("battle_*.json"))
    if not battles:
        console.print("[yellow]No battles found[/yellow]")
        return

    table = Table(title="Battle Status")
    table.add_column("Battle ID")
    table.add_column("Status")
    table.add_column("Round")
    table.add_column("Red Score")
    table.add_column("Blue Score")
    table.add_column("Leader")

    for battle_file in sorted(battles, reverse=True)[:10]:
        try:
            state = BattleState.load(battle_file.stem)
            if state:
                leader = "Red" if state.red_total_score > state.blue_total_score else "Blue"
                table.add_row(
                    state.battle_id,
                    state.status,
                    f"{state.current_round}/{state.max_rounds}",
                    f"{state.red_total_score:.1f}",
                    f"{state.blue_total_score:.1f}",
                    leader
                )
        except Exception:
            pass

    console.print(table)


@app.command()
def resume(
    battle_id: str = typer.Argument(..., help="Battle ID to resume"),
):
    """Resume a paused battle."""
    state = BattleState.load(battle_id)
    if not state:
        console.print(f"[red]Battle not found: {battle_id}[/red]")
        raise typer.Exit(1)

    if state.status == "completed":
        console.print(f"[yellow]Battle already completed[/yellow]")
        return

    console.print(f"[green]Resuming battle from round {state.current_round}[/green]")

    # Recreate orchestrator with existing state
    orchestrator = BattleOrchestrator(state.target_path, state.max_rounds)
    orchestrator.state = state
    orchestrator.battle_id = state.battle_id

    # Continue battle
    final_state = orchestrator.run()

    # Generate report
    report = generate_report(final_state)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    report_path = REPORTS_DIR / f"{final_state.battle_id}.md"
    report_path.write_text(report)
    console.print(f"\n[green]Report saved: {report_path}[/green]")


@app.command()
def report(
    battle_id: str = typer.Argument(..., help="Battle ID to generate report for"),
):
    """Generate report for a completed battle."""
    state = BattleState.load(battle_id)
    if not state:
        console.print(f"[red]Battle not found: {battle_id}[/red]")
        raise typer.Exit(1)

    report_content = generate_report(state)

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    report_path = REPORTS_DIR / f"{battle_id}.md"
    report_path.write_text(report_content)

    console.print(report_content)
    console.print(f"\n[green]Report saved: {report_path}[/green]")


@app.command()
def stop(
    battle_id: str = typer.Argument(..., help="Battle ID to stop"),
):
    """Stop a running battle (kill switch)."""
    state = BattleState.load(battle_id)
    if not state:
        console.print(f"[red]Battle not found: {battle_id}[/red]")
        raise typer.Exit(1)

    state.status = "paused"
    state.save()
    console.print(f"[yellow]Battle {battle_id} stopped[/yellow]")


if __name__ == "__main__":
    app()
