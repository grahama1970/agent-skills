#!/usr/bin/env python3
"""
Create Code Skill - Orchestrator
Orchestrates the Horus coding workflow: Idea -> Research -> Sandbox -> Implementation -> Review -> Finalize.
"""
import os
import subprocess
import sys
import shutil
import json
from pathlib import Path
from typing import List, Optional, Dict, Any
from datetime import datetime

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

# Default retry policies per skill (can be overridden via env)
RETRY_POLICY = {
    "dogpile": 3,
    "battle": 2,
    "hack": 1,
    "review-code": 2,
    "orchestrate": 1,
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

def save_state(project_dir: Path, state: Dict[str, Any]) -> None:
    """Save workflow state to .create-code.json."""
    state_file = project_dir / ".create-code.json"
    with open(state_file, "w") as f:
        json.dump(state, f, indent=2)

def load_state(project_dir: Path) -> Dict[str, Any]:
    """Load workflow state from .create-code.json."""
    state_file = project_dir / ".create-code.json"
    if state_file.exists():
        with open(state_file, "r") as f:
            return json.load(f)
    return {}

def run_skill(skill_name: str, args: List[str], cwd: Optional[Path] = None, capture: bool = False, retries: Optional[int] = None, backoff_s: float = 1.0):
    """Run a skill via its run.sh script. Handles failure with Exit(1). Logs to .create-code.log and JSONL. Retries with exponential backoff."""
    if skill_name not in SKILL_MAP:
        console.print(f"[bold red]Error:[/bold red] Unknown skill: {skill_name}")
        raise typer.Exit(1)

    # Use policy default if retries not specified
    if retries is None:
        retries = RETRY_POLICY.get(skill_name, 0)

    run_script = SKILL_MAP[skill_name]
    if not run_script.exists():
        # Try finding it in .agent/skills as fallback
        run_script = PROJECT_ROOT / ".agent/skills" / f"{skill_name}/run.sh"
        if not run_script.exists():
            console.print(f"[bold red]Error:[/bold red] {skill_name} run.sh not found at {run_script}")
            raise typer.Exit(1)

    cmd = [str(run_script)] + args
    cwd_path = cwd or Path.cwd()
    log_file = cwd_path / ".create-code.log"
    jsonl_file = cwd_path / ".create-code.log.jsonl"
    
    console.print(f"[dim]Running: {' '.join(cmd)}[/dim]")
    
    # Prepend execution info to log
    ts = datetime.now(UTC).isoformat()
    from time import perf_counter
    t0 = perf_counter()
    with open(log_file, "a") as f:
        f.write(f"\n--- [{ts} UTC] {skill_name} {' '.join(args)} ---\n")
    with open(jsonl_file, "a") as jf:
        jf.write(json.dumps({"ts": ts, "stage": skill_name, "cmd": cmd, "cwd": str(cwd_path), "capture": capture}) + "\n")

    attempt = 0
    while True:
        try:
            if capture:
                result = subprocess.run(cmd, cwd=str(cwd_path), capture_output=True, text=True, check=True)
                with open(log_file, "a") as f:
                    f.write(result.stdout)
                with open(jsonl_file, "a") as jf:
                    jf.write(json.dumps({"ts": ts, "stage": skill_name, "status": "ok", "rc": 0, "stdout_len": len(result.stdout), "dur_s": round(perf_counter()-t0, 3), "attempt": attempt+1}) + "\n")
                return result.stdout
            else:
                # We want to both see output and log it
                with open(log_file, "a") as f:
                    process = subprocess.Popen(cmd, cwd=str(cwd_path), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
                    for line in process.stdout:
                        print(line, end="")
                        f.write(line)
                    process.wait()
                    with open(jsonl_file, "a") as jf:
                        jf.write(json.dumps({"ts": ts, "stage": skill_name, "status": "ok" if process.returncode==0 else "err", "rc": process.returncode, "dur_s": round(perf_counter()-t0, 3), "attempt": attempt+1}) + "\n")
                    if process.returncode != 0:
                        raise subprocess.CalledProcessError(process.returncode, cmd)
                return ""
        except subprocess.CalledProcessError as e:
            attempt += 1
            if attempt > max(0, retries):
                with open(jsonl_file, "a") as jf:
                    jf.write(json.dumps({"ts": ts, "stage": skill_name, "status": "err", "rc": e.returncode, "cmd": cmd, "dur_s": round(perf_counter()-t0, 3), "attempt": attempt, "stderr": e.stderr[:500] if hasattr(e, 'stderr') and e.stderr else None}) + "\n")
                console.print(f"[bold red]Error running {skill_name} (rc={e.returncode}):[/bold red] {str(e)[:200]}")
                raise typer.Exit(1)
            delay = backoff_s * (2 ** (attempt-1))
            console.print(f"[yellow]Retrying {skill_name} in {delay:.1f}s (attempt {attempt}/{retries})[/yellow]")
            import time; time.sleep(delay)
            # refresh start time for duration of next attempt
            t0 = perf_counter()

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
    # Check essential skills exist and are runnable
    essential = ("dogpile", "orchestrate", "review-code")
    for skill in essential:
        run_script = SKILL_MAP.get(skill) or (PROJECT_ROOT / f".agent/skills/{skill}/run.sh")
        if not run_script.exists():
            console.print(f"[bold red]Missing skill:[/bold red] {skill} at {run_script}")
            raise typer.Exit(1)
        # Test if skill is runnable
        try:
            result = subprocess.run([str(run_script), "--help"], capture_output=True, timeout=5)
            if result.returncode != 0:
                console.print(f"[bold yellow]Warning:[/bold yellow] {skill} --help failed (rc={result.returncode})")
        except Exception as e:
            console.print(f"[bold yellow]Warning:[/bold yellow] {skill} health check failed: {e}")

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

def _needs_security(idea: str) -> bool:
    keywords = ("auth", "oauth", "jwt", "encryption", "key", "secret", "api", "network", "web", "sandbox", "plugin", "serialize", "exec", "eval", "shell")
    s = idea.lower()
    return any(k in s for k in keywords)

def _needs_battle(idea: str) -> bool:
    keywords = ("performance", "scal", "concurrency", "race", "stress", "fuzz", "robust", "resilience", "fault", "latency")
    s = idea.lower()
    return any(k in s for k in keywords)

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
    # Heuristics to schedule security/battle follow-ups
    idea = context.get('idea', '')
    context['suggest_security'] = _needs_security(idea)
    context['suggest_battle'] = _needs_battle(idea)
    return context

def stage_3_sandbox(context: dict, project_dir: Path, mode: Optional[str], arch: Optional[str], image: str, non_interactive: bool, security_audit: bool = False):
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
        # TODO: Capture twin container ID from battle output and save to context
        context['twin_mode'] = 'docker'
    
    # Optional security audit pass
    if security_audit or context.get('suggest_security'):
        run_skill("hack", ["audit", ".", "--no-interactive"], cwd=project_dir)
    return context

def stage_3_battle(context: dict, project_dir: Path, rounds: int):
    console.print(Panel("[bold blue]Stage 3: Adversarial Battle (/battle)[/bold blue]"))
    run_skill("battle", ["battle", ".", "--rounds", str(rounds)], cwd=project_dir)
    return context

def stage_4_implement(context: dict, project_dir: Path, non_interactive: bool):
    console.print(Panel("[bold blue]Stage 4: Structured Implementation (/task, /orchestrate)[/bold blue]"))
    task_file = project_dir / "0N_TASKS.md"
    
    if non_interactive or Confirm.ask("Generate initial task breakdown using /plan?"):
        if not task_file.exists():
            # Use /plan if available, else fallback to manual
            plan_script = SKILLS_DIR / "plan/run.sh"
            if plan_script.exists():
                run_skill("plan", ["create", str(task_file)], cwd=project_dir)
            else:
                content = f"# Tasks for {context.get('idea', 'Feature')}\n\n- [ ] Task 1: Initialize project\n- [ ] Task 2: Implement core logic\n"
                task_file.write_text(content)
                console.print(f"[green]Created {task_file}[/green]")
    
    if non_interactive or Confirm.ask("Ready to run /orchestrate?"):
        run_skill("orchestrate", ["run", str(task_file.resolve())], cwd=project_dir)
    return context

def _validate_review_request(request_file: Path) -> bool:
    """Validate review_request.md has minimum required sections."""
    if not request_file.exists():
        return False
    content = request_file.read_text()
    required = ["# Review Request", "Repo:", "Branch:", "Focus:"]
    return all(r in content for r in required)

def _generate_review_request(context: dict, project_dir: Path) -> Path:
    """Generate a structured review_request.md with schema."""
    repo, branch = _detect_repo_info(project_dir)
    request_file = project_dir / "review_request.md"
    template = f"""# Review Request: {context.get('idea', 'Project')}

## Metadata
- **Repo**: {repo}
- **Branch**: {branch}
- **Date**: {datetime.utcnow().strftime('%Y-%m-%d')}

## Scope
{context.get('constraints', 'No specific constraints provided.')}

## Tech Stack
{context.get('tech_stack', 'Python')}

## Focus Areas
- Reliability and correctness
- Agentic usability (CLI, error messages, --yes modes)
- Security (if applicable)
- Performance (if applicable)

## Risk Areas
- Error handling and edge cases
- Dependency vulnerabilities
- Concurrency or race conditions

## Definition of Done
- [ ] All critical and high severity issues addressed
- [ ] Sanity tests pass
- [ ] No hardcoded secrets or credentials
"""
    request_file.write_text(template)
    return request_file

    repo, branch = project_dir.name, "main"
    try:
        top = subprocess.run(["git", "rev-parse", "--show-toplevel"], cwd=str(project_dir), capture_output=True, text=True, check=True).stdout.strip()
        repo = Path(top).name
        branch = subprocess.run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=str(project_dir), capture_output=True, text=True, check=True).stdout.strip() or branch
    except: pass
    return repo, branch

def stage_5_review(context: dict, project_dir: Path, non_interactive: bool, provider: str = "github", model: str = "gpt-5", workspace: Optional[str] = None, auto_remediate: bool = False):
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
    
    # Remediation loop: create tasks and run orchestrate, then re-review
    if auto_remediate or (not non_interactive and Confirm.ask("Convert findings to tasks and run remediation?", default=True)):
        task_file = project_dir / "0N_TASKS.md"
        # Append a minimal remediation section
        with open(task_file, "a") as tf:
            tf.write("\n\n## Remediation Tasks (from review)\n- [ ] Address critical findings\n- [ ] Fix high severity issues\n- [ ] Re-run brutal review\n")
        run_skill("orchestrate", ["run", str(task_file.resolve())], cwd=project_dir)
        # Re-run review in diff-only mode if supported
        run_skill("review-code", ["review", "--file", str(request_file.resolve()), "-P", provider, "-m", model, "--diff-only"], cwd=project_dir)
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
    force_docker: bool = typer.Option(False, "--force-docker", help="Always use docker for sandbox/battle"),
):
    """Launch full Horus coding workflow."""
    project_dir = project_dir.resolve()
    load_env_overrides(project_dir)
    non_interactive = yes
    
    state = {"idea": idea, "stage": 0, "context": {}}
    
    # Stage 1
    state["context"] = stage_1_scope(idea, non_interactive)
    state["stage"] = 1
    save_state(project_dir, state)
    
    preflight(project_dir)
    
    # Stage 2
    state["context"] = stage_2_research(state["context"], project_dir)
    state["stage"] = 2
    save_state(project_dir, state)
    
    # Stage 3
    if non_interactive:
        if stage3 == "battle":
            state["context"] = stage_3_battle(state["context"], project_dir, rounds)
        elif stage3 in ("docker", "git_worktree", "qemu"):
            mode = "docker" if force_docker else stage3
            state["context"] = stage_3_sandbox(state["context"], project_dir, mode, None, DEFAULT_DOCKER_IMAGE, True, security_audit)
    else:
        if Confirm.ask("Run Stage 3 (Sandbox/Battle)?"):
            choice = Prompt.ask("Select activity", choices=["sandbox", "battle", "both"], default="sandbox")
            if choice in ("sandbox", "both"):
                mode = "docker" if force_docker else None
                state["context"] = stage_3_sandbox(state["context"], project_dir, mode, None, DEFAULT_DOCKER_IMAGE, False, security_audit)
            if choice in ("battle", "both"):
                if force_docker:
                    state["context"] = stage_3_sandbox(state["context"], project_dir, "docker", None, DEFAULT_DOCKER_IMAGE, True, security_audit)
                else:
                    state["context"] = stage_3_battle(state["context"], project_dir, rounds)
    state["stage"] = 3
    save_state(project_dir, state)
                
    # Stage 4
    state["context"] = stage_4_implement(state["context"], project_dir, non_interactive)
    state["stage"] = 4
    save_state(project_dir, state)
    
    # Stage 5
    state["context"] = stage_5_review(state["context"], project_dir, non_interactive)
    state["stage"] = 5
    save_state(project_dir, state)
    
    # Stage 6
    state["context"] = stage_6_finalize(state["context"], project_dir)
    state["stage"] = 6
    save_state(project_dir, state)

@app.command()
def resume(
    project_dir: Path = typer.Option(Path.cwd(), "--project-dir", help="Project directory"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Non-interactive mode"),
    force_docker: bool = typer.Option(False, "--force-docker", help="Always use docker for sandbox/battle"),
):
    """Resume a workflow from the last saved stage."""
    project_dir = project_dir.resolve()
    state = load_state(project_dir)
    if not state:
        console.print("[bold red]No saved state found in this directory.[/bold red]")
        raise typer.Exit(1)
    
    idea = state.get("idea", "Unknown")
    current_stage = state.get("stage", 0)
    context = state.get("context", {})
    non_interactive = yes
    
    console.print(f"[bold green]Resuming workflow for:[/bold green] {idea}")
    console.print(f"[dim]Last completed stage: {current_stage}[/dim]")
    
    if current_stage < 2:
        context = stage_2_research(context, project_dir)
        state["stage"] = 2; state["context"] = context; save_state(project_dir, state)
    
    if current_stage < 3:
        # Offer optional Stage 3 before resuming implementation
        if Confirm.ask("Run Stage 3 (Sandbox/Battle) before resuming?", default=False):
            choice = Prompt.ask("Select activity", choices=["sandbox", "battle", "both"], default="battle")
            if choice in ("sandbox", "both"):
                mode = "docker" if force_docker else None
                stage_3_sandbox(context, project_dir, mode, None, DEFAULT_DOCKER_IMAGE, False)
            if choice in ("battle", "both"):
                if force_docker:
                    stage_3_sandbox(context, project_dir, "docker", None, DEFAULT_DOCKER_IMAGE, True)
                else:
                    stage_3_battle(context, project_dir, 1)
        state["stage"] = 3; save_state(project_dir, state)
        
    if current_stage < 4:
        context = stage_4_implement(context, project_dir, non_interactive)
        state["stage"] = 4; state["context"] = context; save_state(project_dir, state)
        
    if current_stage < 5:
        context = stage_5_review(context, project_dir, non_interactive)
        state["stage"] = 5; state["context"] = context; save_state(project_dir, state)
        
    if current_stage < 6:
        context = stage_6_finalize(context, project_dir)
        state["stage"] = 6; state["context"] = context; save_state(project_dir, state)

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

@app.command()
def improve(project_dir: Path = typer.Option(Path.cwd(), "--project-dir")):
    """Use /dogpile to gather iterative improvements for create-code skill."""
    project_dir = project_dir.resolve()
    load_env_overrides(project_dir)
    q = "Iterative improvements for Horus create-code orchestrator: UX, logging, isolation, heuristics, retries."
    run_skill("dogpile", ["search", q, "--no-interactive"], cwd=project_dir, capture=False)

if __name__ == "__main__":
    console.print("[bold gold1]HORUS CREATE-CODE ORCHESTRATOR[/bold gold1]")
    app()
