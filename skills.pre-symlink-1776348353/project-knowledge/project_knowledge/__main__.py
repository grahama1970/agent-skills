"""CLI entry point for project-knowledge skill."""
from __future__ import annotations

import json
import os
import re
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Optional

import httpx
import typer
from rich.console import Console
from rich.markdown import Markdown

app = typer.Typer(help="Shared project knowledge document for human and agent collaboration.")
console = Console()

KNOWLEDGE_FILE = "PROJECT_KNOWLEDGE.md"
SKILLS_DIR = Path.home() / ".claude" / "skills"
MEMORY_SOCKET = "/run/user/1000/embry/memory.sock"


def get_working_dir() -> Path:
    """Get the caller's working directory (not the skill dir)."""
    cwd = os.environ.get("PROJECT_KNOWLEDGE_CWD")
    if cwd:
        return Path(cwd)
    return Path.cwd()


def get_project_name() -> str:
    """Get project name from git or directory."""
    cwd = get_working_dir()
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            check=True,
            cwd=str(cwd),
        )
        return Path(result.stdout.strip()).name
    except subprocess.CalledProcessError:
        return cwd.name


def get_knowledge_path() -> Path:
    """Get path to PROJECT_KNOWLEDGE.md in caller's directory."""
    return get_working_dir() / KNOWLEDGE_FILE


def parse_sections(content: str) -> dict[str, str]:
    """Parse markdown into sections by ## headers."""
    sections = {}
    current_section = "header"
    current_content = []

    for line in content.split("\n"):
        if line.startswith("## "):
            if current_content:
                sections[current_section] = "\n".join(current_content).strip()
            current_section = line[3:].strip()
            current_content = []
        else:
            current_content.append(line)

    if current_content:
        sections[current_section] = "\n".join(current_content).strip()

    return sections


def render_sections(sections: dict[str, str]) -> str:
    """Render sections back to markdown."""
    lines = []

    # Header first (no ## prefix)
    if "header" in sections:
        lines.append(sections["header"])
        lines.append("")

    # Then all other sections
    for name, content in sections.items():
        if name != "header":
            lines.append(f"## {name}")
            lines.append("")
            lines.append(content)
            lines.append("")

    return "\n".join(lines)


def call_memory_recall(query: str, k: int = 5, scope: str = "") -> list[dict]:
    """Call /memory recall via Unix socket."""
    try:
        transport = httpx.HTTPTransport(uds=MEMORY_SOCKET)
        with httpx.Client(transport=transport, base_url="http://localhost", timeout=10.0) as client:
            payload = {"q": query, "k": k}
            if scope:
                payload["scope"] = scope
            resp = client.post("/recall", json=payload)
            if resp.status_code == 200:
                data = resp.json()
                return data.get("items", [])
    except Exception as e:
        console.print(f"[yellow]Memory recall failed: {e}[/yellow]")
    return []


def call_memory_learn(problem: str, solution: str, tags: list[str], scope: str = "") -> bool:
    """Call /memory learn via Unix socket (to lessons collection)."""
    try:
        transport = httpx.HTTPTransport(uds=MEMORY_SOCKET)
        with httpx.Client(transport=transport, base_url="http://localhost", timeout=10.0) as client:
            doc = {
                "problem": problem,
                "solution": solution,
                "tags": tags,
            }
            if scope:
                doc["scope"] = scope
            resp = client.post("/store", json={"document": doc})
            return resp.status_code == 200
    except Exception as e:
        console.print(f"[yellow]Memory learn failed: {e}[/yellow]")
    return False


def call_memory_store(doc: dict, collection: str = "project_knowledge") -> bool:
    """Store document to specific /memory collection."""
    try:
        transport = httpx.HTTPTransport(uds=MEMORY_SOCKET)
        with httpx.Client(transport=transport, base_url="http://localhost", timeout=10.0) as client:
            resp = client.post("/store", json={"document": doc, "collection": collection})
            return resp.status_code == 200
    except Exception as e:
        console.print(f"[yellow]Memory store failed: {e}[/yellow]")
    return False


def get_recent_commits(n: int = 10) -> list[str]:
    """Get recent git commits."""
    try:
        result = subprocess.run(
            ["git", "log", f"--oneline", f"-{n}"],
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip().split("\n")
    except subprocess.CalledProcessError:
        return []


def run_project_state_quick() -> str:
    """Run /project-state --quick and return output."""
    project_state_script = SKILLS_DIR / "project-state" / "run.sh"
    if not project_state_script.exists():
        return "(project-state skill not available)"

    try:
        result = subprocess.run(
            [str(project_state_script), "report", "--quick"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        return result.stdout
    except Exception as e:
        return f"(project-state failed: {e})"


@app.command()
def init(
    force: bool = typer.Option(False, "--force", "-f", help="Overwrite existing file"),
):
    """Initialize PROJECT_KNOWLEDGE.md in current directory."""
    path = get_knowledge_path()

    if path.exists() and not force:
        console.print(f"[yellow]{KNOWLEDGE_FILE} already exists. Use --force to overwrite.[/yellow]")
        raise typer.Exit(1)

    project_name = get_project_name()
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    template = f"""# Project Knowledge: {project_name}

**Last updated:** {now} by agent
**Status:** Active development

## Current Understanding

- Project initialized, knowledge tracking started

## Recent Decisions

| Date | Decision | Why |
|------|----------|-----|
| {datetime.now().strftime("%Y-%m-%d")} | Initialize project knowledge | Enable shared human/agent context |

## Open Questions

- [ ] What are the key architectural decisions?
- [ ] What are the known issues?

## Key Files

| File | Purpose |
|------|---------|
| PROJECT_KNOWLEDGE.md | Shared project knowledge |

## Infrastructure State

<!-- Auto-populated from /project-state --quick -->
"""

    path.write_text(template)
    console.print(f"[green]Created {KNOWLEDGE_FILE}[/green]")


@app.command()
def read(
    refresh: bool = typer.Option(False, "--refresh", "-r", help="Refresh from live sources"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Read current project knowledge."""
    path = get_knowledge_path()

    if not path.exists():
        console.print(f"[yellow]{KNOWLEDGE_FILE} not found. Run 'init' first.[/yellow]")
        raise typer.Exit(1)

    content = path.read_text()

    if refresh:
        sections = parse_sections(content)

        # Refresh Infrastructure State from /project-state
        infra = run_project_state_quick()
        sections["Infrastructure State"] = f"```\n{infra}\n```"

        # Update timestamp
        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        if "header" in sections:
            sections["header"] = re.sub(
                r"\*\*Last updated:\*\* .+",
                f"**Last updated:** {now} by agent (refreshed)",
                sections["header"],
            )

        content = render_sections(sections)
        path.write_text(content)

    if json_output:
        sections = parse_sections(content)
        print(json.dumps(sections, indent=2))
    else:
        console.print(Markdown(content))


@app.command()
def update(
    section: str = typer.Argument(..., help="Section name to update"),
    content: str = typer.Argument(..., help="Content to add"),
    append: bool = typer.Option(True, "--append/--replace", help="Append or replace"),
):
    """Update a specific section."""
    path = get_knowledge_path()

    if not path.exists():
        console.print(f"[yellow]{KNOWLEDGE_FILE} not found. Run 'init' first.[/yellow]")
        raise typer.Exit(1)

    file_content = path.read_text()
    sections = parse_sections(file_content)

    if section not in sections:
        sections[section] = ""

    if append:
        sections[section] = sections[section] + "\n- " + content
    else:
        sections[section] = content

    # Update timestamp
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    if "header" in sections:
        sections["header"] = re.sub(
            r"\*\*Last updated:\*\* .+",
            f"**Last updated:** {now} by agent",
            sections["header"],
        )

    path.write_text(render_sections(sections))
    console.print(f"[green]Updated section '{section}'[/green]")


@app.command()
def decide(
    decision: str = typer.Argument(..., help="What was decided"),
    why: str = typer.Argument(..., help="Why it was decided"),
):
    """Add a decision to Recent Decisions table."""
    path = get_knowledge_path()

    if not path.exists():
        console.print(f"[yellow]{KNOWLEDGE_FILE} not found. Run 'init' first.[/yellow]")
        raise typer.Exit(1)

    file_content = path.read_text()
    sections = parse_sections(file_content)

    date = datetime.now().strftime("%Y-%m-%d")
    new_row = f"| {date} | {decision} | {why} |"

    if "Recent Decisions" in sections:
        sections["Recent Decisions"] = sections["Recent Decisions"] + "\n" + new_row
    else:
        sections["Recent Decisions"] = f"| Date | Decision | Why |\n|------|----------|-----|\n{new_row}"

    # Update timestamp
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    if "header" in sections:
        sections["header"] = re.sub(
            r"\*\*Last updated:\*\* .+",
            f"**Last updated:** {now} by agent",
            sections["header"],
        )

    path.write_text(render_sections(sections))
    console.print(f"[green]Added decision: {decision}[/green]")


@app.command()
def question(
    q: str = typer.Argument(..., help="Question to add"),
):
    """Add an open question."""
    path = get_knowledge_path()

    if not path.exists():
        console.print(f"[yellow]{KNOWLEDGE_FILE} not found. Run 'init' first.[/yellow]")
        raise typer.Exit(1)

    file_content = path.read_text()
    sections = parse_sections(file_content)

    new_question = f"- [ ] {q}"

    if "Open Questions" in sections:
        sections["Open Questions"] = sections["Open Questions"] + "\n" + new_question
    else:
        sections["Open Questions"] = new_question

    # Update timestamp
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    if "header" in sections:
        sections["header"] = re.sub(
            r"\*\*Last updated:\*\* .+",
            f"**Last updated:** {now} by agent",
            sections["header"],
        )

    path.write_text(render_sections(sections))
    console.print(f"[green]Added question: {q}[/green]")


@app.command()
def sync():
    """Sync PROJECT_KNOWLEDGE.md to /memory project_knowledge collection."""
    path = get_knowledge_path()

    if not path.exists():
        console.print(f"[yellow]{KNOWLEDGE_FILE} not found. Run 'init' first.[/yellow]")
        raise typer.Exit(1)

    project_name = get_project_name()
    file_content = path.read_text()
    sections = parse_sections(file_content)
    now = datetime.now().isoformat()

    # Build document with deterministic _key for upsert
    import hashlib
    doc_key = hashlib.sha256(f"project_knowledge:{project_name}".encode()).hexdigest()[:16]

    doc = {
        "_key": doc_key,
        "project": project_name,
        "scope": project_name,  # For /recall --scope filtering
        "sections": sections,
        "understanding": sections.get("Current Understanding", ""),
        "decisions": sections.get("Recent Decisions", ""),
        "key_files": sections.get("Key Files", ""),
        "open_questions": sections.get("Open Questions", ""),
        "updated_at": now,
        "tags": ["project_knowledge", f"project:{project_name}"],
    }

    success = call_memory_store(doc, collection="project_knowledge")

    if success:
        console.print(f"[green]Synced PROJECT_KNOWLEDGE.md to /memory[/green]")
        console.print(f"  Project: {project_name}")
        console.print(f"  Key: {doc_key}")
        console.print(f"  Sections: {len(sections)}")
    else:
        console.print(f"[red]Failed to sync to /memory[/red]")


@app.command(name="diff")
def diff_cmd():
    """Check drift between file and actual state."""
    path = get_knowledge_path()

    if not path.exists():
        console.print(f"[yellow]{KNOWLEDGE_FILE} not found. Run 'init' first.[/yellow]")
        raise typer.Exit(1)

    console.print("[bold]Checking drift...[/bold]\n")

    # Check last update time
    file_content = path.read_text()
    match = re.search(r"\*\*Last updated:\*\* (\d{4}-\d{2}-\d{2} \d{2}:\d{2})", file_content)
    if match:
        last_update = match.group(1)
        console.print(f"Last updated: {last_update}")

    # Check recent commits since last update
    commits = get_recent_commits(5)
    if commits:
        console.print("\nRecent commits (may indicate drift):")
        for commit in commits:
            console.print(f"  {commit}")

    # Run project-state and compare
    console.print("\n[bold]Live infrastructure state:[/bold]")
    infra = run_project_state_quick()
    console.print(infra[:500] + "..." if len(infra) > 500 else infra)

    console.print("\n[yellow]Review above and update PROJECT_KNOWLEDGE.md if needed.[/yellow]")


@app.command()
def recall(
    project: Optional[str] = typer.Option(None, "--project", "-p", help="Project name (default: current)"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Recall project knowledge from /memory by project scope."""
    target_project = project or get_project_name()

    try:
        transport = httpx.HTTPTransport(uds=MEMORY_SOCKET)
        with httpx.Client(transport=transport, base_url="http://localhost", timeout=10.0) as client:
            # Query project_knowledge collection with scope filter
            resp = client.post("/list", json={
                "collection": "project_knowledge",
                "limit": 1,
                "filters": {"scope": target_project},
            })
            if resp.status_code == 200:
                data = resp.json()
                docs = data.get("documents", [])
                if docs:
                    doc = docs[0]
                    if json_output:
                        print(json.dumps(doc, indent=2))
                    else:
                        console.print(f"[bold]Project: {doc.get('project')}[/bold]")
                        console.print(f"Updated: {doc.get('updated_at', 'unknown')}\n")

                        if doc.get("understanding"):
                            console.print("[bold]Current Understanding:[/bold]")
                            console.print(doc["understanding"])
                            console.print()

                        if doc.get("decisions"):
                            console.print("[bold]Recent Decisions:[/bold]")
                            console.print(doc["decisions"])
                            console.print()

                        if doc.get("open_questions"):
                            console.print("[bold]Open Questions:[/bold]")
                            console.print(doc["open_questions"])
                else:
                    console.print(f"[yellow]No project knowledge found for '{target_project}'[/yellow]")
                    console.print("Run 'sync' to push local PROJECT_KNOWLEDGE.md to /memory")
            else:
                console.print(f"[red]Memory query failed: {resp.status_code}[/red]")
    except Exception as e:
        console.print(f"[red]Memory recall failed: {e}[/red]")


@app.command(name="update-from-checkpoint")
def update_from_checkpoint():
    """Update knowledge after a checkpoint (hook integration)."""
    path = get_knowledge_path()

    if not path.exists():
        # Silently exit if no knowledge file - this is a hook
        return

    # Get last commit message
    try:
        result = subprocess.run(
            ["git", "log", "-1", "--format=%s"],
            capture_output=True,
            text=True,
            check=True,
        )
        commit_msg = result.stdout.strip()
    except subprocess.CalledProcessError:
        return

    # Update Current Understanding with checkpoint note
    file_content = path.read_text()
    sections = parse_sections(file_content)

    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    checkpoint_note = f"[{now}] Checkpoint: {commit_msg}"

    if "Current Understanding" in sections:
        sections["Current Understanding"] = sections["Current Understanding"] + "\n- " + checkpoint_note

    # Update timestamp
    if "header" in sections:
        sections["header"] = re.sub(
            r"\*\*Last updated:\*\* .+",
            f"**Last updated:** {now} by agent (checkpoint)",
            sections["header"],
        )

    path.write_text(render_sections(sections))


if __name__ == "__main__":
    app()
