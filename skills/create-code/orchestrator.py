#!/usr/bin/env python3
"""
Create Code Skill - Orchestrator
Orchestrates the Horus coding workflow: Idea -> Research -> Sandbox -> Implementation -> Review -> Finalize.
"""
import os
import subprocess
import sys
import shutil
from pathlib import Path
from typing import List, Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.prompt import Confirm, Prompt

app = typer.Typer(name="create-code", help="Horus coding orchestration pipeline", add_completion=False)
console = Console()

# --- Paths & Config ---
SKILL_DIR = Path(__file__).resolve().parent
SKILLS_DIR = SKILL_DIR.parent
PROJECT_ROOT = SKILLS_DIR.parent.parent

DEFAULT_DOCKER_IMAGE = "python:3.11-slim"

# Map skill names to their run.sh paths
SKILL_MAP = {
    "dogpile": SKILLS_DIR / "dogpile/run.sh",
    "battle": SKILLS_DIR / "battle/run.sh",
    "review-code": SKILLS_DIR / "review-code/run.sh",
    "memory": SKILLS_DIR / "memory/run.sh",
    "orchestrate": SKILLS_DIR / "orchestrate/run.sh",
    "hack": SKILLS_DIR / "hack/run.sh",
}

def load_env_overrides(project_dir: Path) -> None:
    """Load KEY=VALUE from .create-code.env if present (destructive/force)."""
    env_file = project_dir / ".create-code.env"
    if env_file.exists():
        console.print(f"[dim]Loading overrides from {env_file}[/dim]")
        for line in env_file.read_text().splitlines():
            s = line.strip()
            if not s or s.startswith("#") or "=" not in s:
                continue
            k, v = s.split("=", 1)
            os.environ[k.strip()] = v.strip()

def run_skill(skill_name: str, args: List[str], cwd: Optional[Path] = None, capture: bool = False):
    """Run a skill via its run.sh script. Handles failure with Exit(1)."""
    if skill_name not in SKILL_MAP:
        console.print(f"[bold red]Error:[/bold red] Unknown skill: {skill_name}")
        raise typer.Exit(1)

    run_script = SKILL_MAP[skill_name]
    if not run_script.exists():
        # Try finding it in .agent/skills as fallback
        run_script = PROJECT_ROOT / ".agent/skills" / f"{skill_name}/run.sh"
        if not run_script.exists():
            console.print(f"[bold red]Error:[/bold red] {skill_name} run.sh not found at {run_script}")
            raise typer.Exit(1)

    cmd = [str(run_script)] + args
    console.print(f"[dim]Running: {' '.join(cmd)}[/dim]")

    try:
        if capture:
            result = subprocess.run(cmd, cwd=str(cwd or Path.cwd()), capture_output=True, text=True, check=True)
            return result.stdout
        else:
            subprocess.run(cmd, cwd=str(cwd or Path.cwd()), check=True)
            return ""
    except subprocess.CalledProcessError as e:
        console.print(f"[bold red]Error running {skill_name}:[/bold red]\n{e.stderr or e.stdout}")
        raise typer.Exit(1)

def _which(cmd: str) -> bool:
    return shutil.which(cmd) is not None

def _is_git_repo(path: Path) -> bool:
    try:
        subprocess.run(["git", "rev-parse", "--is-inside-work-tree"], cwd=str(path), capture_output=True, check=True)
        return True
    except subprocess.CalledProcessError:
        return False

def preflight(project_dir: Path, mode: Optional[str] = None, do_review: bool = False, provider: Optional[str] = None) -> None:
    """Validate external prerequisites and skill availability."""
    # Check essential skills
    essential = ("dogpile", "orchestrate", "review-code")
    missing = [s for s in essential if not SKILL_MAP[s].exists() and not (PROJECT_ROOT / ".agent/skills" / f"{s}/run.sh").exists()]
    if missing:
        console.print(f"[bold red]Missing essential skills:[/bold red] {', '.join(missing)}")
        raise typer.Exit(1)

    if mode == "docker" and not _which("docker"):
        console.print("[bold red]Docker CLI not found.[/bold red] Install Docker or choose a different mode.")
        raise typer.Exit(1)

    if mode == "qemu":
        candidates = ("qemu-system-arm", "qemu-system-x86_64", "qemu-system-riscv64")
        if not any(_which(c) for c in candidates):
            console.print("[bold red]QEMU not found.[/bold red] Install qemu-system-* or choose another mode.")
            raise typer.Exit(1)

    if mode == "git_worktree" and not _is_git_repo(project_dir):
        console.print(f"[bold red]Not a git repository:[/bold red] {project_dir}")
        raise typer.Exit(1)

    if do_review:
        prov = (provider or "github").lower()
        if prov == "github" and not _which("copilot") and not _which("gh"):
            console.print("[bold red]copilot/gh CLI not found for provider 'github'.[/bold red]")
            raise typer.Exit(1)

# --- Stages ---

def stage_1_scope(idea: str, non_interactive: bool = False):
    console.print(Panel(f"[bold blue]Stage 1: Scope Interview[/bold blue]\nIdea: {idea}"))
    if non_interactive:
        return {"idea": idea, "constraints": "Auto-accepted", "tech_stack": "Python"}
    
    constraints = Prompt.ask("Any specific constraints or requirements?")
    tech_stack = Prompt.ask("Preferred tech stack?", default="Python")
    return {"idea": idea, "constraints": constraints, "tech_stack": tech_stack}

def stage_2_research(context: dict, project_dir: Path):
    console.print(Panel("[bold blue]Stage 2: Deep Research (/dogpile)[/bold blue]"))
    with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"), transient=True) as progress:
        progress.add_task(description="Searching for implementation patterns...", total=None)
        query = f"{context['idea']} implementation patterns {context.get('tech_stack', '')}"
        output = run_skill("dogpile", ["search", query, "--no-interactive"], cwd=project_dir, capture=True)
    
    if output:
        console.print("[green]Research complete.[/green]")
        context['research_summary'] = output
    else:
        console.print("[yellow]Research failed or returned no results.[/yellow]")
    return context

def stage_3_sandbox(context: dict, project_dir: Path, mode: Optional[str], arch: Optional[str], image: str, non_interactive: bool):
    console.print(Panel("[bold blue]Stage 3: Isolated Execution & Digital Twin[/bold blue]"))
    if not mode and not non_interactive:
        if not Confirm.ask("Spin up a sandbox digital twin?"):
            return context
        mode = Prompt.ask("Select Digital Twin mode", choices=["docker", "git_worktree", "qemu"], default="docker")

    if not mode:
        return context

    preflight(project_dir, mode=mode)
    if mode == "qemu":
        q_arch = arch or ("arm" if non_interactive else Prompt.ask("Select QEMU arch", choices=["arm", "x86_64", "riscv64"], default="arm"))
        run_skill("battle", ["battle", ".", "--rounds", "1", "--mode", "qemu", "--qemu-machine", q_arch], cwd=project_dir)
    elif mode == "git_worktree":
        run_skill("battle", ["battle", ".", "--rounds", "1", "--mode", "git_worktree"], cwd=project_dir)
    else:
        run_skill("battle", ["battle", ".", "--rounds", "1", "--mode", "docker", "--docker-image", image], cwd=project_dir)
    return context

def stage_3_battle(context: dict, project_dir: Path, rounds: int):
    console.print(Panel("[bold blue]Stage 3: Adversarial Battle (/battle)[/bold blue]"))
    run_skill("battle", ["battle", ".", "--rounds", str(rounds)], cwd=project_dir)
    return context

def stage_4_implement(context: dict, project_dir: Path, non_interactive: bool):
    console.print(Panel("[bold blue]Stage 4: Structured Implementation (/task, /orchestrate)[/bold blue]"))
    task_file = Path("0N_TASKS.md")
    if non_interactive or Confirm.ask("Generate initial task breakdown?"):
        if not (project_dir / task_file).exists():
            content = f"# Tasks for {context['idea']}\n\n- [ ] Task 1: Initialize project\n- [ ] Task 3: Implement core logic\n"
            (project_dir / task_file).write_text(content)
            console.print(f"[green]Created {task_file}[/green]")
    
    if non_interactive or Confirm.ask("Ready to run /orchestrate?"):
        run_skill("orchestrate", ["run", str((project_dir / task_file).resolve())], cwd=project_dir)
    return context

def _detect_repo_info(project_dir: Path) -> tuple[str, str]:
    repo, branch = project_dir.name, "main"
    try:
        top = subprocess.run(["git", "rev-parse", "--show-toplevel"], cwd=str(project_dir), capture_output=True, text=True, check=True).stdout.strip()
        repo = Path(top).name
        branch = subprocess.run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=str(project_dir), capture_output=True, text=True, check=True).stdout.strip() or branch
    except: pass
    return repo, branch

def stage_5_review(context: dict, project_dir: Path, non_interactive: bool, provider: str = "github", model: str = "gpt-5", workspace: Optional[str] = None):
    console.print(Panel("[bold blue]Stage 5: Brutal Code Review (/review-code)[/bold blue]"))
    if not non_interactive and not Confirm.ask("Submit code for brutal review?"):
        return context
        
    preflight(project_dir, do_review=True, provider=provider)
    request_file = project_dir / "review_request.md"
    if not request_file.exists():
        repo, branch = _detect_repo_info(project_dir)
        content = f"# Review Request: {context.get('idea', 'Project')}\n\nRepo: {repo}, Branch: {branch}\n\nFocus: reliability, agentic usability.\n"
        request_file.write_text(content)
        console.print(f"[yellow]Generated minimal request at {request_file}[/yellow]")
    
    cmd = ["review", "--file", str(request_file.resolve()), "-P", provider, "-m", model]
    if workspace: cmd += ["--workspace", workspace]
    run_skill("review-code", cmd, cwd=project_dir)
    return context

def stage_6_finalize(context: dict, project_dir: Path):
    console.print(Panel("[bold blue]Stage 6: Final Research & Consolidation[/bold blue]"))
    run_skill("dogpile", ["search", f"Final review for {context.get('idea', 'ideation')} complete"], cwd=project_dir)
    console.print("[bold green]Workflow complete![/bold green]")
    return context

# --- Commands ---

@app.command()
def start(
    idea: str = typer.Argument(..., help="The idea or feature to implement"),
    project_dir: Path = typer.Option(Path.cwd(), "--project-dir", help="Project directory"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Non-interactive mode"),
    stage3: Optional[str] = typer.Option(None, "--stage3", help="Activity for Stage 3: sandbox, battle, both"),
    rounds: int = typer.Option(10, "--rounds", help="Battle rounds"),
):
    """Launch full Horus coding workflow."""
    project_dir = project_dir.resolve()
    load_env_overrides(project_dir)
    non_interactive = yes
    
    context = stage_1_scope(idea, non_interactive)
    preflight(project_dir)
    context = stage_2_research(context, project_dir)
    
    # Stage 3 logic
    if non_interactive:
        if stage3 == "battle":
            context = stage_3_battle(context, project_dir, rounds)
        elif stage3 in ("docker", "git_worktree", "qemu"):
            context = stage_3_sandbox(context, project_dir, stage3, None, DEFAULT_DOCKER_IMAGE, True)
    else:
        if Confirm.ask("Run Stage 3 (Sandbox/Battle)?"):
            choice = Prompt.ask("Select activity", choices=["sandbox", "battle", "both"], default="sandbox")
            if choice in ("sandbox", "both"):
                context = stage_3_sandbox(context, project_dir, None, None, DEFAULT_DOCKER_IMAGE, False)
            if choice in ("battle", "both"):
                context = stage_3_battle(context, project_dir, rounds)
                
    context = stage_4_implement(context, project_dir, non_interactive)
    context = stage_5_review(context, project_dir, non_interactive)
    context = stage_6_finalize(context, project_dir)

@app.command()
def review(
    yes: bool = typer.Option(False, "--yes", "-y"),
    project_dir: Path = typer.Option(Path.cwd(), "--project-dir"),
    provider: str = typer.Option("github", "--provider", "-P"),
    model: str = typer.Option("gpt-5", "--model", "-m"),
    workspace: Optional[str] = typer.Option(None, "--workspace", "-w"),
):
    """Run Stage 5 review only."""
    project_dir = project_dir.resolve()
    load_env_overrides(project_dir)
    stage_5_review({}, project_dir, yes, provider, model, workspace)

@app.command()
def implement(yes: bool = typer.Option(False, "--yes", "-y"), project_dir: Path = typer.Option(Path.cwd(), "--project-dir")):
    """Run Stage 4 implementation only."""
    project_dir = project_dir.resolve()
    load_env_overrides(project_dir)
    stage_4_implement({"idea": "Implementation"}, project_dir, yes)

@app.command()
def finalize(project_dir: Path = typer.Option(Path.cwd(), "--project-dir")):
    """Run Stage 6 finalization only."""
    project_dir = project_dir.resolve()
    load_env_overrides(project_dir)
    stage_6_finalize({}, project_dir)

if __name__ == "__main__":
    console.print("[bold gold1]HORUS CREATE-CODE ORCHESTRATOR[/bold gold1]")
    app()
