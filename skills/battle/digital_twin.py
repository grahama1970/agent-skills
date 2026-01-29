"""
Battle Skill - Digital Twin
Creates isolated copies of the target for Red/Blue team battles.
Supports git worktree, Docker, QEMU, and copy modes.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from rich.console import Console

from config import SKILL_DIR, WORKTREES_DIR, FIRMWARE_EXTENSIONS
from state import TwinMode

console = Console()


class DigitalTwin:
    """
    Creates isolated copies of the target for Red/Blue team battles.

    Supports git worktree, Docker, QEMU (via qemu_support), and copy modes.
    """

    def __init__(
        self,
        source_path: str,
        battle_id: str,
        mode: TwinMode | None = None,
        qemu_machine: str | None = None,
        docker_image: str | None = None,
    ):
        self.source_path = Path(source_path).resolve()
        self.battle_id = battle_id
        self.worktree_base = WORKTREES_DIR / battle_id

        self.qemu_machine = qemu_machine
        self.docker_image = docker_image
        self.mode = mode or self._detect_mode()

        self.red_worktree: Path | None = None
        self.blue_worktree: Path | None = None
        self.arena_worktree: Path | None = None

        self.red_container: str | None = None
        self.blue_container: str | None = None
        self.arena_container: str | None = None

        self.qemu_processes: dict[str, subprocess.Popen] = {}
        self._is_git_repo = self._check_git_repo()

    def _check_git_repo(self) -> bool:
        """Check if source is a git repository."""
        check_dir = self.source_path if self.source_path.is_dir() else self.source_path.parent
        result = subprocess.run(["git", "rev-parse", "--git-dir"], cwd=check_dir, capture_output=True)
        return result.returncode == 0

    def _detect_mode(self) -> TwinMode:
        """Auto-detect the appropriate twin mode based on target."""
        if self.docker_image:
            return TwinMode.DOCKER
        if self.qemu_machine:
            return TwinMode.QEMU
        if self.source_path.is_file() and self.source_path.suffix.lower() in FIRMWARE_EXTENSIONS:
            return TwinMode.QEMU
        if self.source_path.is_dir() and (self.source_path / "Dockerfile").exists():
            return TwinMode.DOCKER
        if self._check_git_repo():
            return TwinMode.GIT_WORKTREE
        return TwinMode.COPY

    def _run_git(self, *args, cwd: Path | None = None) -> subprocess.CompletedProcess:
        """Run a git command."""
        return subprocess.run(["git", *args], cwd=cwd or self.source_path, capture_output=True, text=True)

    def setup(self) -> bool:
        """Create the digital twin based on detected/configured mode."""
        console.print(f"[cyan]Creating digital twin (mode: {self.mode.value})...[/cyan]")
        if self.mode == TwinMode.DOCKER:
            return self._setup_docker_mode()
        elif self.mode == TwinMode.QEMU:
            return self._setup_qemu_mode()
        elif self.mode == TwinMode.GIT_WORKTREE and self._is_git_repo:
            return self._setup_git_mode()
        return self._setup_copy_mode()

    def _setup_git_mode(self) -> bool:
        """Create git worktree-based digital twin."""
        self.worktree_base.mkdir(parents=True, exist_ok=True)
        battle_branches = [f"battle/{self.battle_id}/{t}" for t in ["red", "blue", "arena"]]
        try:
            for branch in battle_branches:
                self._run_git("branch", branch)
            self.red_worktree = self.worktree_base / "red"
            self.blue_worktree = self.worktree_base / "blue"
            self.arena_worktree = self.worktree_base / "arena"
            for wt, br in zip([self.red_worktree, self.blue_worktree, self.arena_worktree], battle_branches):
                self._run_git("worktree", "add", str(wt), br)
            console.print(f"  [green]Created git worktrees in {self.worktree_base}[/green]")
            return True
        except Exception as e:
            console.print(f"[red]Failed to create worktrees: {e}[/red]")
            return False

    def _setup_copy_mode(self) -> bool:
        """Fallback: create copies instead of worktrees."""
        self.worktree_base.mkdir(parents=True, exist_ok=True)
        self.red_worktree = self.worktree_base / "red"
        self.blue_worktree = self.worktree_base / "blue"
        self.arena_worktree = self.worktree_base / "arena"
        ignore = shutil.ignore_patterns('.git', '__pycache__', '*.pyc', 'worktrees', 'battles', 'reports')
        try:
            for wt in [self.red_worktree, self.blue_worktree, self.arena_worktree]:
                if wt.exists():
                    shutil.rmtree(wt)
                shutil.copytree(self.source_path, wt, ignore=ignore)
            console.print(f"  [green]Created copies in {self.worktree_base}[/green]")
            return True
        except Exception as e:
            console.print(f"[red]Failed to create copies: {e}[/red]")
            return False

    def _setup_docker_mode(self) -> bool:
        """Create Docker container-based digital twin."""
        try:
            network_name = f"battle_{self.battle_id}"
            subprocess.run(["docker", "network", "create", network_name], capture_output=True, check=False)
            image = self.docker_image
            if not image and (self.source_path / "Dockerfile").exists():
                image = f"battle_{self.battle_id}:latest"
                result = subprocess.run(["docker", "build", "-t", image, str(self.source_path)], capture_output=True)
                if result.returncode != 0:
                    console.print(f"[red]Docker build failed[/red]")
                    return False
            if not image:
                console.print("[red]No Docker image or Dockerfile found[/red]")
                return False
            seccomp = SKILL_DIR / "docker" / "seccomp-battle.json"
            for team, attr in [("red", "red_container"), ("blue", "blue_container"), ("arena", "arena_container")]:
                name = f"battle_{self.battle_id}_{team}"
                args = ["docker", "run", "-d", "--name", name, "--network", network_name,
                        "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
                        "--pids-limit", "256", "--memory", "512m", "--read-only",
                        "--tmpfs", "/tmp:rw,noexec,nosuid,size=64m", "--label", f"battle_team={team}"]
                if seccomp.exists():
                    args.extend(["--security-opt", f"seccomp={seccomp}"])
                args.append(image)
                result = subprocess.run(args, capture_output=True, text=True)
                if result.returncode == 0:
                    setattr(self, attr, result.stdout.strip())
                else:
                    return False
            self._setup_worktree_dirs()
            return True
        except Exception as e:
            console.print(f"[red]Docker setup failed: {e}[/red]")
            return False

    def _setup_qemu_mode(self) -> bool:
        """Create QEMU emulation-based digital twin."""
        from qemu_support import detect_qemu_machine
        machine = self.qemu_machine or detect_qemu_machine(self.source_path)
        if not machine:
            console.print("[red]Cannot determine QEMU machine type[/red]")
            return False
        if subprocess.run(["docker", "info"], capture_output=True).returncode != 0:
            console.print("[red]Docker not available[/red]")
            return False
        self.worktree_base.mkdir(parents=True, exist_ok=True)
        try:
            network_name = f"battle_{self.battle_id}"
            subprocess.run(["docker", "network", "create", network_name], capture_output=True, check=False)
            for team in ["red", "blue", "arena"]:
                team_dir = self.worktree_base / team
                team_dir.mkdir(exist_ok=True)
                if self.source_path.is_file():
                    shutil.copy2(self.source_path, team_dir / self.source_path.name)
                    fw_name = self.source_path.name
                else:
                    fw_dest = team_dir / "firmware"
                    if fw_dest.exists():
                        shutil.rmtree(fw_dest)
                    shutil.copytree(self.source_path, fw_dest, ignore=shutil.ignore_patterns('.git'))
                    fw_name = "firmware"
                gdb_port = 5000 + hash(f'{self.battle_id}_{team}') % 1000
                (team_dir / "qemu.conf").write_text(f"machine={machine}\nfirmware={fw_name}\ngdb_port={gdb_port}\n")
            self._setup_worktree_dirs()
            console.print(f"  [green]QEMU mode ready: {machine}[/green]")
            return True
        except Exception as e:
            console.print(f"[red]QEMU setup failed: {e}[/red]")
            return False

    def _setup_worktree_dirs(self):
        """Set up worktree directory paths."""
        self.worktree_base.mkdir(parents=True, exist_ok=True)
        self.red_worktree = self.worktree_base / "red"
        self.blue_worktree = self.worktree_base / "blue"
        self.arena_worktree = self.worktree_base / "arena"
        for wt in [self.red_worktree, self.blue_worktree, self.arena_worktree]:
            wt.mkdir(exist_ok=True)

    def sync_blue_to_arena(self) -> bool:
        """Sync Blue team's patches to the arena for testing."""
        if self.mode == TwinMode.GIT_WORKTREE:
            try:
                result = self._run_git("rev-parse", "HEAD", cwd=self.blue_worktree)
                self._run_git("cherry-pick", result.stdout.strip(), cwd=self.arena_worktree)
                return True
            except Exception:
                return False
        elif self.blue_worktree and self.arena_worktree:
            try:
                for item in self.blue_worktree.rglob("*"):
                    if item.is_file() and not item.name.startswith('.'):
                        rel = item.relative_to(self.blue_worktree)
                        dest = self.arena_worktree / rel
                        dest.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(item, dest)
                return True
            except Exception:
                return False
        return False

    def cleanup(self):
        """Remove all digital twin resources."""
        console.print("[dim]Cleaning up digital twin...[/dim]")
        if self.mode == TwinMode.DOCKER:
            for c in [self.red_container, self.blue_container, self.arena_container]:
                if c:
                    subprocess.run(["docker", "stop", c], capture_output=True)
                    subprocess.run(["docker", "rm", c], capture_output=True)
            subprocess.run(["docker", "network", "rm", f"battle_{self.battle_id}"], capture_output=True)
        elif self.mode == TwinMode.GIT_WORKTREE:
            for wt in [self.red_worktree, self.blue_worktree, self.arena_worktree]:
                if wt and wt.exists():
                    self._run_git("worktree", "remove", str(wt), "--force")
            for suffix in ["red", "blue", "arena"]:
                self._run_git("branch", "-D", f"battle/{self.battle_id}/{suffix}")
        if self.worktree_base.exists():
            shutil.rmtree(self.worktree_base)

    def get_red_target(self) -> Path:
        return self.arena_worktree or self.source_path

    def get_blue_workspace(self) -> Path:
        return self.blue_worktree or self.source_path

    def get_arena(self) -> Path:
        return self.arena_worktree or self.source_path
