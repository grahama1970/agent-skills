import functools
import json
import os
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

app = typer.Typer(help="Automated security auditing and ethical hacking tools.")
console = Console()

# Add skills directory to path for common imports
SCRIPT_DIR = Path(__file__).parent
SKILLS_DIR = SCRIPT_DIR.parent
if str(SKILLS_DIR) not in sys.path:
    sys.path.insert(0, str(SKILLS_DIR))

# Import common memory client for standardized resilience patterns
try:
    from common.memory_client import MemoryClient, MemoryScope, with_retries, RateLimiter
    HAS_MEMORY_CLIENT = True
except ImportError:
    HAS_MEMORY_CLIENT = False
    # Fallback: define minimal resilience utilities inline
    def with_retries(max_attempts=3, base_delay=0.5, exceptions=(Exception,), on_retry=None):
        def decorator(func):
            @functools.wraps(func)
            def wrapper(*args, **kwargs):
                last_error = None
                for attempt in range(1, max_attempts + 1):
                    try:
                        return func(*args, **kwargs)
                    except exceptions as e:
                        last_error = e
                        if attempt < max_attempts:
                            delay = base_delay * (2 ** (attempt - 1))
                            time.sleep(delay)
                if last_error:
                    raise last_error
            return wrapper
        return decorator

    class RateLimiter:
        def __init__(self, requests_per_second=5):
            self.interval = 1.0 / max(1, requests_per_second)
            self.last_request = 0.0
            self._lock = threading.Lock()
        def acquire(self):
            with self._lock:
                sleep_time = max(0.0, (self.last_request + self.interval) - time.time())
                if sleep_time > 0:
                    time.sleep(sleep_time)
                self.last_request = time.time()

# Rate limiter for memory operations
_memory_limiter = RateLimiter(requests_per_second=5)

# Docker image name for isolated scanning
SECURITY_IMAGE = "hack-skill-security:latest"
SKILL_DIR = Path(__file__).parent.resolve()

# Skill paths for integration
SKILLS_DIR = Path(__file__).parent.parent
AGENT_SKILLS = Path(__file__).parent.parent.parent.parent / ".agent" / "skills"
MEMORY_SKILL = AGENT_SKILLS / "memory"
ANVIL_SKILL = SKILLS_DIR / "anvil"
DOCKER_OPS_SKILL = SKILLS_DIR / "ops-docker"
TASK_MONITOR_SKILL = SKILLS_DIR / "task-monitor"
TAXONOMY_SKILL = SKILLS_DIR / "taxonomy"
TREESITTER_SKILL = SKILLS_DIR / "treesitter"


def run_skill(skill_path: Path, *args) -> subprocess.CompletedProcess | None:
    """Run a sibling skill and return result."""
    run_script = skill_path / "run.sh"
    if not run_script.exists():
        console.print(f"[yellow]Skill not found: {skill_path.name}[/yellow]")
        return None

    try:
        return subprocess.run(
            [str(run_script), *args],
            capture_output=True, text=True, timeout=300
        )
    except Exception as e:
        console.print(f"[red]Error running {skill_path.name}: {e}[/red]")
        return None


def classify_findings(text: str) -> dict | None:
    """Use taxonomy skill to classify security findings."""
    result = run_skill(TAXONOMY_SKILL, "--text", text, "--collection", "sparta", "--json")
    if result and result.returncode == 0:
        try:
            import json
            return json.loads(result.stdout)
        except:
            pass
    return None


def extract_symbols(file_path: str) -> str | None:
    """Use treesitter skill to extract code symbols before auditing."""
    result = run_skill(TREESITTER_SKILL, "symbols", file_path)
    if result and result.returncode == 0:
        return result.stdout
    return None


def register_task_monitor(name: str, total: int, state_file: str) -> bool:
    """Register a task with the task-monitor for progress tracking."""
    result = run_skill(
        TASK_MONITOR_SKILL,
        "register", "--name", name, "--total", str(total), "--state", state_file
    )
    return result is not None and result.returncode == 0


def memory_recall(query: str, scope: str = "hack_skill", k: int = 3) -> dict | None:
    """
    Query memory skill for relevant prior knowledge with retry logic.
    Returns recall results or None if memory unavailable.
    """
    # Use common MemoryClient if available for standardized resilience
    if HAS_MEMORY_CLIENT:
        try:
            client = MemoryClient(scope=scope)
            result = client.recall(query, k=k)
            if result.found:
                return {
                    "found": True,
                    "items": result.items,
                    "answer": result.items[0].get("solution", "") if result.items else ""
                }
            return {"found": False}
        except Exception:
            return None

    # Fallback: direct subprocess with inline retry logic
    @with_retries(max_attempts=3, base_delay=0.5)
    def _recall_with_retry():
        _memory_limiter.acquire()
        memory_script = MEMORY_SKILL / "run.sh"
        if not memory_script.exists():
            memory_script = Path.home() / "workspace/experiments/pi-mono/.agent/skills/memory/run.sh"
        if not memory_script.exists():
            raise FileNotFoundError("Memory skill not found")

        result = subprocess.run(
            [str(memory_script), "recall", "--q", query, "--scope", scope, "--k", str(k)],
            capture_output=True, text=True, timeout=30
        )
        if result.returncode == 0 and result.stdout:
            try:
                return json.loads(result.stdout)
            except json.JSONDecodeError:
                return {"raw": result.stdout}
        return {"found": False}

    try:
        return _recall_with_retry()
    except Exception:
        return None


def memory_store(content: str, scope: str = "hack_skill", context: str = "security") -> bool:
    """Store knowledge in memory skill with retry logic."""
    # Use common MemoryClient if available for standardized resilience
    if HAS_MEMORY_CLIENT:
        try:
            client = MemoryClient(scope=scope)
            result = client.learn(problem=context, solution=content, tags=["security", "hack_skill"])
            return result.success
        except Exception:
            return False

    # Fallback: direct subprocess with inline retry logic
    @with_retries(max_attempts=3, base_delay=0.5)
    def _store_with_retry():
        _memory_limiter.acquire()
        memory_script = MEMORY_SKILL / "run.sh"
        if not memory_script.exists():
            memory_script = Path.home() / "workspace/experiments/pi-mono/.agent/skills/memory/run.sh"
        if not memory_script.exists():
            raise FileNotFoundError("Memory skill not found")

        result = subprocess.run(
            [str(memory_script), "store", "--content", content, "--scope", scope, "--context", context],
            capture_output=True, text=True, timeout=30
        )
        if result.returncode != 0:
            raise RuntimeError(f"Memory store failed: {result.stderr}")
        return True

    try:
        return _store_with_retry()
    except Exception:
        return False


def show_memory_context(query: str, scope: str = "hack_skill"):
    """Display relevant memory context before an operation."""
    recall = memory_recall(query, scope=scope)
    if recall and recall.get("found"):
        console.print("\n[bold blue]Memory Recall (Prior Knowledge):[/bold blue]")
        if "answer" in recall:
            console.print(f"  {recall['answer'][:500]}...")
        if "sources" in recall:
            for src in recall.get("sources", [])[:3]:
                console.print(f"  [dim]- {src.get('title', 'Unknown')}[/dim]")
        console.print()


def ensure_docker_image() -> bool:
    """Build the security Docker image if it doesn't exist."""
    # Check if image exists
    result = subprocess.run(
        ["docker", "images", "-q", SECURITY_IMAGE],
        capture_output=True, text=True
    )

    if result.stdout.strip():
        return True  # Image exists

    # Build the image
    dockerfile = SKILL_DIR / "docker" / "Dockerfile.security"
    if not dockerfile.exists():
        console.print(f"[red]Dockerfile not found: {dockerfile}[/red]")
        return False

    console.print("[cyan]Building security scanner Docker image (first time only)...[/cyan]")
    build_result = subprocess.run(
        ["docker", "build", "-t", SECURITY_IMAGE, "-f", str(dockerfile), str(SKILL_DIR / "docker")],
        capture_output=True, text=True
    )

    if build_result.returncode != 0:
        console.print(f"[red]Docker build failed:[/red]\n{build_result.stderr}")
        return False

    console.print("[green]Docker image built successfully.[/green]")
    return True


def run_in_docker(cmd: list[str], target_path: str | None = None, network: str = "host") -> subprocess.CompletedProcess:
    """Run a command inside the security Docker container."""
    docker_cmd = [
        "docker", "run", "--rm",
        f"--network={network}",
    ]

    # Mount target directory if specified
    if target_path:
        abs_path = Path(target_path).resolve()
        if abs_path.is_dir():
            docker_cmd.extend(["-v", f"{abs_path}:/scan:ro"])
        elif abs_path.is_file():
            docker_cmd.extend(["-v", f"{abs_path.parent}:/scan:ro"])

    docker_cmd.append(SECURITY_IMAGE)
    docker_cmd.extend(cmd)

    return subprocess.run(docker_cmd, capture_output=True, text=True, timeout=600)

@app.command()
def scan(
    target: str = typer.Argument(..., help="Target IP or hostname to scan"),
    ports: str = typer.Option("1-1000", help="Port range to scan (e.g., '22,80,443' or '1-1000')"),
    scan_type: str = typer.Option("basic", help="Scan type: basic, service, vuln"),
    output: str = typer.Option(None, help="Output file path for results (XML format)"),
    recall: bool = typer.Option(True, help="Query memory for prior scanning knowledge")
):
    """
    Run network vulnerability scan on the target using nmap.

    ALL scanning runs in an isolated Docker container for security.

    Scan types:
      basic   - Host discovery and port scan (-sS -sV)
      service - Service/version detection (-sV -sC)
      vuln    - Vulnerability scripts (--script vuln)
    """
    console.print(f"[bold cyan]Starting {scan_type} scan on target:[/bold cyan] {target}")
    console.print("[dim]Running in isolated Docker container...[/dim]")

    # Memory recall for relevant scanning techniques
    if recall:
        show_memory_context(f"nmap scanning techniques for {scan_type} scan port {ports}")

    if not ensure_docker_image():
        console.print("[red]Failed to build Docker image. Ensure Docker is running.[/red]")
        sys.exit(1)

    # Build nmap command based on scan type
    cmd = ["nmap"]

    if scan_type == "basic":
        cmd.extend(["-sS", "-sV", "-p", ports])
    elif scan_type == "service":
        cmd.extend(["-sV", "-sC", "-p", ports])
    elif scan_type == "vuln":
        cmd.extend(["-sV", "--script", "vuln", "-p", ports])
    else:
        console.print(f"[red]Unknown scan type: {scan_type}[/red]")
        sys.exit(1)

    cmd.append(target)

    console.print(f"[dim]Command: {' '.join(cmd)}[/dim]")

    try:
        result = run_in_docker(cmd, network="host")

        if result.returncode == 0:
            console.print("[green]Scan complete![/green]")
            console.print(result.stdout)
            if result.stderr:
                console.print(f"[dim]{result.stderr}[/dim]")
            if output:
                # Save output to file
                Path(output).write_text(result.stdout)
                console.print(f"[dim]Results saved to: {output}[/dim]")
        else:
            console.print(f"[red]Scan failed:[/red]\n{result.stderr}")
            sys.exit(1)

    except subprocess.TimeoutExpired:
        console.print("[red]Scan timed out (10 min limit)[/red]")
        sys.exit(1)

@app.command()
def audit(
    target: str = typer.Argument(..., help="Directory or file to audit"),
    tool: str = typer.Option("all", help="Tool to use: all, semgrep, bandit"),
    severity: str = typer.Option("medium", help="Minimum severity: low, medium, high"),
    output: str = typer.Option(None, help="Output file (JSON format)"),
    recall: bool = typer.Option(True, help="Query memory for prior audit knowledge")
):
    """
    Run static application security testing (SAST) on code.

    ALL auditing runs in an isolated Docker container for security.
    Uses Semgrep and Bandit to find security vulnerabilities in Python code.
    """
    target_path = Path(target).resolve()
    if not target_path.exists():
        console.print(f"[red]Target not found: {target}[/red]")
        sys.exit(1)

    console.print(f"[bold red]Starting security audit for:[/bold red] {target_path}")
    console.print("[dim]Running in isolated Docker container...[/dim]")

    # Memory recall for relevant vulnerability patterns
    if recall:
        show_memory_context(f"SAST security vulnerabilities {tool} Python code audit")

    if not ensure_docker_image():
        console.print("[red]Failed to build Docker image. Ensure Docker is running.[/red]")
        sys.exit(1)

    results = {"semgrep": None, "bandit": None, "total_findings": 0}

    # Determine mount path
    if target_path.is_file():
        mount_path = target_path.parent
        scan_target = f"/scan/{target_path.name}"
    else:
        mount_path = target_path
        scan_target = "/scan"

    # Run Semgrep
    if tool in ("all", "semgrep"):
        console.print("\n[cyan]Running Semgrep (SAST)...[/cyan]")
        cmd = ["semgrep", "scan", "--config", "auto", scan_target]

        try:
            result = run_in_docker(cmd, target_path=str(mount_path), network="none")
            if result.stdout:
                console.print(result.stdout)
                results["semgrep"] = result.stdout
            if result.stderr:
                console.print(f"[dim]{result.stderr}[/dim]")
        except subprocess.TimeoutExpired:
            console.print("[yellow]Semgrep timed out[/yellow]")
        except Exception as e:
            console.print(f"[yellow]Semgrep error: {e}[/yellow]")

    # Run Bandit (Python-specific)
    if tool in ("all", "bandit"):
        console.print("\n[cyan]Running Bandit (Python SAST)...[/cyan]")

        # Bandit severity: -l (low+), -ll (medium+), -lll (high only)
        severity_flags = {"low": "-l", "medium": "-ll", "high": "-lll"}
        sev_flag = severity_flags.get(severity.lower(), "-ll")

        cmd = ["bandit", "-r", scan_target, sev_flag, "-f", "txt"]

        try:
            result = run_in_docker(cmd, target_path=str(mount_path), network="none")
            if result.stdout:
                console.print(result.stdout)
                results["bandit"] = result.stdout
            if result.stderr and "No issues" not in result.stderr:
                console.print(f"[dim]{result.stderr}[/dim]")
        except subprocess.TimeoutExpired:
            console.print("[yellow]Bandit timed out[/yellow]")
        except Exception as e:
            console.print(f"[yellow]Bandit error: {e}[/yellow]")

    # Save combined results
    if output:
        import json as json_mod
        with open(output, "w") as f:
            json_mod.dump(results, f, indent=2)
        console.print(f"\n[green]Results saved to: {output}[/green]")

    console.print("\n[bold green]Audit complete.[/bold green]")

@app.command()
def tools():
    """
    List available security tools and Docker image status.
    """
    # Check Docker availability
    docker_available = shutil.which("docker") is not None
    image_exists = False

    if docker_available:
        result = subprocess.run(
            ["docker", "images", "-q", SECURITY_IMAGE],
            capture_output=True, text=True
        )
        image_exists = bool(result.stdout.strip())

    # Docker status
    console.print("\n[bold]Container Status:[/bold]")
    docker_status = "[green]Available[/green]" if docker_available else "[red]Not Found[/red]"
    image_status = "[green]Built[/green]" if image_exists else "[yellow]Not Built (will build on first use)[/yellow]"
    console.print(f"  Docker Engine: {docker_status}")
    console.print(f"  Security Image ({SECURITY_IMAGE}): {image_status}")

    # Tools in container
    table = Table(title="\nTools in Security Container")
    table.add_column("Tool", style="cyan")
    table.add_column("Type", style="dim")
    table.add_column("Command", style="green")
    table.add_column("Description")

    tools_info = [
        ("nmap", "Network", "scan", "Network vulnerability scanning"),
        ("semgrep", "SAST", "audit", "Multi-language static analysis"),
        ("bandit", "SAST", "audit", "Python security linter"),
        ("pip-audit", "SCA", "sca", "Python dependency vulnerabilities"),
        ("safety", "SCA", "sca --tool safety", "Python dependency checker"),
    ]

    for tool, tool_type, command, desc in tools_info:
        table.add_row(tool, tool_type, command, desc)

    console.print(table)

    console.print("\n[dim]All tools run in isolated Docker containers - no local installation needed.[/dim]")

    if not docker_available:
        console.print("\n[bold red]Warning:[/bold red] Docker not found. Install Docker to use this skill.")
        console.print("  Install: https://docs.docker.com/engine/install/")


@app.command()
def sca(
    target: str = typer.Argument(".", help="Directory to scan for dependencies"),
    tool: str = typer.Option("pip-audit", help="Tool: pip-audit, safety"),
    output: str = typer.Option(None, help="Output file (JSON)")
):
    """
    Software Composition Analysis - scan dependencies for known vulnerabilities.

    ALL scanning runs in an isolated Docker container for security.
    """
    target_path = Path(target).resolve()
    console.print(f"[bold blue]Scanning dependencies in:[/bold blue] {target_path}")
    console.print("[dim]Running in isolated Docker container...[/dim]")

    if not ensure_docker_image():
        console.print("[red]Failed to build Docker image. Ensure Docker is running.[/red]")
        sys.exit(1)

    # Check for requirements.txt or pyproject.toml
    req_file = target_path / "requirements.txt"
    pyproject = target_path / "pyproject.toml"

    if not req_file.exists() and not pyproject.exists():
        console.print("[yellow]No requirements.txt or pyproject.toml found[/yellow]")

    if tool == "pip-audit":
        cmd = ["pip-audit"]
        if req_file.exists():
            cmd.extend(["-r", "/scan/requirements.txt"])

        console.print(f"[dim]Command: {' '.join(cmd)}[/dim]")

        try:
            result = run_in_docker(cmd, target_path=str(target_path), network="bridge")

            if result.returncode == 0:
                console.print("[green]No vulnerabilities found![/green]")
            else:
                console.print(result.stdout)
                console.print("[yellow]Vulnerabilities detected - review above[/yellow]")

            if result.stderr:
                console.print(f"[dim]{result.stderr}[/dim]")

            if output:
                Path(output).write_text(result.stdout or "")
                console.print(f"[dim]Results saved to: {output}[/dim]")

        except subprocess.TimeoutExpired:
            console.print("[red]Scan timed out[/red]")
            sys.exit(1)

    elif tool == "safety":
        cmd = ["safety", "check"]
        if req_file.exists():
            cmd.extend(["-r", "/scan/requirements.txt"])

        console.print(f"[dim]Command: {' '.join(cmd)}[/dim]")

        try:
            result = run_in_docker(cmd, target_path=str(target_path), network="bridge")
            console.print(result.stdout)
            if result.stderr:
                console.print(f"[dim]{result.stderr}[/dim]")

            if output:
                Path(output).write_text(result.stdout or "")
                console.print(f"[dim]Results saved to: {output}[/dim]")

        except subprocess.TimeoutExpired:
            console.print("[red]Scan timed out[/red]")
            sys.exit(1)

@app.command()
def learn(
    source: str = typer.Option(None, help="Source to fetch exploits from (exploit-db, packetstorm, github)"),
    type: str = typer.Option("exploit", help="Type of learning material (exploit, book)"),
    query: str = typer.Option(None, help="Query for specific topic (e.g. for books)"),
    watch_dir: str = typer.Option(None, help="Directory for Readarr to watch (defaults to ~/workspace/experiments/Readarr/inbox)")
):
    """
    Fetch and update local knowledge base (exploits or books).
    """
    if type == "book":
        if not query:
            console.print("[red]Error: --query required for book learning[/red]")
            return

        console.print(f"[bold blue]Learning from Books (Readarr-Ops)...[/bold blue]")
        
        # Locate skill
        # Try sibling directory first (local dev)
        skill_script = os.path.join(os.path.dirname(__file__), "..", "readarr-ops", "run.sh")
        
        if not os.path.exists(skill_script):
             # Try standard agent path
             skill_script = os.path.expanduser("~/workspace/experiments/pi-mono/.agent/skills/readarr-ops/run.sh")

        if not os.path.exists(skill_script):
            console.print(f"[red]readarr-ops skill not found at {skill_script}[/red]")
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
             console.print("Fetching latest CSV from Exploit-DB...")
             csv_url = "https://gitlab.com/exploit-database/exploitdb/-/raw/main/files_exploits.csv"
             try:
                 import requests
                 resp = requests.get(csv_url, timeout=30)
                 if resp.status_code == 200:
                     target_file = os.path.join(data_dir, "exploitdb.csv")
                     with open(target_file, "wb") as f:
                         f.write(resp.content)
                     console.print(f"[green]Successfully downloaded Exploit-DB database to {target_file}[/green]")
                     count = len(resp.text.splitlines())
                     console.print(f"[dim]Indexed {count} exploits.[/dim]")
                 else:
                     console.print(f"[red]Failed to download: HTTP {resp.status_code}[/red]")
             except Exception as e:
                 console.print(f"[red]Download error: {e}[/red]")

        elif source == "github":
             if not query:
                 console.print("[red]Error: --query required for GitHub source (e.g., 'CVE-2024-1234')[/red]")
                 return
             
             console.print(f"Searching GitHub for repositories matching: {query}...")
             try:
                 import requests
                 api_url = "https://api.github.com/search/repositories"
                 params = {"q": f"{query} topic:exploit", "sort": "updated", "order": "desc"}
                 resp = requests.get(api_url, params=params, headers={"Accept": "application/vnd.github.v3+json"}, timeout=10)
                 
                 if resp.status_code == 200:
                     results = resp.json().get("items", [])
                     if not results:
                         console.print("[yellow]No repositories found.[/yellow]")
                         return
                     
                     repo = results[0]
                     clone_url = repo["clone_url"]
                     repo_name = repo["name"]
                     console.print(f"[green]Found: {repo['full_name']} ({repo['stargazers_count']} stars)[/green]")
                     console.print(f"[dim]{repo['description']}[/dim]")
                     
                     target_path = os.path.join(data_dir, "repos", repo_name)
                     
                     if os.path.exists(target_path):
                         console.print(f"[yellow]Repository already exists at {target_path}. Pulling updates...[/yellow]")
                         subprocess.run(["git", "-C", target_path, "pull"], check=False)
                     else:
                         console.print(f"Cloning to {target_path}...")
                         subprocess.run(["git", "clone", clone_url, target_path], check=True)
                         console.print("[green]Clone complete.[/green]")
                         
                     console.print(f"[bold]Tip:[/bold] Analyze this code with: [cyan]hack process {target_path}[/cyan]")
                     
                 else:
                     console.print(f"[red]GitHub API Error: {resp.status_code}[/red]")
             except Exception as e:
                 console.print(f"[red]GitHub Error: {e}[/red]")
        else:
             console.print(f"[red]Unknown source: {source}[/red]")
    else:
        console.print("[yellow]Please specify --source for exploits or --type book[/yellow]")

@app.command()
def research(
    topic: str = typer.Argument(..., help="Research topic"),
    skill: str = typer.Option("dogpile", help="Skill to use (dogpile, arxiv, perplexity, etc.)")
):
    """
    Leverage other agent skills for deep research.
    """
    console.print(f"[bold purple]Researching '{topic}' using {skill}...[/bold purple]")
    
    skill_map = {
        "dogpile": "dogpile/run.sh",
        "arxiv": "arxiv/run.sh",
        "perplexity": "perplexity/run.sh",
        "code-review": "code-review/run.sh",
        "wayback": "dogpile/run.sh",
        "lean4-prove": "lean4-prove/run.sh",
        "fixture-graph": "fixture-graph/run.sh"
    }
    
    if skill not in skill_map:
        console.print(f"[red]Unknown skill: {skill}. Available: {', '.join(skill_map.keys())}[/red]")
        return

    skill_script = os.path.join(os.path.dirname(__file__), "..", skill_map[skill])
    
    if not os.path.exists(skill_script):
         skill_script = os.path.join(os.path.dirname(__file__), "..", skill, "run.sh")
         if not os.path.exists(skill_script):
            console.print(f"[red]Skill script not found at {skill_script}[/red]")
            return

    cmd = [skill_script, "search" if skill == "dogpile" else "run", topic]
    
    # specialized argument mapping
    if skill == "dogpile": 
        # dogpile search <query>
        cmd = [skill_script, "search", topic]
    elif skill == "arxiv":
        # arxiv search --query <query>
        cmd = [skill_script, "search", "--query", topic]
    
    console.print(f"Executing: {' '.join(cmd)}")
    subprocess.run(cmd)

@app.command()
def process(
    target: str = typer.Argument(..., help="File path, URL, or content to learn from"),
    scope: str = typer.Option("hack_skill", help="Memory scope for storage"),
    context: str = typer.Option(None, help="Context for extraction (e.g. 'security research')")
):
    """
    Process content into memory using the universal 'learn' skill.
    Supports: URL, PDF, GitHub, YouTube, Text, etc.
    """
    console.print(f"[bold green]Processing target:[/bold green] {target}")
    
    # Locate learn skill
    skill_script = os.path.join(os.path.dirname(__file__), "..", "..", "..", ".agent", "skills", "learn", "run.sh")
    
    if not os.path.exists(skill_script):
         skill_script = os.path.expanduser("~/workspace/experiments/pi-mono/.agent/skills/learn/run.sh")
         
    if not os.path.exists(skill_script):
        console.print(f"[red]Learn skill not found at {skill_script}[/red]")
        return
        
    cmd = [skill_script, target, "--scope", scope]
         
    if context:
        cmd.extend(["--context", context])
        
    console.print(f"Executing: {' '.join(cmd)}")
    subprocess.run(cmd)

@app.command()
def prove(
    claim: str = typer.Option(..., help="Security claim or theorem to prove/refute"),
    negate: bool = typer.Option(False, help="Negate the claim to find a counterexample (Red Team mode)"),
    persona: str = typer.Option("security researcher", help="Persona context for proof generation")
):
    """
    Formally verify security properties using Lean4 (via lean4-prove skill).
    """
    
    # Construct requirement
    requirement = claim
    if negate:
        # "There exists an execution where bad thing happens"
        console.print("[bold red]Negating claim to find counterexample (Witness Search)...[/bold red]")
        requirement = f"Refute that {claim}, or prove there exists a state where {claim} is false."
    
    console.print(f"[bold blue]Proving:[/bold blue] {requirement}")

    # Locate skill
    skill_script = os.path.join(os.path.dirname(__file__), "..", "..", "..", ".agent", "skills", "lean4-prove", "run.sh")
    
    if not os.path.exists(skill_script):
         skill_script = os.path.expanduser("~/workspace/experiments/pi-mono/.agent/skills/lean4-prove/run.sh")

    if not os.path.exists(skill_script):
        console.print(f"[red]Lean4-Prove skill not found at {skill_script}[/red]")
        return
        
    cmd = [skill_script, "--requirement", requirement, "--persona", persona]
    
    console.print(f"Executing: {' '.join(cmd)}")
    subprocess.run(cmd)

@app.command()
def exploit(
    target: str = typer.Option(..., help="Target IP/Hostname"),
    env: str = typer.Option("python", help="Environment type (python, c, ruby, node)"),
    payload: str = typer.Option(None, help="Path to exploit script (optional)"),
    interactive: bool = typer.Option(False, help="Run interactively")
):
    """
    Run an exploit or test in an isolated Docker container.
    """
    console.print(f"[bold red]Preparing Isolated Environment ({env})...[/bold red]")
    
    base_images = {
        "python": "python:3.9-slim",
        "c": "gcc:latest",
        "ruby": "ruby:3.0",
        "node": "node:18-slim",
        "kali": "kalilinux/kali-rolling" 
    }
    
    if env not in base_images:
        console.print(f"[red]Unknown environment: {env}. Supported: {', '.join(base_images.keys())}[/red]")
        return
        
    image = base_images[env]
    work_dir = os.path.join(os.getcwd(), f"hack_env_{env}_{os.getpid()}")
    os.makedirs(work_dir, exist_ok=True)
    
    try:
        # Generate Dockerfile
        dockerfile_content = f"""
FROM {image}
WORKDIR /app
RUN apt-get update && apt-get install -y iputils-ping netcat-openbsd curl wget
"""
        if env == "python":
            dockerfile_content += "RUN pip install requests scapy pwntools\n"
        
        # Copy payload if exists
        display_payload_name = "exploit_script"
        if payload:
            if os.path.exists(payload):
                shutil.copy(payload, os.path.join(work_dir, os.path.basename(payload)))
                dockerfile_content += f"COPY {os.path.basename(payload)} /app/\n"
                display_payload_name = os.path.basename(payload)
            else:
                console.print(f"[yellow]Payload {payload} not found, skipping copy.[/yellow]")
                
        with open(os.path.join(work_dir, "Dockerfile"), "w") as f:
            f.write(dockerfile_content)
            
        # Generate compose file
        compose_content = f"""
services:
  exploiter:
    build: .
    command: { 'tail -f /dev/null' if interactive else f'python {display_payload_name}' if env == 'python' and payload else 'echo "No payload provided, container ready."' }
    volumes:
      - .:/app
    network_mode: host
"""
        with open(os.path.join(work_dir, "docker-compose.yml"), "w") as f:
            f.write(compose_content)
            
        console.print(f"[green]Environment ready in {work_dir}[/green]")
        console.print(f"[dim]Building and starting container targeting {target}...[/dim]")
        
        # Build
        subprocess.run(["docker", "compose", "build"], cwd=work_dir, check=True)
        
        # Run
        if interactive:
            console.print("[bold]Entering interactive shell...[/bold]")
            subprocess.run(["docker", "compose", "run", "--rm", "exploiter", "/bin/bash"], cwd=work_dir)
        else:
            console.print("[bold]Running exploit...[/bold]")
            subprocess.run(["docker", "compose", "run", "--rm", "exploiter"], cwd=work_dir)
            
    except Exception as e:
        console.print(f"[bold red]Error during exploitation:[/bold red] {e}")
    finally:
        # Cleanup
        console.print("[dim]Cleaning up environment...[/dim]")
        subprocess.run(["docker", "compose", "down", "--rmi", "local", "-v"], cwd=work_dir, capture_output=True)
        shutil.rmtree(work_dir)
        console.print("[green]Cleanup complete.[/green]")

@app.command()
def harden(
    target: str = typer.Argument(".", help="Directory to harden/red-team"),
    issue: str = typer.Option(None, help="Specific security issue to focus on"),
    mode: str = typer.Option("harden", help="Mode: harden (defensive) or debug (find issues)")
):
    """
    Red-team/harden a codebase using anvil's Thunderdome.

    Spawns multiple agents in isolated git worktrees to compete on fixing
    security issues. Delegates to the anvil skill.
    """
    console.print(f"[bold red]Running Anvil Thunderdome on:[/bold red] {target}")

    # Memory recall for relevant hardening techniques
    show_memory_context(f"security hardening techniques vulnerabilities")

    anvil_script = ANVIL_SKILL / "run.sh"
    if not anvil_script.exists():
        console.print("[red]Anvil skill not found. Install anvil skill first.[/red]")
        return

    cmd = [str(anvil_script), mode, "run"]
    if issue:
        cmd.extend(["--issue", issue])

    console.print(f"[dim]Delegating to anvil: {' '.join(cmd)}[/dim]")
    subprocess.run(cmd, cwd=target)


@app.command()
def docker_cleanup(
    until: str = typer.Option("24h", help="Prune resources older than this"),
    execute: bool = typer.Option(False, help="Actually prune (default is dry-run)")
):
    """
    Clean up Docker resources using ops-docker skill.

    Prunes unused containers, images, and volumes.
    """
    console.print("[bold blue]Docker cleanup via ops-docker skill[/bold blue]")

    docker_ops_script = DOCKER_OPS_SKILL / "run.sh"
    if not docker_ops_script.exists():
        console.print("[red]ops-docker skill not found.[/red]")
        return

    cmd = [str(docker_ops_script), "prune", "--until", until]
    if execute:
        cmd.append("--execute")
    else:
        console.print("[dim](Dry run - add --execute to actually prune)[/dim]")

    subprocess.run(cmd)


@app.command()
def symbols(
    target: str = typer.Argument(..., help="File to extract symbols from"),
    content: bool = typer.Option(False, "-c", help="Include full source code")
):
    """
    Extract code symbols using treesitter skill.

    Useful for understanding code structure before auditing.
    """
    console.print(f"[bold cyan]Extracting symbols from:[/bold cyan] {target}")

    treesitter_script = TREESITTER_SKILL / "run.sh"
    if not treesitter_script.exists():
        console.print("[red]treesitter skill not found.[/red]")
        return

    cmd = [str(treesitter_script), "symbols", target]
    if content:
        cmd.append("--content")

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode == 0:
        console.print(result.stdout)
    else:
        console.print(f"[red]Error: {result.stderr}[/red]")


@app.command()
def classify(
    text: str = typer.Argument(..., help="Security finding text to classify"),
    collection: str = typer.Option("sparta", help="Taxonomy collection: sparta, operational, lore")
):
    """
    Classify security findings using taxonomy skill.

    Returns bridge tags (Loyalty, Fragility, etc.) for graph traversal.
    """
    console.print("[bold purple]Classifying with taxonomy skill...[/bold purple]")

    taxonomy_script = TAXONOMY_SKILL / "run.sh"
    if not taxonomy_script.exists():
        console.print("[red]taxonomy skill not found.[/red]")
        return

    result = subprocess.run(
        [str(taxonomy_script), "--text", text, "--collection", collection, "--json"],
        capture_output=True, text=True
    )

    if result.returncode == 0:
        try:
            import json
            data = json.loads(result.stdout)
            console.print(f"\n[green]Bridge Tags:[/green] {', '.join(data.get('bridge_tags', []))}")
            console.print(f"[blue]Collection Tags:[/blue] {data.get('collection_tags', {})}")
            console.print(f"[dim]Worth Remembering: {data.get('worth_remembering', False)}[/dim]")
        except:
            console.print(result.stdout)
    else:
        console.print(f"[red]Error: {result.stderr}[/red]")


@app.command()
def remember(
    content: str = typer.Argument(..., help="Security knowledge to store in memory"),
    title: str = typer.Option(None, help="Title/summary for the knowledge"),
    tags: str = typer.Option("security", help="Comma-separated tags (e.g., 'exploit,cve,nmap')")
):
    """
    Store security knowledge in memory for future recall.

    Examples:
      hack remember "Use nmap -sV for service detection" --title "nmap tips"
      hack remember "CVE-2024-1234 affects version 1.0-1.5" --tags "cve,critical"
    """
    console.print("[bold blue]Storing knowledge in memory...[/bold blue]")

    # Format content with metadata
    formatted = f"[{title or 'Security Note'}] {content}"
    if tags:
        formatted += f" (tags: {tags})"

    if memory_store(formatted, scope="hack_skill", context="security"):
        console.print("[green]Knowledge stored successfully.[/green]")
        console.print(f"[dim]Content: {content[:100]}{'...' if len(content) > 100 else ''}[/dim]")
    else:
        console.print("[yellow]Memory skill not available. Knowledge not stored.[/yellow]")
        console.print("[dim]Ensure .agent/skills/memory is installed.[/dim]")


@app.command()
def recall(
    query: str = typer.Argument(..., help="Query to search in memory"),
    k: int = typer.Option(5, help="Number of results to return")
):
    """
    Recall security knowledge from memory.

    Examples:
      hack recall "nmap scanning techniques"
      hack recall "buffer overflow exploits" --k 10
    """
    console.print(f"[bold blue]Searching memory for:[/bold blue] {query}")

    result = memory_recall(query, scope="hack_skill", k=k)

    if result is None:
        console.print("[yellow]Memory skill not available.[/yellow]")
        console.print("[dim]Ensure .agent/skills/memory is installed.[/dim]")
        return

    if result.get("found"):
        console.print("\n[green]Found relevant knowledge:[/green]")
        if "answer" in result:
            console.print(f"\n{result['answer']}")
        if "sources" in result:
            console.print("\n[dim]Sources:[/dim]")
            for src in result.get("sources", []):
                console.print(f"  - {src.get('title', src.get('id', 'Unknown'))}")
    elif "raw" in result:
        console.print(result["raw"])
    else:
        console.print("[yellow]No relevant knowledge found in memory.[/yellow]")
        console.print("[dim]Use 'hack remember' to store knowledge, or 'hack learn' to ingest content.[/dim]")


if __name__ == "__main__":
    app()
