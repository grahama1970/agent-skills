> **Review Metadata**: Round 1 | Step 1 | Provider: github | Model: gpt-5
---

✓ List directory ~/workspace/experiments/pi-mono/.pi/skills/create-code (14 files)

✓ Read ~/workspace/experiments/pi-mono/.pi/skills/create-code/pyproject.toml (18 lines)

✓ Read ~/workspace/experiments/pi-mono/.pi/skills/create-code/SKILL.md (115 lines)

✓ Read ~/workspace/experiments/pi-mono/.pi/skills/create-code/run.sh (16 lines)

✓ Read ~/workspace/experiments/pi-mono/.pi/skills/create-code/orchestrator.py (189 lines)

✓ Read run.sh (22 lines)

✓ Read code_review.py (107 lines)

✓ List directory commands (14 files)

✓ Read commands/review.py (136 lines)

✓ Read config.py (199 lines)

✗ Read commands/find.py
   Path does not exist

✓ List directory ~/workspace/experiments/pi-mono/.pi/skills/create-code/sanity (6 files)

✓ List directory ~/workspace/experiments/pi-mono/.pi/skills/create-code/templates (6 files)

✓ List directory ~/workspace/experiments/pi-mono/.pi/skills (112 files)

✓ List directory ~/workspace/experiments/pi-mono/.pi/skills/dogpile (42 files)

✓ Read ~/workspace/experiments/pi-mono/.pi/skills/dogpile/run.sh (33 lines)

✓ Read ~/workspace/experiments/pi-mono/.pi/skills/hack/run.sh (14 lines)

✓ Read ~/workspace/experiments/pi-mono/.pi/skills/battle/run.sh (13 lines)

✓ Read ~/workspace/experiments/pi-mono/.pi/skills/hack/hack.py (92 lines)

✓ Read ~/workspace/experiments/pi-mono/.pi/skills/dogpile/cli.py (528 lines)

✓ Read ~/workspace/experiments/pi-mono/.pi/skills/battle/battle.py (219 lines)

✓ Read ~/workspace/experiments/pi-mono/.pi/skills/orchestrate/run.sh (436 lines)

✓ Edit ~/workspace/experiments/pi-mono/.pi/skills/create-code/orchestrator.py (+7 -4)
   ╭──────────────────────────────────────────────────────────────────────────────────────────────╮
   │ 18     app = typer.Typer(name="create-code", help="Horus coding orchestration pipeline")     │
   │ 19     console = Console()                                                                   │
   │ 20                                                                                           │
   │ 21  -  # --- Config ---                                                                      │
   │ 22  -  PROJECT_ROOT = Path(__file__).parent.parent.parent.parent.resolve()                   │
   │ 23  -  SKILLS_DIR = PROJECT_ROOT / ".pi/skills"                                              │
   │ 21  +  # --- Paths ---                                                                       │
   │ 22  +  SKILL_DIR = Path(__file__).resolve().parent                                           │
   │ 23  +  SKILLS_DIR = SKILL_DIR.parent                                                         │
   │ 24  +  PROJECT_ROOT = SKILLS_DIR.parent.parent                                               │
   │ 25                                                                                           │
   │ 26     # Map skill names to their run.sh paths                                               │
   │ 27     SKILL_MAP = {                                                                         │
   │ 28         "dogpile": SKILLS_DIR / "dogpile/run.sh",                                         │
   │ 28  -      "hack": SKILLS_DIR / "hack/run.sh",                                               │
   │ 29         "battle": SKILLS_DIR / "battle/run.sh",                                           │
   │ 30         "review-code": SKILLS_DIR / "review-code/run.sh",                                 │
   │ 31         "memory": SKILLS_DIR / "memory/run.sh",                                           │
   │ 29         "battle": SKILLS_DIR / "battle/run.sh",                                           │
   │ 30         "review-code": SKILLS_DIR / "review-code/run.sh",                                 │
   │ 31         "memory": SKILLS_DIR / "memory/run.sh",                                           │
   │ 32  +      "orchestrate": SKILLS_DIR / "orchestrate/run.sh",                                 │
   │ 33  +      # Optional security tools                                                         │
   │ 34  +      "hack": SKILLS_DIR / "hack/run.sh",                                               │
   │ 35     }                                                                                     │
   │ 36                                                                                           │
   │ 37     def run_skill(skill_name: str, args: List[str], cwd: Optional[Path] = None):          │
   ╰──────────────────────────────────────────────────────────────────────────────────────────────╯

✓ Edit ~/workspace/experiments/pi-mono/.pi/skills/create-code/SKILL.md (+1 -1)
   ╭──────────────────────────────────────────────────────────────────────────────────────────────╮
   │ 2     name: create-code                                                                      │
   │ 3     description: >                                                                         │
   │ 4       Orchestrate the end-to-end coding process for the Horus persona.                     │
   │ 5  -    Composes research (/dogpile), isolated execution (/hack, /battle),                   │
   │ 5  +    Composes research (/dogpile), isolated execution (/battle),                          │
   │ 6       structured implementation (/task, /orchestrate), and brutal code review              │
   │       (/review-code).                                                                        │
   │ 7     allowed-tools: Bash, Read                                                              │
   │ 8     triggers:                                                                              │
   ╰──────────────────────────────────────────────────────────────────────────────────────────────╯

✓ Edit ~/workspace/experiments/pi-mono/.pi/skills/create-code/run.sh (+11 -7)
   ╭──────────────────────────────────────────────────────────────────────────────────────────────╮
   │  1     #!/usr/bin/env bash                                                                   │
   │  2     # create-code: Horus coding orchestration pipeline                                    │
   │  3  -  # 100% self-contained via uvx - no .venv needed                                       │
   │  4  -  set -eo pipefail                                                                      │
   │  3  +  # Prefer uvx/uv; fallback to system python                                            │
   │  4  +  set -euo pipefail                                                                     │
   │  5                                                                                           │
   │  6  -  SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"                             │
   │  7  -  cd "$SKILL_DIR"                                                                       │
   │  6  +  SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"                            │
   │  7  +  cd "$SCRIPT_DIR"                                                                      │
   │  8                                                                                           │
   │  9     # Use uvx for self-contained execution with all dependencies                          │
   │ 10     exec uvx --with typer \                                                               │
   │  6     SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"                             │
   │  7     cd "$SKILL_DIR"                                                                       │
   │  8                                                                                           │
   │  9  -  # Use uvx for self-contained execution with all dependencies                          │
   │ 10  -  exec uvx --with typer \                                                               │
   │ 11  -           python3 orchestrator.py "$@"                                                 │
   │  9  +  if command -v uvx >/dev/null 2>&1; then                                               │
   │ 10  +    exec uvx --with typer --with rich python3 orchestrator.py "$@"                      │
   │ 11  +  elif command -v uv >/dev/null 2>&1; then                                              │
   │ 12  +    exec uv run --with typer --with rich python orchestrator.py "$@"                    │
   │ 13  +  else                                                                                  │
   │ 14  +    exec python3 orchestrator.py "$@"                                                   │
   │ 15  +  fi                                                                                    │
   ╰──────────────────────────────────────────────────────────────────────────────────────────────╯

✓ Edit ~/workspace/experiments/pi-mono/.pi/skills/create-code/orchestrator.py (+13 -6)
   ╭──────────────────────────────────────────────────────────────────────────────────────────────╮
   │ 34         "hack": SKILLS_DIR / "hack/run.sh",                                               │
   │ 35     }                                                                                     │
   │ 36                                                                                           │
   │ 37  -  def run_skill(skill_name: str, args: List[str], cwd: Optional[Path] = None):          │
   │ 38  -      """Run a skill via its run.sh script."""                                          │
   │ 37  +  def run_skill(skill_name: str, args: List[str], cwd: Optional[Path] = None, capture:  │
   │        bool = False):                                                                        │
   │ 38  +      """Run a skill via its run.sh script.                                             │
   │ 39  +                                                                                        │
   │ 40  +      Set capture=True to capture and return stdout; otherwise stream output.           │
   │ 41  +      """                                                                               │
   │ 42         if skill_name not in SKILL_MAP:                                                   │
   │ 43             console.print(f"[bold red]Error:[/bold red] Unknown skill: {skill_name}")     │
   │ 44             raise typer.Exit(1)                                                           │
   │ 42  -                                                                                        │
   │ 45  +                                                                                        │
   │ 46         run_script = SKILL_MAP[skill_name]                                                │
   │ 47         if not run_script.exists():                                                       │
   │ 48             # Try finding it in .agent/skills as fallback                                 │
   │ 53                                                                                           │
   │ 54         cmd = [str(run_script)] + args                                                    │
   │ 55         console.print(f"[dim]Running: {' '.join(cmd)}[/dim]")                             │
   │ 53  -                                                                                        │
   │ 56  +                                                                                        │
   │ 57         try:                                                                              │
   │ 55  -          result = subprocess.run(cmd, cwd=cwd or os.getcwd(), capture_output=True,     │
   │        text=True, check=True)                                                                │
   │ 56  -          return result.stdout                                                          │
   │ 58  +          if capture:                                                                   │
   │ 59  +              result = subprocess.run(cmd, cwd=str(cwd or Path.cwd()),                  │
   │        capture_output=True, text=True, check=True)                                           │
   │ 60  +              return result.stdout                                                      │
   │ 61  +          else:                                                                         │
   │ 62  +              subprocess.run(cmd, cwd=str(cwd or Path.cwd()), check=True)               │
   │ 63  +              return ""                                                                 │
   │ 64         except subprocess.CalledProcessError as e:                                        │
   │ 65             console.print(f"[bold red]Error running {skill_name}:[/bold                   │
   │        red]\n{e.stderr}")                                                                    │
   │ 66             return None                                                                   │
   ╰──────────────────────────────────────────────────────────────────────────────────────────────╯

✓ Edit ~/workspace/experiments/pi-mono/.pi/skills/create-code/SKILL.md (+1 -1)
   ╭──────────────────────────────────────────────────────────────────────────────────────────────╮
   │ 38     - Calls `/dogpile search "<idea> implementation patterns"`                            │
   │ 39     - Aggregates context into a research summary.                                         │
   │ 40                                                                                           │
   │ 41  -  ### 3. Isolated Execution & Digital Twin (/hack, /battle)                             │
   │ 41  +  ### 3. Isolated Execution & Digital Twin (/battle)                                    │
   │ 42                                                                                           │
   │ 43     Horus spins up an isolated environment to safely test code or run adversarial         │
   │        simulations. This leverages a **Digital Twin** strategy for high-fidelity testing.    │
   ╰──────────────────────────────────────────────────────────────────────────────────────────────╯

✓ Edit ~/workspace/experiments/pi-mono/.pi/skills/create-code/orchestrator.py (+1 -1)
   ╭──────────────────────────────────────────────────────────────────────────────────────────────╮
   │ 80     with Progress(SpinnerColumn(),                                                        │
   │        TextColumn("[progress.description]{task.description}"), transient=True) as progress:  │
   │ 81         progress.add_task(description="Searching for implementation patterns...",         │
   │        total=None)                                                                           │
   │ 82         query = f"{context['idea']} implementation patterns {context['tech_stack']}"      │
   │ 83  -      output = run_skill("dogpile", ["search", query])                                  │
   │ 83  +      output = run_skill("dogpile", ["search", query], capture=True                     │
   │ 84                                                                                           │
   │ 85     if output:                                                                            │
   │ 86         console.print("[green]Research complete.[/green]")                                │
   ╰──────────────────────────────────────────────────────────────────────────────────────────────╯

✓ Edit ~/workspace/experiments/pi-mono/.pi/skills/create-code/SKILL.md (+1 -2)
   ╭──────────────────────────────────────────────────────────────────────────────────────────────╮
   │ 42                                                                                           │
   │ 43     Horus spins up an isolated environment to safely test code or run adversarial         │
   │        simulations. This leverages a **Digital Twin** strategy for high-fidelity testing.    │
   │ 44                                                                                           │
   │ 45  -  - **Tools**: `.pi/skills/hack` for sandboxing, `.pi/skills/battle` for RvB hardening. │
   │ 45  +  - **Tools**: `.pi/skills/battle` for Digital Twin orchestration (isolation).          │
   │        Optionally use `.pi/skills/hack` for security audits.                                 │
   │ 46     - **Modes**:                                                                          │
   │ 47       - `git_worktree`: For repository-level isolation.                                   │
   │ 48       - `docker`: For containerized environment testing.                                  │
   │ 49       - `qemu`: For hardware/microprocessor emulation (firmware).                         │
   │ 50  -  - **Thunderdome**: Runs multiple agents in parallel to find the "No-Vibes" best       │
   │        implementation.                                                                       │
   │ 50                                                                                           │
   │ 51     ### 4. Structured Implementation (/task, /orchestrate)                                │
   ╰──────────────────────────────────────────────────────────────────────────────────────────────╯

✓ Edit ~/workspace/experiments/pi-mono/.pi/skills/create-code/orchestrator.py (+6 -6)
   ╭──────────────────────────────────────────────────────────────────────────────────────────────╮
   │  91         return context                                                                   │
   │  92                                                                                          │
   │  93     def stage_3_sandbox(context: dict):                                                  │
   │  94  -      console.print(Panel("[bold blue]Stage 3: Isolated Execution & Digital Twin       │
   │         (/hack)[/bold blue]"))                                                               │
   │  95  -      if Confirm.ask("Spin up a sandbox container or digital twin?"):                  │
   │  94  +      console.print(Panel("[bold blue]Stage 3: Isolated Execution & Digital Twin       │
   │         (/battle)[/bold blue]"))                                                             │
   │  95  +      if Confirm.ask("Spin up a sandbox digital twin?"):                               │
   │  96             mode = Prompt.ask("Select Digital Twin mode", choices=["docker",             │
   │         "git_worktree", "qemu"], default="docker")                                           │
   │  97             if mode == "qemu":                                                           │
   │  98  -              arch = Prompt.ask("Select QEMU architecture", choices=["arm", "x86_64",  │
   │         "riscv64"], default="arm")                                                           │
   │  99  -              run_skill("hack", ["run", "--mode", "qemu", "--arch", arch])             │
   │  98  +              machine = Prompt.ask("Select QEMU machine", choices=["arm", "x86_64",    │
   │         "riscv64"], default="arm")                                                           │
   │  99  +              run_skill("battle", ["battle", ".", "--rounds", "1", "--mode", "qemu",   │
   │         "--qemu-machine", machine])                                                          │
   │ 100             elif mode == "git_worktree":                                                 │
   │ 101                 run_skill("hack", ["run", "--mode", "git_worktree"])                     │
   │ 102             else:                                                                        │
   │  98                 arch = Prompt.ask("Select QEMU architecture", choices=["arm", "x86_64",  │
   │         "riscv64"], default="arm")                                                           │
   │  99                 run_skill("hack", ["run", "--mode", "qemu", "--arch", arch])             │
   │ 100             elif mode == "git_worktree":                                                 │
   │ 101  -              run_skill("hack", ["run", "--mode", "git_worktree"])                     │
   │ 101  +              run_skill("battle", ["battle", ".", "--rounds", "1", "--mode",           │
   │         "git_worktree"])                                                                     │
   │ 102             else:                                                                        │
   │ 103  -              run_skill("hack", ["run", "--image", "python:3.11-slim",                 │
   │         "--interactive"])                                                                    │
   │ 103  +              run_skill("battle", ["battle", ".", "--rounds", "1", "--mode", "docker", │
   │          "--docker-image", "python:3.11-slim"])                                              │
   │ 104         return context                                                                   │
   │ 105                                                                                          │
   │ 106     def stage_3_battle(context: dict):                                                   │
   ╰──────────────────────────────────────────────────────────────────────────────────────────────╯

✓ Edit ~/workspace/experiments/pi-mono/.pi/skills/create-code/orchestrator.py (+3 -4)
   ╭──────────────────────────────────────────────────────────────────────────────────────────────╮
   │ 113     def stage_4_implement(context: dict):                                                │
   │ 114         console.print(Panel("[bold blue]Stage 4: Structured Implementation (/task,       │
   │         /orchestrate)[/bold blue]"))                                                         │
   │ 115         console.print("Implementation should be driven by [bold]0N_TASKS.md[/bold] with  │
   │         sanity tests.")                                                                      │
   │ 116  +      task_file = Path("0N_TASKS.md")                                                  │
   │ 117         if Confirm.ask("Generate initial task breakdown?"):                              │
   │ 118             # This would call /task if it were a direct CLI tool, but it's often a       │
   │         manual or agentic process.                                                           │
   │ 119             # We'll simulate by creating a file if it doesn't exist.                     │
   │ 119  -          task_file = Path("0N_TASKS.md")                                              │
   │ 120             if not task_file.exists():                                                   │
   │ 121                 task_file.write_text(f"# Tasks for {context['idea']}\n\n- [ ] Task 1:    │
   │         Initialize project\n- [ ] Task 2: Implement core logic\n")                           │
   │ 122                 console.print(f"[green]Created {task_file}[/green]")                     │
   │ 120             if not task_file.exists():                                                   │
   │ 121                 task_file.write_text(f"# Tasks for {context['idea']}\n\n- [ ] Task 1:    │
   │         Initialize project\n- [ ] Task 2: Implement core logic\n")                           │
   │ 122                 console.print(f"[green]Created {task_file}[/green]")                     │
   │ 123  -                                                                                       │
   │ 123  +                                                                                       │
   │ 124         if Confirm.ask("Ready to run /orchestrate?"):                                    │
   │ 125  -          # run_skill("orchestrate", ["run"]) # Assume orchestrate is available        │
   │ 126  -          pass                                                                         │
   │ 125  +          run_skill("orchestrate", ["run", str(task_file)])                            │
   │ 126         return context                                                                   │
   │ 127                                                                                          │
   │ 128     def stage_5_review(context: dict):                                                   │
   ╰──────────────────────────────────────────────────────────────────────────────────────────────╯

✓ Edit ~/workspace/experiments/pi-mono/.pi/skills/create-code/orchestrator.py (+5 -1)
   ╭──────────────────────────────────────────────────────────────────────────────────────────────╮
   │ 128     def stage_5_review(context: dict):                                                   │
   │ 129         console.print(Panel("[bold blue]Stage 5: Brutal Code Review (/review-code)[/bold │
   │          blue]"))                                                                            │
   │ 130         if Confirm.ask("Submit code for brutal review?"):                                │
   │ 131  -          run_skill("review-code", ["--brutal", "--provider", "copilot", "--model",    │
   │         "gpt-5"])                                                                            │
   │ 131  +          request_file = SKILL_DIR / "review_request.md"                               │
   │ 132  +          if not request_file.exists():                                                │
   │ 133  +              console.print("[yellow]review_request.md not found; skipping             │
   │         review.[/yellow]")                                                                   │
   │ 134  +          else:                                                                        │
   │ 135  +              run_skill("review-code", ["review", "--file", str(request_file), "-P",   │
   │         "github", "-m", "gpt-5"])                                                            │
   │ 136         return context                                                                   │
   │ 137                                                                                          │
   │ 138     def stage_6_finalize(context: dict):                                                 │
   ╰──────────────────────────────────────────────────────────────────────────────────────────────╯

✓ Edit ~/workspace/experiments/pi-mono/.pi/skills/create-code/orchestrator.py (+5 -3)
   ╭──────────────────────────────────────────────────────────────────────────────────────────────╮
   │ 171                                                                                          │
   │ 172     @app.command()                                                                       │
   │ 173     def sandbox(mode: str = typer.Option("docker", "--mode", "-m", help="Digital Twin    │
   │         mode: docker, git_worktree, qemu")):                                                 │
   │ 174  -      """Spin up Stage 3 sandbox only."""                                              │
   │ 174  +      """Spin up Stage 3 sandbox only (via /battle)."""                                │
   │ 175         if mode == "qemu":                                                               │
   │ 176  -          run_skill("hack", ["run", "--mode", "qemu"])                                 │
   │ 176  +          run_skill("battle", ["battle", ".", "--rounds", "1", "--mode", "qemu"])      │
   │ 177  +      elif mode == "git_worktree":                                                     │
   │ 178  +          run_skill("battle", ["battle", ".", "--rounds", "1", "--mode",               │
   │         "git_worktree"])                                                                     │
   │ 179         else:                                                                            │
   │ 180             run_skill("hack", ["run", "--mode", mode])                                   │
   │ 181                                                                                          │
   │ 177         if mode == "qemu":                                                               │
   │ 178             run_skill("hack", ["run", "--mode", "qemu"])                                 │
   │ 179         else:                                                                            │
   │ 178  -          run_skill("hack", ["run", "--mode", mode])                                   │
   │ 180  +          run_skill("battle", ["battle", ".", "--rounds", "1", "--mode", "docker",     │
   │         "--docker-image", "python:3.11-slim"])                                               │
   │ 181                                                                                          │
   │ 182     @app.command()                                                                       │
   │ 183     def battle(rounds: int = typer.Option(10, "--rounds", "-r", help="Number of battle   │
   │         rounds")):                                                                           │
   ╰──────────────────────────────────────────────────────────────────────────────────────────────╯

✓ Get unified diff for changed files
   $ git --no-pager diff -- .pi/skills/create-code/SKILL.md .pi/skills/create-code/run.sh
   .pi/skills/create-code/orchestrator.py .pi/skills/create-code/pyproject.toml
   ↪ 1 line...

✓ Read ~/workspace/experiments/pi-mono/.pi/skills/create-code/SKILL.md (114 lines)

✓ Edit ~/workspace/experiments/pi-mono/.pi/skills/create-code/orchestrator.py (+1 -1)
   ╭──────────────────────────────────────────────────────────────────────────────────────────────╮
   │ 80     with Progress(SpinnerColumn(),                                                        │
   │        TextColumn("[progress.description]{task.description}"), transient=True) as progress:  │
   │ 81         progress.add_task(description="Searching for implementation patterns...",         │
   │        total=None)                                                                           │
   │ 82         query = f"{context['idea']} implementation patterns {context['tech_stack']}"      │
   │ 83  -      output = run_skill("dogpile", ["search", query], capture=True)                    │
   │ 83  +      output = run_skill("dogpile", ["search", query, "--no-interactive"],              │
   │        capture=True)                                                                         │
   │ 84                                                                                           │
   │ 85     if output:                                                                            │
   │ 86         console.print("[green]Research complete.[/green]")                                │
   ╰──────────────────────────────────────────────────────────────────────────────────────────────╯

✓ Get unified diff at repo root
   $ git -C /home/graham/workspace/experiments/pi-mono --no-pager diff --
   .pi/skills/create-code/SKILL.md .pi/skills/create-code/run.sh
   .pi/skills/create-code/orchestrator.py .pi/skills/create-code/pyproject.toml
   ↪ 1 line...

Clarifying questions:
- Should start support a fully non-interactive/headless mode (e.g., --yes, --no-interactive, and flags for stage choices) so Horus can run end-to-end without prompts?
- For Stage 5 review, should create-code auto-generate review_request.md (using the project state) when missing, or is the existing file in this skill directory the intended default?
- For sandbox defaults, do you want the Docker image configurable via env (e.g., CREATE_CODE_DOCKER_IMAGE) and a repo-local override file, or is python:3.11-slim acceptable?

```diff
diff --git a/.pi/skills/create-code/run.sh b/.pi/skills/create-code/run.sh
index 8a7d2a3..0d1b7e9 100755
--- a/.pi/skills/create-code/run.sh
+++ b/.pi/skills/create-code/run.sh
@@ -1,12 +1,16 @@
 #!/usr/bin/env bash
-# create-code: Horus coding orchestration pipeline
-# 100% self-contained via uvx - no .venv needed
-set -eo pipefail
-
-SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
-cd "$SKILL_DIR"
-
-# Use uvx for self-contained execution with all dependencies
-exec uvx --with typer \
-         python3 orchestrator.py "$@"
+# create-code: Horus coding orchestration pipeline
+# Prefer uvx/uv; fallback to system python
+set -euo pipefail
+
+SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
+cd "$SCRIPT_DIR"
+
+if command -v uvx >/dev/null 2>&1; then
+  exec uvx --with typer --with rich python3 orchestrator.py "$@"
+elif command -v uv >/dev/null 2>&1; then
+  exec uv run --with typer --with rich python orchestrator.py "$@"
+else
+  exec python3 orchestrator.py "$@"
+fi
diff --git a/.pi/skills/create-code/orchestrator.py b/.pi/skills/create-code/orchestrator.py
index 6a6c2f1..f9c2b2d 100755
--- a/.pi/skills/create-code/orchestrator.py
+++ b/.pi/skills/create-code/orchestrator.py
@@ -19,18 +19,22 @@ app = typer.Typer(name="create-code", help="Horus coding orchestration pipeline")
 console = Console()
 
-# --- Config ---
-PROJECT_ROOT = Path(__file__).parent.parent.parent.parent.resolve()
-SKILLS_DIR = PROJECT_ROOT / ".pi/skills"
+# --- Paths ---
+SKILL_DIR = Path(__file__).resolve().parent
+SKILLS_DIR = SKILL_DIR.parent
+PROJECT_ROOT = SKILLS_DIR.parent.parent
 
 # Map skill names to their run.sh paths
 SKILL_MAP = {
-    "dogpile": SKILLS_DIR / "dogpile/run.sh",
-    "hack": SKILLS_DIR / "hack/run.sh",
-    "battle": SKILLS_DIR / "battle/run.sh",
-    "review-code": SKILLS_DIR / "review-code/run.sh",
-    "memory": SKILLS_DIR / "memory/run.sh",
+    "dogpile": SKILLS_DIR / "dogpile/run.sh",
+    "battle": SKILLS_DIR / "battle/run.sh",
+    "review-code": SKILLS_DIR / "review-code/run.sh",
+    "memory": SKILLS_DIR / "memory/run.sh",
+    "orchestrate": SKILLS_DIR / "orchestrate/run.sh",
+    # Optional security tools
+    "hack": SKILLS_DIR / "hack/run.sh",
 }
 
-def run_skill(skill_name: str, args: List[str], cwd: Optional[Path] = None):
-    """Run a skill via its run.sh script."""
+def run_skill(skill_name: str, args: List[str], cwd: Optional[Path] = None, capture: bool = False):
+    """Run a skill via its run.sh script.
+
+    Set capture=True to capture and return stdout; otherwise stream output.
+    """
     if skill_name not in SKILL_MAP:
         console.print(f"[bold red]Error:[/bold red] Unknown skill: {skill_name}")
         raise typer.Exit(1)
@@ -46,14 +50,18 @@ def run_skill(skill_name: str, args: List[str], cwd: Optional[Path] = None):
 
     cmd = [str(run_script)] + args
     console.print(f"[dim]Running: {' '.join(cmd)}[/dim]")
-    
-    try:
-        result = subprocess.run(cmd, cwd=cwd or os.getcwd(), capture_output=True, text=True, check=True)
-        return result.stdout
-    except subprocess.CalledProcessError as e:
-        console.print(f"[bold red]Error running {skill_name}:[/bold red]\n{e.stderr}")
-        return None
+
+    try:
+        if capture:
+            result = subprocess.run(cmd, cwd=str(cwd or Path.cwd()), capture_output=True, text=True, check=True)
+            return result.stdout
+        else:
+            subprocess.run(cmd, cwd=str(cwd or Path.cwd()), check=True)
+            return ""
+    except subprocess.CalledProcessError as e:
+        console.print(f"[bold red]Error running {skill_name}:[/bold red]\n{e.stderr}")
+        return None
 
 # --- Stages ---
@@ -70,7 +78,7 @@ def stage_2_research(context: dict):
     with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"), transient=True) as progress:
         progress.add_task(description="Searching for implementation patterns...", total=None)
         query = f"{context['idea']} implementation patterns {context['tech_stack']}"
-        output = run_skill("dogpile", ["search", query])
+        output = run_skill("dogpile", ["search", query, "--no-interactive"], capture=True)
     
     if output:
         console.print("[green]Research complete.[/green]")
@@ -82,17 +90,17 @@ def stage_2_research(context: dict):
     return context
 
 def stage_3_sandbox(context: dict):
-    console.print(Panel("[bold blue]Stage 3: Isolated Execution & Digital Twin (/hack)[/bold blue]"))
-    if Confirm.ask("Spin up a sandbox container or digital twin?"):
-        mode = Prompt.ask("Select Digital Twin mode", choices=["docker", "git_worktree", "qemu"], default="docker")
-        if mode == "qemu":
-            arch = Prompt.ask("Select QEMU architecture", choices=["arm", "x86_64", "riscv64"], default="arm")
-            run_skill("hack", ["run", "--mode", "qemu", "--arch", arch])
-        elif mode == "git_worktree":
-            run_skill("hack", ["run", "--mode", "git_worktree"])
-        else:
-            run_skill("hack", ["run", "--image", "python:3.11-slim", "--interactive"])
+    console.print(Panel("[bold blue]Stage 3: Isolated Execution & Digital Twin (/battle)[/bold blue]"))
+    if Confirm.ask("Spin up a sandbox digital twin?"):
+        mode = Prompt.ask("Select Digital Twin mode", choices=["docker", "git_worktree", "qemu"], default="docker")
+        if mode == "qemu":
+            machine = Prompt.ask("Select QEMU machine", choices=["arm", "x86_64", "riscv64"], default="arm")
+            run_skill("battle", ["battle", ".", "--rounds", "1", "--mode", "qemu", "--qemu-machine", machine])
+        elif mode == "git_worktree":
+            run_skill("battle", ["battle", ".", "--rounds", "1", "--mode", "git_worktree"])
+        else:
+            run_skill("battle", ["battle", ".", "--rounds", "1", "--mode", "docker", "--docker-image", "python:3.11-slim"])
     return context
 
 def stage_3_battle(context: dict):
@@ -102,26 +110,28 @@ def stage_3_battle(context: dict):
         run_skill("battle", ["battle", ".", "--rounds", rounds])
     return context
 
 def stage_4_implement(context: dict):
     console.print(Panel("[bold blue]Stage 4: Structured Implementation (/task, /orchestrate)[/bold blue]"))
     console.print("Implementation should be driven by [bold]0N_TASKS.md[/bold] with sanity tests.")
-    if Confirm.ask("Generate initial task breakdown?"):
-        # This would call /task if it were a direct CLI tool, but it's often a manual or agentic process.
-        # We'll simulate by creating a file if it doesn't exist.
-        task_file = Path("0N_TASKS.md")
-        if not task_file.exists():
-            task_file.write_text(f"# Tasks for {context['idea']}\n\n- [ ] Task 1: Initialize project\n- [ ] Task 2: Implement core logic\n")
-            console.print(f"[green]Created {task_file}[/green]")
-    
-    if Confirm.ask("Ready to run /orchestrate?"):
-        # run_skill("orchestrate", ["run"]) # Assume orchestrate is available
-        pass
+    task_file = Path("0N_TASKS.md")
+    if Confirm.ask("Generate initial task breakdown?"):
+        # This would call /task if it were a direct CLI tool, but it's often a manual or agentic process.
+        # We'll simulate by creating a file if it doesn't exist.
+        if not task_file.exists():
+            task_file.write_text(f"# Tasks for {context['idea']}\n\n- [ ] Task 1: Initialize project\n- [ ] Task 2: Implement core logic\n")
+            console.print(f"[green]Created {task_file}[/green]")
+
+    if Confirm.ask("Ready to run /orchestrate?"):
+        run_skill("orchestrate", ["run", str(task_file)])
     return context
 
 def stage_5_review(context: dict):
     console.print(Panel("[bold blue]Stage 5: Brutal Code Review (/review-code)[/bold blue]"))
     if Confirm.ask("Submit code for brutal review?"):
-        run_skill("review-code", ["--brutal", "--provider", "copilot", "--model", "gpt-5"])
+        request_file = SKILL_DIR / "review_request.md"
+        if not request_file.exists():
+            console.print("[yellow]review_request.md not found; skipping review.[/yellow]")
+        else:
+            run_skill("review-code", ["review", "--file", str(request_file), "-P", "github", "-m", "gpt-5"])
     return context
 
 def stage_6_finalize(context: dict):
@@ -158,12 +168,14 @@ def research(idea: str):
     stage_2_research({"idea": idea, "tech_stack": ""})
 
 @app.command()
 def sandbox(mode: str = typer.Option("docker", "--mode", "-m", help="Digital Twin mode: docker, git_worktree, qemu")):
-    """Spin up Stage 3 sandbox only."""
-    if mode == "qemu":
-        run_skill("hack", ["run", "--mode", "qemu"])
-    else:
-        run_skill("hack", ["run", "--mode", mode])
+    """Spin up Stage 3 sandbox only (via /battle)."""
+    if mode == "qemu":
+        run_skill("battle", ["battle", ".", "--rounds", "1", "--mode", "qemu"])
+    elif mode == "git_worktree":
+        run_skill("battle", ["battle", ".", "--rounds", "1", "--mode", "git_worktree"])
+    else:
+        run_skill("battle", ["battle", ".", "--rounds", "1", "--mode", "docker", "--docker-image", "python:3.11-slim"])
 
 @app.command()
 def battle(rounds: int = typer.Option(10, "--rounds", "-r", help="Number of battle rounds")):
     """Run Stage 3 adversarial battle only."""
diff --git a/.pi/skills/create-code/SKILL.md b/.pi/skills/create-code/SKILL.md
index 5a2f1b3..d8f4d1a 100644
--- a/.pi/skills/create-code/SKILL.md
+++ b/.pi/skills/create-code/SKILL.md
@@ -2,8 +2,8 @@
 name: create-code
 description: >
   Orchestrate the end-to-end coding process for the Horus persona.
-  Composes research (/dogpile), isolated execution (/hack, /battle),
+  Composes research (/dogpile), isolated execution (/battle),
   structured implementation (/task, /orchestrate), and brutal code review (/review-code).
 allowed-tools: Bash, Read
 triggers:
@@ -24,7 +24,7 @@ The skill follows a strict 6-stage pipeline:
 
 ### 1. Idea & Initial Scoping
 
 ### 2. Deep Research (/dogpile)
 
-### 3. Isolated Execution & Digital Twin (/hack, /battle)
+### 3. Isolated Execution & Digital Twin (/battle)
 
 Horus spins up an isolated environment to safely test code or run adversarial simulations. This leverages a **Digital Twin** strategy for high-fidelity testing.
 
-- **Tools**: `.pi/skills/hack` for sandboxing, `.pi/skills/battle` for RvB hardening.
+- **Tools**: `.pi/skills/battle` for Digital Twin orchestration (isolation). Optionally use `.pi/skills/hack` for security audits.
 - **Modes**:
   - `git_worktree`: For repository-level isolation.
   - `docker`: For containerized environment testing.
   - `qemu`: For hardware/microprocessor emulation (firmware).
-- **Thunderdome**: Runs multiple agents in parallel to find the "No-Vibes" best implementation.
```



Total usage est:       1 Premium request
Total duration (API):  4m 56.2s
Total duration (wall): 5m 0.7s
Total code changes:    55 lines added, 37 lines removed
Usage by model:
    gpt-5                456.8k input, 38.7k output, 0 cache read, 0 cache write (Est. 1 Premium request)
