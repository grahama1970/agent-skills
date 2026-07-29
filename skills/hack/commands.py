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
import json
import subprocess
import tempfile
from pathlib import Path
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
            subprocess.run(cmd,
                env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
            )
            return

        if source:
            console.print(f"[bold blue]Learning from Source: {source}[/bold blue]")
            data_dir = str(Path(__file__).resolve().parent / "data")
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
        import httpx

        resp = httpx.get(csv_url, timeout=30)
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
        import httpx

        api_url = "https://api.github.com/search/repositories"
        params = {"q": f"{query} topic:exploit", "sort": "updated", "order": "desc"}
        resp = httpx.get(
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
                subprocess.run(["git", "-C", target_path, "pull"], check=False,
                env={k: v for k, v in os.environ.items() if k != "VIRTUAL_ENV"},
                )
            else:
                subprocess.run(["git", "clone", clone_url, target_path], check=True,
                    env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
                )
            console.print(f"[bold]Tip:[/bold] hack process {target_path}")
        else:
            console.print(f"[red]GitHub API Error: {resp.status_code}[/red]")
    except Exception as e:
        console.print(f"[red]GitHub Error: {e}[/red]",
        env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
        )


def create_research_command() -> Callable[..., None]:
    """Create the research command."""

    def research(
        topic: str = typer.Argument(..., help="Research topic"),
        skill: str = typer.Option("dogpile", help="Skill to use"),
        model: str = typer.Option("gpt-5.2-codex", help="AI model to use for research"),
        silent: bool = typer.Option(False, "--silent", help="Run non-interactively"),
        output_dir: Path | None = typer.Option(None, "--output-dir", help="Directory for Dogpile packet artifacts."),
    ):
        """Leverage other agent skills for deep research."""
        if not silent:
            console.print(f"[bold purple]Researching '{topic}' using {skill} (model: {model})...[/bold purple]")
        
        if skill not in SKILL_MAP:
            if not silent:
                console.print(f"[red]Unknown skill: {skill}[/red]")
            return
        
        skill_script = Path(SKILL_MAP[skill])
        if not skill_script.exists():
            if not silent:
                console.print(f"[red]Skill not found at: {skill_script}[/red]")
            return
        
        if skill == "dogpile":
            packet_dir = output_dir or Path(tempfile.mkdtemp(prefix="hack-dogpile-research-"))
            packet_out = packet_dir / "dogpile-security-packet.json"
            cmd = [
                str(skill_script),
                "search",
                topic,
                "--no-interactive",
                "--output-dir",
                str(packet_dir),
                "--security-packet-out",
                str(packet_out),
            ]
        elif skill == "arxiv":
            cmd = [str(skill_script), "search", "--query", topic]
        else:
            cmd = [str(skill_script), "run", topic, "--model", model]
            
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            env={k: v for k, v in os.environ.items() if k != "VIRTUAL_ENV"},
        )
        if not silent and result.stdout:
            console.print(result.stdout)
        if result.returncode != 0:
            if not silent:
                console.print(f"[red]Research command failed with exit code {result.returncode}[/red]")
                if result.stderr:
                    console.print(result.stderr[-1200:])
            raise typer.Exit(result.returncode)

        if skill == "dogpile":
            packet_path = packet_out
            hack_request = packet_dir / "hack-scan-request.json"
            if not packet_path.exists() or not hack_request.exists():
                if not silent:
                    console.print("[red]Dogpile did not produce required security packet artifacts[/red]")
                raise typer.Exit(2)
            try:
                packet = json.loads(packet_path.read_text())
            except Exception as exc:
                if not silent:
                    console.print(f"[red]Dogpile security packet is unreadable: {exc}[/red]")
                raise typer.Exit(2)
            if int(packet.get("source_bearing_evidence_count") or 0) < 1:
                if not silent:
                    console.print("[red]Dogpile packet has no source-bearing evidence[/red]")
                raise typer.Exit(2)
            if not silent:
                console.print(
                    "[green]Dogpile source-bearing packet ready:[/green] "
                    f"{packet_path} ({packet.get('source_bearing_evidence_count')} evidence items)"
                )

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
        subprocess.run(cmd,
        env={k: v for k, v in os.environ.items() if k != "VIRTUAL_ENV"},
        )

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
        subprocess.run(cmd,
        env={k: v for k, v in os.environ.items() if k != "VIRTUAL_ENV"},
        )

    return prove


def create_exploit_command() -> Callable[..., None]:
    """Create the exploit command."""

    def exploit(
        target: str = typer.Option(..., help="Target IP/Hostname"),
        env: str = typer.Option("python", help="Environment type"),
        payload: str = typer.Option(None, help="Path to exploit script"),
        interactive: bool = typer.Option(False, help="Run interactively"),
        skip_research: bool = typer.Option(False, "--skip-research", help="Skip research phase"),
        chaos: bool = typer.Option(False, "--chaos", help="Enable Chaos Mode (novel brainstorming)"),
        max_retries: int = typer.Option(3, "--max-retries", help="Max retries for Chaos iteration"),
        model: str = typer.Option("gpt-5.2-codex", help="AI model to use for research and chaos brainstorming"),
    ):
        """Run exploit in isolated container with optional Chaos Mode iteration loop.

        Uses /code-runner via exploit_writer for self-improving exploit generation,
        with chaos brainstorming feeding context into each code-runner round.
        """
        from hack.utils import start_task_session, end_task_session, add_task_accomplishment
        from hack.chaos import brainstorm_chaos_exploits, generate_assembly_payload
        from hack.exploit_writer import write_exploit, ExploitResult

        start_task_session(project=f"exploit-{target}")

        if not skip_research:
            console.print(f"[bold blue]Entering Research Phase for target:[/bold blue] {target}")
            add_task_accomplishment(f"Started research on {target}")
            from hack.commands import create_research_command
            research_fn = create_research_command()
            try:
                research_fn(topic=f"exploit vulnerability research {target}", silent=True)
                add_task_accomplishment("Research phase complete")
            except Exception as e:
                console.print(f"[dim]Research phase issue: {e}[/dim]")

            console.print("[cyan]Research phase complete.[/cyan]")

        # --- Code-runner self-improvement loop ---
        prior_context = ""
        docker_target = target  # container name or IP
        attempt = 1

        while attempt <= max_retries:
            console.print(f"\n[bold yellow]Attempt {attempt}/{max_retries}[/bold yellow]")
            add_task_accomplishment(f"Exploit attempt {attempt} for {target}")

            # Chaos brainstorming feeds context into code-runner
            if chaos and attempt > 1:
                console.print(f"[bold purple]Chaos Mode: Brainstorming novel bypass using {model}...[/bold purple]")
                ideas = brainstorm_chaos_exploits(target, failure_context=prior_context, model=model)
                if ideas:
                    idea = ideas[0]
                    console.print(f"[purple]Chaos Idea: {idea['title']} (Insane Factor: {idea['insane_factor']})[/purple]")
                    prior_context += f"\nChaos idea: {idea['title']}: {idea['description']}"

            # Use exploit_writer (code-runner) to generate + test exploit
            finding_desc = f"Exploit target {target} via {env} environment"
            if payload:
                finding_desc += f"\nExisting payload: {payload}"

            console.print("[bold red]Running exploit_writer (code-runner self-improvement loop)...[/bold red]")
            result: ExploitResult = write_exploit(
                target_path=target,
                finding=finding_desc,
                prior_context=prior_context,
                docker_target=docker_target,
                max_rounds=max_retries,
            )

            if result.success:
                console.print(f"[bold green]Exploit Succeeded! (score={result.score:.3f}, rounds={result.rounds})[/bold green]")
                add_task_accomplishment(f"Exploit succeeded: score={result.score:.3f}")
                break
            else:
                console.print(f"[yellow]Exploit failed (score={result.score:.3f}, rounds={result.rounds})[/yellow]")
                prior_context += f"\nAttempt {attempt} failed: score={result.score:.3f}"
                add_task_accomplishment(f"Attempt {attempt} failed (score={result.score:.3f})")

            if not chaos:
                break
            attempt += 1

        end_task_session(notes=f"Finished exploit run for {target}")

    return exploit


def create_harden_command() -> Callable[..., None]:
    """Create the harden command."""

    def harden(
        target: str = typer.Argument(".", help="Directory to harden"),
        issue: str = typer.Option(None, help="Specific issue to focus on"),
        mode: str = typer.Option("harden", help="Mode: harden or debug"),
    ):
        """Red-team/harden a codebase using anvil with monitor tracking."""
        from hack.utils import start_task_session, end_task_session, add_task_accomplishment
        
        start_task_session(project=f"harden-{Path(target).name}")
        console.print(f"[bold red]Running Anvil on:[/bold red] {target}")
        add_task_accomplishment(f"Started Anvil {mode} on {target}")
        show_memory_context("security hardening techniques")
        
        anvil_script = ANVIL_SKILL / "run.sh"
        if not anvil_script.exists():
            console.print("[red]Anvil skill not found[/red]")
            end_task_session(notes="Anvil skill not found")
            return
            
        cmd = [str(anvil_script), mode, "run"]
        if issue:
            cmd.extend(["--issue", issue])
            add_task_accomplishment(f"Focusing on issue: {issue}")
            
        try:
            subprocess.run(cmd, cwd=target,
            env={k: v for k, v in os.environ.items() if k != "VIRTUAL_ENV"},
            )
            add_task_accomplishment(f"Anvil {mode} complete")
        except Exception as e:
            console.print(f"[red]Anvil failed: {e}[/red]")
            add_task_accomplishment(f"Anvil error: {str(e)}",
                env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
            )
        finally:
            end_task_session(notes=f"Completed hardening session for {target}")

    return harden


def create_docker_cleanup_command() -> Callable[..., None]:
    """Create the docker-cleanup command."""

    def docker_cleanup(
        until: str = typer.Option("24h", help="Prune resources older than this"),
        execute: bool = typer.Option(False, help="Actually prune"),
    ):
        """Clean up Docker resources using ops-docker skill."""
        console.print("[bold blue]Docker cleanup[/bold blue]")
        docker_ops_script = DOCKER_OPS_SKILL / "run.sh"
        if not docker_ops_script.exists():
            console.print("[red]ops-docker skill not found[/red]")
            return
        cmd = [str(docker_ops_script), "prune", "--until", until]
        if execute:
            cmd.append("--execute")
        else:
            console.print("[dim](Dry run - add --execute to prune)[/dim]")
        subprocess.run(cmd,
        env={k: v for k, v in os.environ.items() if k != "VIRTUAL_ENV"},
        )

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
        result = subprocess.run(cmd, capture_output=True, text=True,
        env={k: v for k, v in os.environ.items() if k != "VIRTUAL_ENV"},
        )
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
            env={k: v for k, v in os.environ.items() if k != "VIRTUAL_ENV"},
        )
        if result.returncode == 0:
            try:
                import json
                data = json.loads(result.stdout,
                env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
                )
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


def create_remediate_command() -> Callable[..., None]:
    """Interactive security remediation workflow."""
    
    def remediate(
        target: str = typer.Argument(
            ...,
            help="Path to audit and remediate (file or directory)"
        ),
        auto_fix: bool = typer.Option(
            False,
            "--auto-fix",
            help="Skip interview, apply all automated fixes"
        ),
        plan_only: bool = typer.Option(
            False,
            "--plan-only",
            help="Skip interview, just create remediation plan"
        ),
        profile: str = typer.Option(
            "hobbyist",
            help="Threat profile: script-kiddie, hobbyist, organized-crime, state-actor"
        ),
        model: str = typer.Option(
            "gpt-5.2-codex",
            help="AI model to use for remediation planning"
        ),
    ):
        """Interactive security remediation with monitor tracking."""
        from hack.remediation import remediate_workflow
        from hack.utils import start_task_session, end_task_session, add_task_accomplishment
        
        start_task_session(project=f"remediate-{Path(target).name}")
        add_task_accomplishment(f"Started remediation workflow for {target}")
        
        try:
            remediate_workflow(target, auto_fix=auto_fix, plan_only=plan_only, profile=profile, model=model)
            add_task_accomplishment("Remediation workflow complete")
        except Exception as e:
            console.print(f"[red]Remediation error: {e}[/red]")
            add_task_accomplishment(f"Remediation failed: {str(e)}")
        finally:
            end_task_session(notes=f"Completed remediation for {target}")
    
    return remediate


def create_update_exploits_command() -> Callable[..., None]:
    """Create the update-exploits command using consume-feed skill."""

    def update_exploits(
        source: str = typer.Option(
            "github", help="Source to monitor: github, rss, nvd"
        ),
        query: str = typer.Option(
            "exploit cve", help="Query for exploit search"
        ),
    ):
        """Monitor and ingest latest exploits via consume-feed skill with monitor tracking."""
        from hack.config import CANONICAL_SKILLS
        from hack.utils import start_task_session, end_task_session, add_task_accomplishment
        
        start_task_session(project=f"exploit-feed-{source}")
        console.print(f"[bold blue]Monitoring for latest exploits ({source})...[/bold blue]")
        add_task_accomplishment(f"Updating exploit feed from {source} (query: {query})")
        
        feed_skill = CANONICAL_SKILLS / "consume-feed" / "run.sh"
        if not feed_skill.exists():
            console.print("[red]Error: consume-feed skill not found[/red]")
            end_task_session(notes="consume-feed skill not found")
            return

        # Map source to feed-skill commands
        if source == "github":
            cmd = [str(feed_skill), "run", "--mode", "manual"] # Search is no longer top-level
        elif source == "rss":
            cmd = [str(feed_skill), "run", "--mode", "manual"]
        else:
            cmd = [str(feed_skill), "run", "--mode", "manual"]

        console.print(f"[dim]Executing: {' '.join(cmd)}[/dim]")
        
        try:
            subprocess.run(cmd, check=True,
            env={k: v for k, v in os.environ.items() if k != "VIRTUAL_ENV"},
            )
            console.print("[green]✓ Exploit feed updated[/green]")
            add_task_accomplishment(f"Successfully updated exploit feed from {source}")
        except Exception as e:
            console.print(f"[red]Error updating feed: {e}[/red]")
            add_task_accomplishment(f"Feed update failed: {str(e)}")
        finally:
            end_task_session(notes=f"Completed exploit update from {source}",
            env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
            )

    return update_exploits


# Module exports
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
    "create_remediate_command",
]

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
    "create_remediate_command",
    "create_update_exploits_command",
]
