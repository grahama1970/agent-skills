"""
Additional CLI commands for the hack skill.

This module contains secondary commands that integrate with other skills:
- learn: Fetch exploit/book resources
- research: Leverage research skills
- process: Store content in memory
- prove: Formal verification
- exploit: Run exploits in containers
- harden: Red-team codebases
"""
from __future__ import annotations

import os
import subprocess
from typing import Callable

import typer
from rich.console import Console

from hack.config import (
    SKILL_MAP,
    ANVIL_SKILL,
    DOCKER_OPS_SKILL,
    TREESITTER_SKILL,
    TAXONOMY_SKILL,
)
from hack.container_manager import (
    setup_exploit_environment,
    run_exploit,
    cleanup_exploit_environment,
)
from hack.utils import (
    memory_recall,
    memory_store,
    show_memory_context,
)

console = Console()


def create_learn_command() -> Callable[..., None]:
    """Create the learn command."""

    def learn(
        source: str = typer.Option(
            None, help="Source to fetch exploits from (exploit-db, packetstorm, github)"
        ),
        type: str = typer.Option(
            "exploit", help="Type of learning material (exploit, book)"
        ),
        query: str = typer.Option(None, help="Query for specific topic (e.g. for books)"),
        watch_dir: str = typer.Option(
            None,
            help="Directory for Readarr to watch",
        ),
    ):
        """Fetch and update local knowledge base (exploits or books)."""
        if type == "book":
            if not query:
                console.print("[red]Error: --query required for book learning[/red]")
                return

            console.print("[bold blue]Learning from Books (Readarr-Ops)...[/bold blue]")
            skill_script = os.path.join(
                os.path.dirname(__file__), "..", "readarr-ops", "run.sh"
            )
            if not os.path.exists(skill_script):
                skill_script = os.path.expanduser(
                    "~/workspace/experiments/pi-mono/.agent/skills/readarr-ops/run.sh"
                )
            if not os.path.exists(skill_script):
                console.print(f"[red]readarr-ops skill not found[/red]")
                return

            cmd = [skill_script, "add", query]
            console.print(f"Executing: {' '.join(cmd)}")
            subprocess.run(cmd)
            return

        if source:
            console.print(f"[bold blue]Learning from Source: {source}[/bold blue]")
            data_dir = os.path.expanduser("~/.pi/skills/hack/data")
            os.makedirs(data_dir, exist_ok=True)

            if source == "exploit-db":
                _fetch_exploit_db(data_dir)
            elif source == "github":
                if not query:
                    console.print("[red]Error: --query required for GitHub[/red]")
                    return
                _fetch_github_exploit(query, data_dir)
            else:
                console.print(f"[red]Unknown source: {source}[/red]")
        else:
            console.print(
                "[yellow]Please specify --source for exploits or --type book[/yellow]"
            )

    return learn


def _fetch_exploit_db(data_dir: str) -> None:
    """Fetch Exploit-DB CSV database."""
    console.print("Fetching latest CSV from Exploit-DB...")
    csv_url = "https://gitlab.com/exploit-database/exploitdb/-/raw/main/files_exploits.csv"
    try:
        import requests

        resp = requests.get(csv_url, timeout=30)
        if resp.status_code == 200:
            target_file = os.path.join(data_dir, "exploitdb.csv")
            with open(target_file, "wb") as f:
                f.write(resp.content)
            console.print(f"[green]Downloaded to {target_file}[/green]")
            count = len(resp.text.splitlines())
            console.print(f"[dim]Indexed {count} exploits.[/dim]")
        else:
            console.print(f"[red]Failed: HTTP {resp.status_code}[/red]")
    except Exception as e:
        console.print(f"[red]Download error: {e}[/red]")


def _fetch_github_exploit(query: str, data_dir: str) -> None:
    """Search and clone exploit from GitHub."""
    console.print(f"Searching GitHub for: {query}...")
    try:
        import requests

        api_url = "https://api.github.com/search/repositories"
        params = {"q": f"{query} topic:exploit", "sort": "updated", "order": "desc"}
        resp = requests.get(
            api_url,
            params=params,
            headers={"Accept": "application/vnd.github.v3+json"},
            timeout=10,
        )
        if resp.status_code == 200:
            results = resp.json().get("items", [])
            if not results:
                console.print("[yellow]No repositories found.[/yellow]")
                return
            repo = results[0]
            clone_url = repo["clone_url"]
            repo_name = repo["name"]
            console.print(f"[green]Found: {repo['full_name']}[/green]")
            target_path = os.path.join(data_dir, "repos", repo_name)
            if os.path.exists(target_path):
                subprocess.run(["git", "-C", target_path, "pull"], check=False)
            else:
                subprocess.run(["git", "clone", clone_url, target_path], check=True)
            console.print(f"[bold]Tip:[/bold] hack process {target_path}")
        else:
            console.print(f"[red]GitHub API Error: {resp.status_code}[/red]")
    except Exception as e:
        console.print(f"[red]GitHub Error: {e}[/red]")


def create_research_command() -> Callable[..., None]:
    """Create the research command."""

    def research(
        topic: str = typer.Argument(..., help="Research topic"),
        skill: str = typer.Option("dogpile", help="Skill to use"),
    ):
        """Leverage other agent skills for deep research."""
        console.print(f"[bold purple]Researching '{topic}' using {skill}...[/bold purple]")
        if skill not in SKILL_MAP:
            console.print(f"[red]Unknown skill: {skill}[/red]")
            return
        skill_script = os.path.join(os.path.dirname(__file__), "..", SKILL_MAP[skill])
        if not os.path.exists(skill_script):
            skill_script = os.path.join(os.path.dirname(__file__), "..", skill, "run.sh")
        if not os.path.exists(skill_script):
            console.print(f"[red]Skill not found[/red]")
            return
        if skill == "dogpile":
            cmd = [skill_script, "search", topic]
        elif skill == "arxiv":
            cmd = [skill_script, "search", "--query", topic]
        else:
            cmd = [skill_script, "run", topic]
        subprocess.run(cmd)

    return research


def create_process_command() -> Callable[..., None]:
    """Create the process command."""

    def process(
        target: str = typer.Argument(..., help="File path, URL, or content"),
        scope: str = typer.Option("hack_skill", help="Memory scope"),
        context: str = typer.Option(None, help="Context for extraction"),
    ):
        """Process content into memory using the 'learn' skill."""
        console.print(f"[bold green]Processing:[/bold green] {target}")
        skill_script = os.path.join(
            os.path.dirname(__file__), "..", "..", "..", ".agent", "skills", "learn", "run.sh"
        )
        if not os.path.exists(skill_script):
            skill_script = os.path.expanduser(
                "~/workspace/experiments/pi-mono/.agent/skills/learn/run.sh"
            )
        if not os.path.exists(skill_script):
            console.print(f"[red]Learn skill not found[/red]")
            return
        cmd = [skill_script, target, "--scope", scope]
        if context:
            cmd.extend(["--context", context])
        subprocess.run(cmd)

    return process


def create_prove_command() -> Callable[..., None]:
    """Create the prove command."""

    def prove(
        claim: str = typer.Option(..., help="Security claim to prove/refute"),
        negate: bool = typer.Option(False, help="Negate claim (Red Team mode)"),
        persona: str = typer.Option("security researcher", help="Persona context"),
    ):
        """Formally verify security properties using Lean4."""
        requirement = claim
        if negate:
            console.print("[bold red]Negating claim...[/bold red]")
            requirement = f"Refute that {claim}"
        console.print(f"[bold blue]Proving:[/bold blue] {requirement}")
        skill_script = os.path.join(
            os.path.dirname(__file__), "..", "..", "..", ".agent", "skills", "lean4-prove", "run.sh"
        )
        if not os.path.exists(skill_script):
            skill_script = os.path.expanduser(
                "~/workspace/experiments/pi-mono/.agent/skills/lean4-prove/run.sh"
            )
        if not os.path.exists(skill_script):
            console.print(f"[red]Lean4-Prove skill not found[/red]")
            return
        cmd = [skill_script, "--requirement", requirement, "--persona", persona]
        subprocess.run(cmd)

    return prove


def create_exploit_command() -> Callable[..., None]:
    """Create the exploit command."""

    def exploit(
        target: str = typer.Option(..., help="Target IP/Hostname"),
        env: str = typer.Option("python", help="Environment type"),
        payload: str = typer.Option(None, help="Path to exploit script"),
        interactive: bool = typer.Option(False, help="Run interactively"),
    ):
        """Run an exploit in an isolated Docker container."""
        console.print(f"[bold red]Preparing Environment ({env})...[/bold red]")
        work_dir, error = setup_exploit_environment(target, env, payload, interactive)
        if error:
            console.print(f"[red]{error}[/red]")
            return
        console.print(f"[green]Environment ready in {work_dir}[/green]")
        try:
            run_exploit(work_dir, interactive)
        except Exception as e:
            console.print(f"[bold red]Error:[/bold red] {e}")
        finally:
            cleanup_exploit_environment(work_dir)

    return exploit


def create_harden_command() -> Callable[..., None]:
    """Create the harden command."""

    def harden(
        target: str = typer.Argument(".", help="Directory to harden"),
        issue: str = typer.Option(None, help="Specific issue to focus on"),
        mode: str = typer.Option("harden", help="Mode: harden or debug"),
    ):
        """Red-team/harden a codebase using anvil's Thunderdome."""
        console.print(f"[bold red]Running Anvil on:[/bold red] {target}")
        show_memory_context("security hardening techniques")
        anvil_script = ANVIL_SKILL / "run.sh"
        if not anvil_script.exists():
            console.print("[red]Anvil skill not found[/red]")
            return
        cmd = [str(anvil_script), mode, "run"]
        if issue:
            cmd.extend(["--issue", issue])
        subprocess.run(cmd, cwd=target)

    return harden


def create_docker_cleanup_command() -> Callable[..., None]:
    """Create the docker-cleanup command."""

    def docker_cleanup(
        until: str = typer.Option("24h", help="Prune resources older than this"),
        execute: bool = typer.Option(False, help="Actually prune"),
    ):
        """Clean up Docker resources using docker-ops skill."""
        console.print("[bold blue]Docker cleanup[/bold blue]")
        docker_ops_script = DOCKER_OPS_SKILL / "run.sh"
        if not docker_ops_script.exists():
            console.print("[red]docker-ops skill not found[/red]")
            return
        cmd = [str(docker_ops_script), "prune", "--until", until]
        if execute:
            cmd.append("--execute")
        else:
            console.print("[dim](Dry run - add --execute to prune)[/dim]")
        subprocess.run(cmd)

    return docker_cleanup


def create_symbols_command() -> Callable[..., None]:
    """Create the symbols command."""

    def symbols(
        target: str = typer.Argument(..., help="File to extract symbols from"),
        content: bool = typer.Option(False, "-c", help="Include full source"),
    ):
        """Extract code symbols using treesitter skill."""
        console.print(f"[bold cyan]Extracting symbols from:[/bold cyan] {target}")
        treesitter_script = TREESITTER_SKILL / "run.sh"
        if not treesitter_script.exists():
            console.print("[red]treesitter skill not found[/red]")
            return
        cmd = [str(treesitter_script), "symbols", target]
        if content:
            cmd.append("--content")
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode == 0:
            console.print(result.stdout)
        else:
            console.print(f"[red]Error: {result.stderr}[/red]")

    return symbols


def create_classify_command() -> Callable[..., None]:
    """Create the classify command."""

    def classify(
        text: str = typer.Argument(..., help="Security finding to classify"),
        collection: str = typer.Option("sparta", help="Taxonomy collection"),
    ):
        """Classify security findings using taxonomy skill."""
        console.print("[bold purple]Classifying...[/bold purple]")
        taxonomy_script = TAXONOMY_SKILL / "run.sh"
        if not taxonomy_script.exists():
            console.print("[red]taxonomy skill not found[/red]")
            return
        result = subprocess.run(
            [str(taxonomy_script), "--text", text, "--collection", collection, "--json"],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            try:
                import json
                data = json.loads(result.stdout)
                console.print(f"[green]Bridge Tags:[/green] {data.get('bridge_tags', [])}")
            except Exception:
                console.print(result.stdout)
        else:
            console.print(f"[red]Error: {result.stderr}[/red]")

    return classify


def create_remember_command() -> Callable[..., None]:
    """Create the remember command."""

    def remember(
        content: str = typer.Argument(..., help="Knowledge to store"),
        title: str = typer.Option(None, help="Title for the knowledge"),
        tags: str = typer.Option("security", help="Comma-separated tags"),
    ):
        """Store security knowledge in memory."""
        console.print("[bold blue]Storing in memory...[/bold blue]")
        formatted = f"[{title or 'Security Note'}] {content}"
        if tags:
            formatted += f" (tags: {tags})"
        if memory_store(formatted, scope="hack_skill", context="security"):
            console.print("[green]Stored successfully.[/green]")
        else:
            console.print("[yellow]Memory skill not available.[/yellow]")

    return remember


def create_recall_command() -> Callable[..., None]:
    """Create the recall command."""

    def recall(
        query: str = typer.Argument(..., help="Query to search"),
        k: int = typer.Option(5, help="Number of results"),
    ):
        """Recall security knowledge from memory."""
        console.print(f"[bold blue]Searching memory:[/bold blue] {query}")
        result = memory_recall(query, scope="hack_skill", k=k)
        if result is None:
            console.print("[yellow]Memory skill not available.[/yellow]")
            return
        if result.get("found"):
            console.print("[green]Found knowledge:[/green]")
            if "answer" in result:
                console.print(result["answer"])
        elif "raw" in result:
            console.print(result["raw"])
        else:
            console.print("[yellow]No relevant knowledge found.[/yellow]")

    return recall

# Explicit module exports for clarity
__all__ = [
    "create_learn_command",
    "create_research_command",
    "create_process_command",
    "create_prove_command",
    "create_exploit_command",
    "create_harden_command",
    "create_docker_cleanup_command",
    "create_symbols_command",
    "create_classify_command",
    "create_remember_command",
    "create_recall_command",
]
