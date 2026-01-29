> **Review Metadata**: Round 2 | Final Diff | Provider: github | Model: gpt-5
---

```diff
feat(create-code): fix preflight exit, stage3 routing, env precedence, cwd consistency, review flags

diff --git a/.pi/skills/create-code/SKILL.md b/.pi/skills/create-code/SKILL.md
index 33b6b9b..e9a0f9d 100644
--- a/.pi/skills/create-code/SKILL.md
+++ b/.pi/skills/create-code/SKILL.md
@@ -68,6 +68,7 @@ Environment/config:
 ./run.sh sandbox --mode docker --yes
 ./run.sh implement --yes
 
 # Run specific stages
 ./run.sh research "idea"
-./run.sh review
+./run.sh review --provider github --model gpt-5 --yes
 ```
 
 ## Commands
diff --git a/.pi/skills/create-code/orchestrator.py b/.pi/skills/create-code/orchestrator.py
index 2a8b9f0..7b5a6cf 100755
--- a/.pi/skills/create-code/orchestrator.py
+++ b/.pi/skills/create-code/orchestrator.py
@@ -20,6 +20,7 @@ import shutil
 
 import typer
 from rich.console import Console
 from rich.panel import Panel
 from rich.progress import Progress, SpinnerColumn, TextColumn
 from rich.prompt import Confirm, Prompt
@@ -33,15 +34,15 @@ DEFAULT_DOCKER_IMAGE = "python:3.11-slim"
 def load_env_overrides(project_dir: Path) -> None:
     """Load KEY=VALUE from .create-code.env if present (non-destructive)."""
     env_file = project_dir / ".create-code.env"
     if env_file.exists():
         for line in env_file.read_text().splitlines():
             s = line.strip()
             if not s or s.startswith("#") or "=" not in s:
                 continue
             k, v = s.split("=", 1)
-            os.environ.setdefault(k.strip(), v.strip())
+            os.environ[k.strip()] = v.strip()
 
 # Map skill names to their run.sh paths
 SKILL_MAP = {
     "dogpile": SKILLS_DIR / "dogpile/run.sh",
     "battle": SKILLS_DIR / "battle/run.sh",
@@ -75,11 +76,11 @@ def run_skill(skill_name: str, args: List[str], cwd: Optional[Path] = None, capt
         else:
             subprocess.run(cmd, cwd=str(cwd or PROJECT_ROOT), check=True)
             return ""
     except subprocess.CalledProcessError as e:
         console.print(f"[bold red]Error running {skill_name}:[/bold red]\n{e.stderr}")
-        return None
+        raise typer.Exit(1)
 
 def _which(cmd: str) -> bool:
     return shutil.which(cmd) is not None
 
 def _is_git_repo(path: Path) -> bool:
@@ -89,21 +90,25 @@ def _is_git_repo(path: Path) -> bool:
         return True
     except subprocess.CalledProcessError:
         return False
 
-def preflight(project_dir: Path, mode: Optional[str] = None, do_review: bool = False) -> None:
+def preflight(project_dir: Path, mode: Optional[str] = None, do_review: bool = False, provider: Optional[str] = None) -> None:
     """Validate external prerequisites and skill availability."""
     missing_skills = [name for name, p in SKILL_MAP.items() if name in ("dogpile","battle","orchestrate","review-code") and not p.exists()]
     if missing_skills:
         console.print(f"[bold red]Missing skills:[/bold red] {', '.join(missing_skills)}")
+        raise typer.Exit(1)
     if mode == "docker" and not _which("docker"):
         console.print("[bold red]Docker CLI not found.[/bold red] Set up Docker or choose a different mode.")
         raise typer.Exit(1)
     if mode == "qemu":
         # Check a reasonable default machine binary
         candidates = ("qemu-system-arm","qemu-system-x86_64","qemu-system-riscv64")
         if not any(_which(c) for c in candidates):
             console.print("[bold red]QEMU not found.[/bold red] Install qemu-system-* binaries or choose a different mode.")
             raise typer.Exit(1)
     if mode == "git_worktree" and not _is_git_repo(project_dir):
         console.print(f"[bold red]Not a git repository:[/bold red] {project_dir}")
         raise typer.Exit(1)
-    if do_review and not _which("copilot"):
-        console.print("[yellow]copilot CLI not found; GitHub provider may not work. Install or choose another provider.[/yellow]")
+    if do_review:
+        prov = (provider or "github").lower()
+        if prov == "github" and not _which("copilot"):
+            console.print("[bold red]copilot CLI not found for provider 'github'.[/bold red] Install it or choose a different provider via --provider.")
+            raise typer.Exit(1)
 
 # --- Stages ---
@@ -162,7 +167,7 @@ def stage_3_battle(context: dict, project_dir: Path, rounds: int):
     run_skill("battle", ["battle", ".", "--rounds", str(rounds)], cwd=project_dir)
     return context
 
-def stage_4_implement(context: dict, project_dir: Path, non_interactive: bool):
+def stage_4_implement(context: dict, project_dir: Path, non_interactive: bool):
     console.print(Panel("[bold blue]Stage 4: Structured Implementation (/task, /orchestrate)[/bold blue]"))
     console.print("Implementation should be driven by [bold]0N_TASKS.md[/bold] with sanity tests.")
     task_file = Path("0N_TASKS.md")
     if non_interactive or Confirm.ask("Generate initial task breakdown?"):
         # This would call /task if it were a direct CLI tool, but it's often a manual or agentic process.
@@ -175,12 +180,34 @@ def stage_4_implement(context: dict, project_dir: Path, non_interactive: bool):
     if non_interactive or Confirm.ask("Ready to run /orchestrate?"):
         run_skill("orchestrate", ["run", str((project_dir / task_file).resolve())], cwd=project_dir)
     return context
 
-def _detect_repo_branch(project_dir: Path) -> tuple[str, str]:
+def _detect_repo_branch(project_dir: Path) -> tuple[str, str]:
     repo = project_dir.name
     branch = "HEAD"
     try:
         top = subprocess.run(["git", "rev-parse", "--show-toplevel"], cwd=str(project_dir), capture_output=True, text=True, check=True).stdout.strip()
         repo = Path(top).name
         branch = subprocess.run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=str(project_dir), capture_output=True, text=True, check=True).stdout.strip() or branch
     except subprocess.CalledProcessError:
         pass
     return repo, branch
 
-def stage_5_review(context: dict, project_dir: Path, non_interactive: bool):
+def stage_5_review(
+    context: dict,
+    project_dir: Path,
+    non_interactive: bool,
+    provider: str = "github",
+    model: str = "gpt-5",
+    workspace: Optional[str] = None,
+):
     console.print(Panel("[bold blue]Stage 5: Brutal Code Review (/review-code)[/bold blue]"))
     go = True if non_interactive else Confirm.ask("Submit code for brutal review?")
     if go:
-        preflight(project_dir, do_review=True)
+        preflight(project_dir, do_review=True, provider=provider)
         request_file = (project_dir / "review_request.md")
         if not request_file.exists():
             repo, branch = _detect_repo_branch(project_dir)
             minimal = f"""# Create-code review request
@@ -202,16 +229,20 @@ def stage_5_review(context: dict, project_dir: Path, non_interactive: bool):
 """
             request_file.write_text(minimal)
             console.print(f"[yellow]Generated minimal review request at {request_file}[/yellow]")
-        run_skill("review-code", ["review", "--file", str(request_file), "-P", "github", "-m", "gpt-5"], cwd=project_dir)
+        cmd = ["review", "--file", str(request_file), "-P", provider, "-m", model]
+        if workspace:
+            cmd += ["--workspace", workspace]
+        run_skill("review-code", cmd, cwd=project_dir)
     return context
 
-def stage_6_finalize(context: dict):
+def stage_6_finalize(context: dict, project_dir: Path):
     console.print(Panel("[bold blue]Stage 6: Final Research & Consolidation[/bold blue]"))
     with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"), transient=True) as progress:
         progress.add_task(description="Finalizing research and updating memory...", total=None)
-        run_skill("dogpile", ["search", f"Final review for {context['idea']} implementation"])
+        run_skill("dogpile", ["search", f"Final review for {context['idea']} implementation"], cwd=project_dir)
         # run_skill("memory", ["learn", "--context", "New implementation completed"])
     console.print("[bold green]Workflow complete![/bold green]")
     return context
 
 # --- CLI Commands ---
@@ -229,25 +260,39 @@ def start(
 ):
     """Launch the full 6-stage Horus coding workflow (headless-ready)."""
     project_dir = project_dir.resolve()
     load_env_overrides(project_dir)
     non_interactive = yes or no_interactive
     docker_image = os.environ.get("CREATE_CODE_DOCKER_IMAGE", DEFAULT_DOCKER_IMAGE)
 
     context = stage_1_scope(idea, non_interactive=non_interactive)
     preflight(project_dir)  # base checks
     context = stage_2_research(context, project_dir=project_dir)
 
     # Stage 3
-    if non_interactive or Confirm.ask("Run Stage 3 (Sandbox/Battle)?"):
-        choice = ("sandbox" if non_interactive and stage3 else
-                  Prompt.ask("Select Stage 3 activity", choices=["sandbox", "battle", "both"], default="sandbox"))
-        if choice in ["sandbox", "both"]:
-            context = stage_3_sandbox(context, project_dir, stage3, qemu_machine, docker_image, non_interactive)
-        if choice in ["battle", "both"]:
-            context = stage_3_battle(context, project_dir, rounds)
+    if non_interactive:
+        if stage3:
+            if stage3 == "battle":
+                context = stage_3_battle(context, project_dir, rounds)
+            elif stage3 in ("docker", "git_worktree", "qemu"):
+                context = stage_3_sandbox(context, project_dir, stage3, qemu_machine, docker_image, non_interactive)
+        else:
+            # default to no stage3 in headless unless explicitly requested
+            pass
+    else:
+        if Confirm.ask("Run Stage 3 (Sandbox/Battle)?"):
+            choice = Prompt.ask("Select Stage 3 activity", choices=["sandbox", "battle", "both"], default="sandbox")
+            if choice in ["sandbox", "both"]:
+                context = stage_3_sandbox(context, project_dir, None, qemu_machine, docker_image, non_interactive)
+            if choice in ["battle", "both"]:
+                context = stage_3_battle(context, project_dir, rounds)
 
     context = stage_4_implement(context, project_dir, non_interactive)
-    context = stage_5_review(context, project_dir, non_interactive)
-    context = stage_6_finalize(context)
+    context = stage_5_review(context, project_dir, non_interactive)
+    context = stage_6_finalize(context, project_dir)
 
 @app.command()
 def research(idea: str, project_dir: Path = typer.Option(Path.cwd(), "--project-dir")):
     """Run Stage 2 research only."""
     project_dir = project_dir.resolve()
     load_env_overrides(project_dir)
     stage_2_research({"idea": idea, "tech_stack": ""}, project_dir)
 
 @app.command()
 def sandbox(
@@ -262,23 +307,31 @@ def sandbox(
     preflight(project_dir, mode=mode)
     non_interactive = yes
     if mode == "qemu":
         machine = qemu_machine or ("arm" if non_interactive else Prompt.ask("Select QEMU machine", choices=["arm","x86_64","riscv64"], default="arm"))
         run_skill("battle", ["battle", ".", "--rounds", "1", "--mode", "qemu", "--qemu-machine", machine], cwd=project_dir)
     elif mode == "git_worktree":
         run_skill("battle", ["battle", ".", "--rounds", "1", "--mode", "git_worktree"], cwd=project_dir)
     else:
         run_skill("battle", ["battle", ".", "--rounds", "1", "--mode", "docker", "--docker-image", docker_image], cwd=project_dir)
 
 @app.command()
-def battle(rounds: int = typer.Option(10, "--rounds", "-r", help="Number of battle rounds")):
+def battle(
+    rounds: int = typer.Option(10, "--rounds", "-r", help="Number of battle rounds"),
+    project_dir: Path = typer.Option(Path.cwd(), "--project-dir"),
+):
     """Run Stage 3 adversarial battle only."""
-    stage_3_battle({"rounds": rounds}, PROJECT_ROOT, rounds)
+    project_dir = project_dir.resolve()
+    load_env_overrides(project_dir)
+    stage_3_battle({"rounds": rounds}, project_dir, rounds)
 
 @app.command()
-def review(yes: bool = typer.Option(False, "--yes"), project_dir: Path = typer.Option(Path.cwd(), "--project-dir")):
+def review(
+    yes: bool = typer.Option(False, "--yes"),
+    project_dir: Path = typer.Option(Path.cwd(), "--project-dir"),
+    provider: str = typer.Option("github", "--provider", "-P"),
+    model: str = typer.Option("gpt-5", "--model", "-m"),
+    workspace: Optional[str] = typer.Option(None, "--workspace", "-w"),
+):
     """Run Stage 5 review only."""
     project_dir = project_dir.resolve()
     load_env_overrides(project_dir)
-    stage_5_review({}, project_dir, non_interactive=yes)
+    stage_5_review({}, project_dir, non_interactive=yes, provider=provider, model=model, workspace=workspace)
 
 @app.command()
-def finalize():
+def finalize(project_dir: Path = typer.Option(Path.cwd(), "--project-dir")):
     """Run Stage 6 finalization only."""
-    stage_6_finalize({})
+    project_dir = project_dir.resolve()
+    load_env_overrides(project_dir)
+    stage_6_finalize({}, project_dir)
 
 @app.command()
 def implement(yes: bool = typer.Option(False, "--yes"), project_dir: Path = typer.Option(Path.cwd(), "--project-dir")):
     """Run Stage 4 implementation only."""
     project_dir = project_dir.resolve()
     load_env_overrides(project_dir)
     stage_4_implement({"idea": "Project Tasks"}, project_dir, non_interactive=yes)
```


Total usage est:       1 Premium request
Total duration (API):  27.5s
Total duration (wall): 29.8s
Total code changes:    0 lines added, 0 lines removed
Usage by model:
    gpt-5                93.6k input, 4.7k output, 0 cache read, 0 cache write (Est. 1 Premium request)
