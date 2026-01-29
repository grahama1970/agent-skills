#!/usr/bin/env python3
"""
Create Code Skill - Orchestrator
Orchestrates the Horus coding workflow: Idea -> Research -> Sandbox -> Implementation -> Review -> Finalize.
"""
import os
import subprocess
import sys
from pathlib import Path
from typing import List, Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.prompt import Confirm, Prompt

app = typer.Typer(name="create-code", help="Horus coding orchestration pipeline")
console = Console()

# --- Config ---
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent.resolve()
SKILLS_DIR = PROJECT_ROOT / ".pi/skills"

# Map skill names to their run.sh paths
SKILL_MAP = {
    "dogpile": SKILLS_DIR / "dogpile/run.sh",
    "hack": SKILLS_DIR / "hack/run.sh",
    "battle": SKILLS_DIR / "battle/run.sh",
    "review-code": SKILLS_DIR / "review-code/run.sh",
    "memory": SKILLS_DIR / "memory/run.sh",
}

def run_skill(skill_name: str, args: List[str], cwd: Optional[Path] = None):
    """Run a skill via its run.sh script."""
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
        result = subprocess.run(cmd, cwd=cwd or os.getcwd(), capture_output=True, text=True, check=True)
        return result.stdout
    except subprocess.CalledProcessError as e:
        console.print(f"[bold red]Error running {skill_name}:[/bold red]\n{e.stderr}")
        return None

# --- Stages ---

def stage_1_scope(idea: str):
    console.print(Panel(f"[bold blue]Stage 1: Scope Interview[/bold blue]\nIdea: {idea}"))
    # In a real implementation, we would use the /interview skill here.
    # For now, we'll do a simple prompt.
    constraints = Prompt.ask("Any specific constraints or requirements?")
    tech_stack = Prompt.ask("Preferred tech stack?", default="Python, Typer")
    return {"idea": idea, "constraints": constraints, "tech_stack": tech_stack}

def stage_2_research(context: dict):
    console.print(Panel("[bold blue]Stage 2: Deep Research (/dogpile)[/bold blue]"))
    with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"), transient=True) as progress:
        progress.add_task(description="Searching for implementation patterns...", total=None)
        query = f"{context['idea']} implementation patterns {context['tech_stack']}"
        output = run_skill("dogpile", ["search", query])
    
    if output:
        console.print("[green]Research complete.[/green]")
        # Save research context
        context['research_summary'] = output
    else:
        console.print("[yellow]Research failed or returned no results.[/yellow]")
    return context

def stage_3_sandbox(context: dict):
    console.print(Panel("[bold blue]Stage 3: Isolated Execution & Digital Twin (/hack)[/bold blue]"))
    if Confirm.ask("Spin up a sandbox container or digital twin?"):
        mode = Prompt.ask("Select Digital Twin mode", choices=["docker", "git_worktree", "qemu"], default="docker")
        if mode == "qemu":
            arch = Prompt.ask("Select QEMU architecture", choices=["arm", "x86_64", "riscv64"], default="arm")
            run_skill("hack", ["run", "--mode", "qemu", "--arch", arch])
        elif mode == "git_worktree":
            run_skill("hack", ["run", "--mode", "git_worktree"])
        else:
            run_skill("hack", ["run", "--image", "python:3.11-slim", "--interactive"])
    return context

def stage_3_battle(context: dict):
    console.print(Panel("[bold blue]Stage 3: Adversarial Battle (/battle)[/bold blue]"))
    if Confirm.ask("Run a security hardening battle?"):
        rounds = Prompt.ask("Number of rounds?", default="10")
        run_skill("battle", ["battle", ".", "--rounds", rounds])
    return context

def stage_4_implement(context: dict):
    console.print(Panel("[bold blue]Stage 4: Structured Implementation (/task, /orchestrate)[/bold blue]"))
    console.print("Implementation should be driven by [bold]0N_TASKS.md[/bold] with sanity tests.")
    if Confirm.ask("Generate initial task breakdown?"):
        # This would call /task if it were a direct CLI tool, but it's often a manual or agentic process.
        # We'll simulate by creating a file if it doesn't exist.
        task_file = Path("0N_TASKS.md")
        if not task_file.exists():
            task_file.write_text(f"# Tasks for {context['idea']}\n\n- [ ] Task 1: Initialize project\n- [ ] Task 2: Implement core logic\n")
            console.print(f"[green]Created {task_file}[/green]")
    
    if Confirm.ask("Ready to run /orchestrate?"):
        # run_skill("orchestrate", ["run"]) # Assume orchestrate is available
        pass
    return context

def stage_5_review(context: dict):
    console.print(Panel("[bold blue]Stage 5: Brutal Code Review (/review-code)[/bold blue]"))
    if Confirm.ask("Submit code for brutal review?"):
        run_skill("review-code", ["--brutal", "--provider", "copilot", "--model", "gpt-5"])
    return context

def stage_6_finalize(context: dict):
    console.print(Panel("[bold blue]Stage 6: Final Research & Consolidation[/bold blue]"))
    with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"), transient=True) as progress:
        progress.add_task(description="Finalizing research and updating memory...", total=None)
        run_skill("dogpile", ["search", f"Final review for {context['idea']} implementation"])
        # run_skill("memory", ["learn", "--context", "New implementation completed"])
    console.print("[bold green]Workflow complete![/bold green]")
    return context

# --- CLI Commands ---

@app.command()
def start(idea: str = typer.Argument(..., help="The idea or feature to implement")):
    """Launch the full 6-stage Horus coding workflow."""
    context = stage_1_scope(idea)
    context = stage_2_research(context)
    
    # Optional Sandbox or Battle
    if Confirm.ask("Run Stage 3 (Sandbox/Battle)?"):
        choice = Prompt.ask("Select Stage 3 activity", choices=["sandbox", "battle", "both"], default="sandbox")
        if choice in ["sandbox", "both"]:
            context = stage_3_sandbox(context)
        if choice in ["battle", "both"]:
            context = stage_3_battle(context)
    
    context = stage_4_implement(context)
    context = stage_5_review(context)
    context = stage_6_finalize(context)

@app.command()
def research(idea: str):
    """Run Stage 2 research only."""
    stage_2_research({"idea": idea, "tech_stack": ""})

@app.command()
def sandbox(mode: str = typer.Option("docker", "--mode", "-m", help="Digital Twin mode: docker, git_worktree, qemu")):
    """Spin up Stage 3 sandbox only."""
    if mode == "qemu":
        run_skill("hack", ["run", "--mode", "qemu"])
    else:
        run_skill("hack", ["run", "--mode", mode])

@app.command()
def battle(rounds: int = typer.Option(10, "--rounds", "-r", help="Number of battle rounds")):
    """Run Stage 3 adversarial battle only."""
    stage_3_battle({"rounds": rounds})

@app.command()
def review():
    """Run Stage 5 review only."""
    stage_5_review({})

@app.command()
def finalize():
    """Run Stage 6 finalization only."""
    stage_6_finalize({})

if __name__ == "__main__":
    console.print("[bold gold1]HORUS CREATE-CODE ORCHESTRATOR[/bold gold1]")
    app()
