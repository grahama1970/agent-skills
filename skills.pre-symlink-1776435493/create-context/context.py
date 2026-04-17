#!/usr/bin/env python3
"""
Generate comprehensive CONTEXT.md for agent handoff.

Captures current state, decisions, lessons learned, and next steps
so another agent can continue with zero prior context.

Key feature: reads existing project knowledge (CLAUDE.md, MEMORY.md,
agent-inbox, existing CONTEXT.md) to produce context that reflects
deep understanding, not just git scraping.
"""

import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

try:
    import typer
    from rich.console import Console
    from rich.panel import Panel
    from rich.prompt import Prompt, Confirm
except ImportError:
    print("Missing dependencies. Run: uv pip install typer rich")
    sys.exit(1)

from detectors import (
    detect_agent_inbox,
    detect_architecture_diagram,
    detect_assessment,
    detect_claude_md,
    detect_companion_repos,
    detect_dependency_graph,
    detect_environment_snapshot,
    detect_error_log_summary,
    detect_existing_context,
    detect_git_info,
    detect_key_code_snippets,
    detect_memory_md,
    detect_modified_files,
    detect_running_processes,
    detect_session_transcript,
    detect_test_coverage,
    infer_focus_from_git,
    run_command,
)
from renderer import generate_markdown

app = typer.Typer(help="Generate CONTEXT.md for agent handoff")
console = Console()

# Default paths — overridden by --project-root
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
DEFAULT_OUTPUT = PROJECT_ROOT / "local" / "docs" / "CONTEXT.md"


@dataclass
class ContextData:
    """Data collected for CONTEXT.md generation."""

    # Header
    title: str = ""
    focus: str = ""
    date: str = field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d"))
    git_branch: str = ""

    # Sections
    current_state: str = ""
    files_modified: list[str] = field(default_factory=list)
    decisions_made: list[str] = field(default_factory=list)
    research_conducted: str = ""
    lessons_learned: list[str] = field(default_factory=list)
    known_issues: list[str] = field(default_factory=list)
    open_questions: list[str] = field(default_factory=list)
    next_steps_immediate: list[str] = field(default_factory=list)
    next_steps_nearterm: list[str] = field(default_factory=list)
    next_steps_longterm: list[str] = field(default_factory=list)
    how_to_continue: str = ""
    related_skills: list[str] = field(default_factory=list)

    # Auto-detected
    git_status: str = ""
    git_diff_stat: str = ""
    recent_commits: str = ""
    todo_state: str = ""
    test_results: str = ""

    # Additional elements
    architecture_diagram: str = ""
    key_code_snippets: list[dict] = field(default_factory=list)
    performance_notes: str = ""
    test_coverage: dict = field(default_factory=dict)
    dependency_graph: list[dict] = field(default_factory=list)
    error_log_summary: list[str] = field(default_factory=list)
    environment_snapshot: dict = field(default_factory=dict)
    session_transcript_path: str = ""

    # Project knowledge (from CLAUDE.md, MEMORY.md, agent-inbox)
    project_purpose: str = ""
    project_type: str = ""
    project_status: str = ""
    memory_content: str = ""
    inbox_messages: list[str] = field(default_factory=list)
    companion_repos: list[dict] = field(default_factory=list)
    running_processes: list[str] = field(default_factory=list)
    assessment: list[str] = field(default_factory=list)


def interactive_gather(data: ContextData) -> ContextData:
    """Interactively gather context information."""
    console.print(Panel("[bold]Context Generation Interview[/bold]", style="blue"))

    # Title and focus
    data.title = Prompt.ask("Project/Feature name", default=data.title or "Current Work")
    data.focus = Prompt.ask("Session focus (brief description)", default=data.focus)

    # Current state
    console.print("\n[bold]Current State[/bold]")
    console.print("[dim]What was built/modified this session?[/dim]")
    state_items = []
    while True:
        item = Prompt.ask("Add item (or press Enter to finish)")
        if not item:
            break
        state_items.append(f"- {item}")
    data.current_state = "\n".join(state_items) if state_items else data.current_state

    # Decisions made
    console.print("\n[bold]Key Decisions[/bold]")
    console.print("[dim]What decisions were made and why?[/dim]")
    while True:
        decision = Prompt.ask("Decision (or press Enter to finish)")
        if not decision:
            break
        rationale = Prompt.ask("  Rationale", default="")
        data.decisions_made.append(f"{decision}" + (f" - {rationale}" if rationale else ""))

    # Lessons learned
    console.print("\n[bold]Lessons Learned[/bold]")
    console.print("[dim]What worked? What didn't?[/dim]")
    while True:
        lesson = Prompt.ask("Lesson (or press Enter to finish)")
        if not lesson:
            break
        data.lessons_learned.append(lesson)

    # Known issues
    console.print("\n[bold]Known Issues/Gaps[/bold]")
    console.print("[dim]What's incomplete or broken?[/dim]")
    while True:
        issue = Prompt.ask("Issue (or press Enter to finish)")
        if not issue:
            break
        data.known_issues.append(issue)

    # Open questions
    console.print("\n[bold]Open Questions[/bold]")
    console.print("[dim]What needs clarification or user input?[/dim]")
    while True:
        question = Prompt.ask("Question (or press Enter to finish)")
        if not question:
            break
        data.open_questions.append(question)

    # Next steps
    console.print("\n[bold]Next Steps[/bold]")

    console.print("[dim]Immediate (this session):[/dim]")
    while True:
        step = Prompt.ask("Step (or press Enter to finish)")
        if not step:
            break
        data.next_steps_immediate.append(step)

    console.print("[dim]Near-term (next few sessions):[/dim]")
    while True:
        step = Prompt.ask("Step (or press Enter to finish)")
        if not step:
            break
        data.next_steps_nearterm.append(step)

    # How to continue
    console.print("\n[bold]How to Continue[/bold]")
    console.print("[dim]Commands to run, files to read first[/dim]")
    how_to = []
    while True:
        cmd = Prompt.ask("Command/instruction (or press Enter to finish)")
        if not cmd:
            break
        how_to.append(cmd)
    data.how_to_continue = "\n".join(f"- {h}" for h in how_to) if how_to else data.how_to_continue

    return data


@app.command()
def generate(
    focus: str = typer.Option("", "--focus", "-f", help="Session focus description"),
    output: Path = typer.Option(DEFAULT_OUTPUT, "--output", "-o", help="Output file path"),
    project_root: Optional[Path] = typer.Option(None, "--project-root", "-p", help="Target project root (default: auto-detect)"),
    include_git: bool = typer.Option(True, "--include-git/--no-git", help="Include git info"),
    include_tests: bool = typer.Option(False, "--include-tests/--no-tests", help="Run and include test results"),
    include_deps: bool = typer.Option(True, "--include-deps/--no-deps", help="Include dependency graph"),
    include_env: bool = typer.Option(True, "--include-env/--no-env", help="Include environment snapshot"),
    include_errors: bool = typer.Option(True, "--include-errors/--no-errors", help="Include error log summary"),
    include_snippets: bool = typer.Option(True, "--include-snippets/--no-snippets", help="Include key code snippets"),
    include_transcript: bool = typer.Option(True, "--include-transcript/--no-transcript", help="Include session transcript path"),
    include_memory: bool = typer.Option(True, "--include-memory/--no-memory", help="Include MEMORY.md content"),
    include_inbox: bool = typer.Option(True, "--include-inbox/--no-inbox", help="Check agent-inbox"),
    include_assess: bool = typer.Option(True, "--include-assess/--no-assess", help="Run code health assessment"),
    include_processes: bool = typer.Option(True, "--include-processes/--no-processes", help="Detect running processes"),
    interactive: bool = typer.Option(False, "--interactive", "-i", help="Interactive mode"),
    title: str = typer.Option("", "--title", "-t", help="Project/feature title"),
    full: bool = typer.Option(False, "--full", help="Include all optional elements"),
):
    """Generate CONTEXT.md for agent handoff."""
    global PROJECT_ROOT

    # Resolve project root
    if project_root:
        PROJECT_ROOT = project_root.resolve()
    else:
        # Try to detect from cwd or git root
        cwd = Path.cwd()
        git_root = run_command(["git", "rev-parse", "--show-toplevel"])
        if git_root:
            PROJECT_ROOT = Path(git_root)
        else:
            PROJECT_ROOT = cwd

    # Full mode enables everything
    if full:
        include_tests = include_deps = include_env = include_errors = True
        include_snippets = include_transcript = include_memory = True
        include_inbox = include_assess = include_processes = True

    console.print(f"[dim]Gathering context for: {PROJECT_ROOT}[/dim]")

    # Pre-hook: Recall prior contexts for delta/drift detection
    try:
        from memory_integration import recall_prior_contexts
        prior = recall_prior_contexts(title or PROJECT_ROOT.name)
        if prior:
            console.print(f"[dim]  Recalled prior context snapshots from memory[/dim]")
    except ImportError:
        prior = ""
    except Exception as e:
        prior = ""
        console.print(f"[dim]  Prior context recall skipped: {e}[/dim]")

    # Initialize data
    data = ContextData()

    # -- Project knowledge (CLAUDE.md, MEMORY.md) --
    console.print("[dim]  Reading project knowledge (CLAUDE.md)...[/dim]")
    claude_md = detect_claude_md(PROJECT_ROOT)
    data.project_purpose = claude_md.get("purpose", "")
    data.project_type = claude_md.get("type", "")
    data.project_status = claude_md.get("status", "")

    # Title: prefer user-provided, then CLAUDE.md purpose, then project dir name
    data.title = title or data.project_purpose or PROJECT_ROOT.name

    # -- Memory --
    if include_memory:
        console.print("[dim]  Reading MEMORY.md...[/dim]")
        data.memory_content = detect_memory_md(PROJECT_ROOT)

    # -- Companion repos --
    console.print("[dim]  Detecting companion repos...[/dim]")
    data.companion_repos = detect_companion_repos(PROJECT_ROOT, claude_md, data.memory_content)

    # -- Agent inbox --
    if include_inbox:
        console.print("[dim]  Checking agent-inbox...[/dim]")
        project_name = PROJECT_ROOT.name
        data.inbox_messages = detect_agent_inbox(project_name)

    # -- Git info --
    console.print("[dim]  Detecting git info...[/dim]")
    branch, status, diff_stat, commits = detect_git_info(PROJECT_ROOT)
    data.git_branch = branch
    data.git_status = status
    data.git_diff_stat = diff_stat
    data.recent_commits = commits

    # -- Focus: prefer user-provided, then infer from git --
    data.focus = focus or infer_focus_from_git(PROJECT_ROOT) or "auto-generated"

    # -- Modified files --
    data.files_modified = detect_modified_files(PROJECT_ROOT)

    # Architecture diagram from modified files
    data.architecture_diagram = detect_architecture_diagram(data.files_modified)

    # -- Assessment (code health) --
    if include_assess:
        console.print("[dim]  Running code health assessment...[/dim]")
        data.assessment = detect_assessment(PROJECT_ROOT)

    # -- Running processes --
    if include_processes:
        console.print("[dim]  Detecting running processes...[/dim]")
        data.running_processes = detect_running_processes(PROJECT_ROOT)

    # -- Key code snippets --
    if include_snippets:
        console.print("[dim]  Scanning for key code markers...[/dim]")
        data.key_code_snippets = detect_key_code_snippets(PROJECT_ROOT)

    # -- Test coverage --
    if include_tests:
        console.print("[dim]  Running test detection...[/dim]")
        data.test_coverage = detect_test_coverage(PROJECT_ROOT)

    # -- Dependency graph --
    if include_deps:
        console.print("[dim]  Building dependency graph...[/dim]")
        data.dependency_graph = detect_dependency_graph(PROJECT_ROOT)

    # -- Error log summary --
    if include_errors:
        console.print("[dim]  Scanning error logs...[/dim]")
        data.error_log_summary = detect_error_log_summary(PROJECT_ROOT)

    # -- Environment snapshot --
    if include_env:
        console.print("[dim]  Capturing environment...[/dim]")
        data.environment_snapshot = detect_environment_snapshot()

    # -- Session transcript --
    if include_transcript:
        console.print("[dim]  Finding session transcript...[/dim]")
        data.session_transcript_path = detect_session_transcript()

    # -- Existing context merge --
    existing = detect_existing_context(output)
    if existing:
        console.print(f"[dim]  Found existing CONTEXT.md ({len(existing)} sections) — preserving content[/dim]")

    # -- Interactive or auto mode --
    if interactive:
        data = interactive_gather(data)
    else:
        # Smart auto-generation using all gathered knowledge
        state_parts = []

        if data.files_modified:
            state_parts.append(f"{len(data.files_modified)} files modified in working tree.")

        if data.running_processes:
            state_parts.append(f"\n**Running processes**: {len(data.running_processes)} project-related processes detected.")

        if data.inbox_messages:
            state_parts.append(f"\n**Agent inbox**: {len(data.inbox_messages)} pending messages.")

        # Preserve existing manually-written sections if available
        if existing.get("Current State") and not state_parts:
            data.current_state = existing["Current State"]
        elif state_parts:
            data.current_state = "\n".join(state_parts)

        # Preserve existing hand-written sections
        for section_key, attr in [
            ("Decisions Made", "decisions_made"),
            ("Lessons Learned", "lessons_learned"),
            ("Known Issues / Gaps", "known_issues"),
            ("Open Questions", "open_questions"),
            ("How to Continue", "how_to_continue"),
        ]:
            existing_content = existing.get(section_key, "")
            current_val = getattr(data, attr)
            if existing_content and not current_val:
                # Preserve existing content as-is for string fields
                if isinstance(current_val, list):
                    # Parse bullet points back into list
                    items = [l.lstrip("- [ ] ").lstrip("- ").strip()
                             for l in existing_content.split("\n")
                             if l.strip() and l.strip().startswith(("-", "1", "2", "3"))]
                    setattr(data, attr, items)
                else:
                    setattr(data, attr, existing_content)

    # Generate markdown
    content = generate_markdown(data, include_git=include_git)

    # Ensure output directory exists
    output.parent.mkdir(parents=True, exist_ok=True)

    # Write file
    output.write_text(content)

    console.print(f"\n[green]CONTEXT.md generated: {output}[/green]")
    console.print(f"[dim]Size: {len(content)} bytes, {len(content.splitlines())} lines[/dim]")

    # Post-hook: Learn context to memory with taxonomy tags
    try:
        from memory_integration import learn_context
        memory_ids = learn_context(
            project_name=data.title or PROJECT_ROOT.name,
            focus=data.focus,
            git_branch=data.git_branch,
            decisions=data.decisions_made,
            lessons=data.lessons_learned,
            known_issues=data.known_issues,
            next_steps=data.next_steps_immediate + data.next_steps_nearterm,
            files_modified=data.files_modified,
            context_path=str(output),
        )
        if memory_ids:
            console.print(f"[dim]Learned {len(memory_ids)} entries to memory[/dim]")
    except ImportError:
        pass  # memory_integration optional
    except Exception as e:
        console.print(f"[dim]Memory learn skipped: {e}[/dim]")

    # Summary of what was included
    included = []
    if data.project_purpose:
        included.append("CLAUDE.md")
    if data.memory_content:
        included.append("MEMORY.md")
    if data.inbox_messages:
        included.append(f"{len(data.inbox_messages)} inbox msgs")
    if data.companion_repos:
        included.append(f"{len(data.companion_repos)} companion repos")
    if data.running_processes:
        included.append(f"{len(data.running_processes)} processes")
    if data.assessment:
        included.append(f"{len(data.assessment)} health issues")
    if data.architecture_diagram:
        included.append("architecture")
    if data.key_code_snippets:
        included.append(f"{len(data.key_code_snippets)} snippets")
    if data.test_coverage:
        included.append("tests")
    if data.dependency_graph:
        included.append(f"{len(data.dependency_graph)} deps")
    if data.error_log_summary:
        included.append(f"{len(data.error_log_summary)} errors")
    if data.environment_snapshot:
        included.append(f"{len(data.environment_snapshot)} env vars")
    if data.session_transcript_path:
        included.append("transcript")
    if existing:
        included.append(f"merged {len(existing)} existing sections")

    if included:
        console.print(f"[dim]Included: {', '.join(included)}[/dim]")


@app.command()
def validate(
    path: Path = typer.Argument(DEFAULT_OUTPUT, help="CONTEXT.md to validate"),
):
    """Validate CONTEXT.md completeness."""

    if not path.exists():
        console.print(f"[red]File not found: {path}[/red]")
        raise typer.Exit(1)

    content = path.read_text()

    # Required sections
    required = [
        "## Current State",
        "## Next Steps",
        "## How to Continue",
    ]

    # Recommended sections
    recommended = [
        "## Decisions Made",
        "## Lessons Learned",
        "## Known Issues",
    ]

    # Check required
    missing_required = [s for s in required if s not in content]
    missing_recommended = [s for s in recommended if s not in content]

    # Check for placeholder text
    placeholders = ["TODO", "FIXME", "XXX", "[placeholder]", "[fill in]"]
    found_placeholders = [p for p in placeholders if p.lower() in content.lower()]

    # Report
    console.print(Panel(f"[bold]Validating: {path}[/bold]", style="blue"))

    if missing_required:
        console.print("[red]Missing required sections:[/red]")
        for s in missing_required:
            console.print(f"  - {s}")
    else:
        console.print("[green]All required sections present[/green]")

    if missing_recommended:
        console.print("[yellow]Missing recommended sections:[/yellow]")
        for s in missing_recommended:
            console.print(f"  - {s}")

    if found_placeholders:
        console.print("[yellow]Found placeholder text:[/yellow]")
        for p in found_placeholders:
            console.print(f"  - {p}")

    # Exit code
    if missing_required:
        raise typer.Exit(1)


@app.command()
def diff(
    path: Path = typer.Argument(DEFAULT_OUTPUT, help="CONTEXT.md to compare"),
):
    """Show changes since last CONTEXT.md was written."""

    if not path.exists():
        console.print(f"[yellow]No existing CONTEXT.md at {path}[/yellow]")
        console.print("Run `generate` to create one.")
        raise typer.Exit(0)

    # Get files modified since CONTEXT.md was written
    mtime = datetime.fromtimestamp(path.stat().st_mtime)
    console.print(f"CONTEXT.md last modified: {mtime}")

    # Show git changes since that time
    since = mtime.strftime("%Y-%m-%d %H:%M:%S")
    changes = run_command(["git", "log", f"--since={since}", "--oneline"])

    if changes:
        console.print("\n[bold]Commits since last CONTEXT.md:[/bold]")
        console.print(changes)
    else:
        console.print("[dim]No commits since last CONTEXT.md[/dim]")

    # Show current uncommitted changes
    status = run_command(["git", "status", "--short"])
    if status:
        console.print("\n[bold]Current uncommitted changes:[/bold]")
        console.print(status)


@app.command()
def recall(
    project_name: str = typer.Argument(..., help="Project name to recall prior contexts for"),
    k: int = typer.Option(3, "-k", help="Number of results"),
):
    """Recall prior context snapshots from memory."""
    try:
        from memory_integration import recall_prior_contexts
        context = recall_prior_contexts(project_name, k=k)
        if context:
            console.print(context)
        else:
            console.print(f"[dim]No prior contexts found for '{project_name}'[/dim]")
    except ImportError:
        console.print("[red]memory_integration not available[/red]")
        raise typer.Exit(1)


if __name__ == "__main__":
    app()
