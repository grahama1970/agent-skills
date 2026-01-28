#!/usr/bin/env python3
"""
Learn - Unified Knowledge Acquisition for Any Persona Agent

ONE command to learn from ANY content type.
Auto-detects source type and routes to appropriate backend skill.

Usage:
    ./run.sh https://arxiv.org/abs/2302.02083 --scope horus_lore
    ./run.sh https://youtube.com/watch?v=xyz --scope horus_lore
    ./run.sh ./document.pdf --scope project_kb --context "technical docs"
    ./run.sh --list --scope horus_lore
"""

import hashlib
import json
import re
import subprocess
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Optional, List, Tuple
from urllib.parse import urlparse

try:
    import typer
    from rich.console import Console
    from rich.table import Table
except ImportError:
    print("Installing dependencies...")
    subprocess.run([sys.executable, "-m", "pip", "install", "typer", "rich", "-q"])
    import typer
    from rich.console import Console
    from rich.table import Table

# Paths
SKILL_DIR = Path(__file__).resolve().parent
DATA_DIR = Path.home() / ".learn"

# Skills locations - check in order of preference
SKILLS_DIRS = [
    Path.home() / ".claude" / "skills",
    Path.home() / ".pi" / "skills",
    SKILL_DIR.parent,  # Sibling skills in same directory
]

console = Console()


class SourceType(Enum):
    """Types of content sources."""
    ARXIV = "arxiv"
    YOUTUBE = "youtube"
    GITHUB = "github"
    PDF = "pdf"
    AUDIOBOOK = "audiobook"
    URL = "url"
    FILE = "file"
    UNKNOWN = "unknown"


@dataclass
class LearnedItem:
    """Record of something learned."""
    source: str
    source_type: str
    title: str
    learned_at: str
    context: str
    scope: str
    success: bool
    error: Optional[str] = None
    qa_count: int = 0


def find_skill(skill_name: str) -> Optional[Path]:
    """Find a skill directory by name."""
    for skills_dir in SKILLS_DIRS:
        skill_path = skills_dir / skill_name
        if skill_path.exists() and (skill_path / "run.sh").exists():
            return skill_path
    return None


def detect_source_type(source: str) -> SourceType:
    """Auto-detect source type from URL or path."""
    if source.startswith(("http://", "https://")):
        domain = urlparse(source).netloc.lower()
        if "arxiv.org" in domain:
            return SourceType.ARXIV
        if any(yt in domain for yt in ["youtube.com", "youtu.be"]):
            return SourceType.YOUTUBE
        if "github.com" in domain:
            return SourceType.GITHUB
        if source.lower().endswith(".pdf"):
            return SourceType.PDF
        return SourceType.URL

    if source.lower().endswith(".pdf"):
        return SourceType.PDF
    if source.lower().endswith((".aax", ".aaxc", ".m4b", ".m4a")):
        return SourceType.AUDIOBOOK
    if Path(source).exists():
        return SourceType.FILE

    return SourceType.UNKNOWN


def run_skill(skill_name: str, args: List[str]) -> Tuple[bool, str, int]:
    """Run a skill and return (success, output, qa_count)."""
    skill_dir = find_skill(skill_name)
    if not skill_dir:
        return False, f"Skill not found: {skill_name}", 0

    console.print(f"[dim]Running: {skill_name} {' '.join(args[:3])}...[/dim]")

    try:
        result = subprocess.run(
            [str(skill_dir / "run.sh")] + args,
            capture_output=True,
            text=True,
            timeout=300,
            cwd=str(skill_dir),
        )
        output = result.stdout + result.stderr
        qa_match = re.search(r"(\d+)\s*(?:Q&A|pairs|questions)", output, re.I)
        qa_count = int(qa_match.group(1)) if qa_match else 0
        return result.returncode == 0, output[:1000], qa_count
    except subprocess.TimeoutExpired:
        return False, "Timeout after 5 minutes", 0
    except Exception as e:
        return False, str(e), 0


class Learner:
    """Tracks learned content per scope."""

    def __init__(self, scope: str):
        self.scope = scope
        self.data_dir = DATA_DIR / scope
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.learned_file = self.data_dir / "learned.json"
        self.learned = self._load()

    def _load(self) -> dict:
        if self.learned_file.exists():
            try:
                return json.loads(self.learned_file.read_text())
            except json.JSONDecodeError:
                pass
        return {"items": [], "hashes": {}}

    def _save(self):
        self.learned_file.write_text(json.dumps(self.learned, indent=2))

    def _hash(self, source: str) -> str:
        return hashlib.sha256(source.encode()).hexdigest()[:16]

    def already_learned(self, source: str) -> bool:
        return self._hash(source) in self.learned.get("hashes", {})

    def record(self, item: LearnedItem):
        self.learned["items"].append(asdict(item))
        self.learned["hashes"][self._hash(item.source)] = len(self.learned["items"]) - 1
        self._save()

    def list_items(self) -> List[dict]:
        return self.learned.get("items", [])

    def learn(self, source: str, context: str, force: bool = False) -> Tuple[bool, str]:
        """Learn from a source. Returns (success, message)."""
        if not force and self.already_learned(source):
            return False, f"Already learned: {source} (use --force to re-learn)"

        source_type = detect_source_type(source)
        if source_type == SourceType.UNKNOWN:
            return False, f"Unknown source type: {source}"

        console.print(f"[cyan]Type:[/cyan] {source_type.value}")

        # Route to handler
        handlers = {
            SourceType.ARXIV: self._learn_arxiv,
            SourceType.YOUTUBE: self._learn_youtube,
            SourceType.GITHUB: self._learn_url,
            SourceType.PDF: self._learn_pdf,
            SourceType.AUDIOBOOK: self._learn_audiobook,
            SourceType.URL: self._learn_url,
            SourceType.FILE: self._learn_file,
        }

        handler = handlers.get(source_type, self._learn_url)
        success, message, qa_count = handler(source, context)

        # Record result
        title = self._extract_title(source)
        self.record(LearnedItem(
            source=source,
            source_type=source_type.value,
            title=title,
            learned_at=datetime.now(timezone.utc).isoformat(),
            context=context,
            scope=self.scope,
            success=success,
            error=None if success else message,
            qa_count=qa_count,
        ))

        return success, message

    def _extract_title(self, source: str) -> str:
        if source.startswith(("http://", "https://")):
            parts = [p for p in urlparse(source).path.split("/") if p]
            return parts[-1].replace("-", " ").replace("_", " ") if parts else source[:50]
        return Path(source).stem.replace("-", " ").replace("_", " ")

    def _learn_arxiv(self, source: str, context: str) -> Tuple[bool, str, int]:
        """Learn from arXiv paper."""
        match = re.search(r"(\d+\.\d+)", source)
        if not match:
            return False, "Could not extract arXiv ID", 0
        paper_id = match.group(1)
        return run_skill("arxiv", ["learn", paper_id, "--scope", self.scope, "--context", context, "--skip-interview"])

    def _learn_youtube(self, source: str, context: str) -> Tuple[bool, str, int]:
        """Learn from YouTube video."""
        success, transcript, _ = run_skill("youtube-transcripts", [source])
        if not success:
            return False, f"Failed to get transcript: {transcript}", 0

        temp = Path("/tmp/learn_yt.txt")
        temp.write_text(transcript)
        return run_skill("distill", ["--file", str(temp), "--scope", self.scope, "--context", context])

    def _learn_pdf(self, source: str, context: str) -> Tuple[bool, str, int]:
        """Learn from PDF."""
        success, content, _ = run_skill("extractor", [source])
        if not success:
            return False, f"Failed to extract: {content}", 0

        temp = Path("/tmp/learn_pdf.txt")
        temp.write_text(content)
        return run_skill("distill", ["--file", str(temp), "--scope", self.scope, "--context", context])

    def _learn_url(self, source: str, context: str) -> Tuple[bool, str, int]:
        """Learn from URL."""
        success, content, _ = run_skill("fetcher", [source])
        if not success:
            return False, f"Failed to fetch: {content}", 0

        temp = Path("/tmp/learn_url.txt")
        temp.write_text(content)
        return run_skill("distill", ["--file", str(temp), "--scope", self.scope, "--context", context])

    def _learn_audiobook(self, source: str, context: str) -> Tuple[bool, str, int]:
        """Learn from audiobook (AAX, M4B, etc.)."""
        # Use audiobook-ingest to transcribe, then distill
        success, output, _ = run_skill("audiobook-ingest", ["ingest", source])
        if not success:
            return False, f"Failed to transcribe: {output}", 0

        # The transcript should be in the output or a known location
        # audiobook-ingest creates ~/clawd/library/books/<name>/transcript.txt
        book_name = Path(source).stem
        transcript_path = Path.home() / "clawd" / "library" / "books" / book_name / "transcript.txt"
        if transcript_path.exists():
            return run_skill("distill", ["--file", str(transcript_path), "--scope", self.scope, "--context", context])
        return False, "Transcript not found after ingestion", 0

    def _learn_file(self, source: str, context: str) -> Tuple[bool, str, int]:
        """Learn from local file."""
        return run_skill("distill", ["--file", source, "--scope", self.scope, "--context", context])


def find_knowledge_gaps() -> list:
    """Query episodic memory and logs for knowledge gaps (errors, persistent failures)."""
    gaps = []

    # 1. Check for skill failures in logs
    log_paths = [
        Path.home() / "workspace" / "experiments" / "pi-mono" / "logs",
        Path.home() / ".claude" / "logs",
        Path("/tmp"),
    ]

    skill_failures = {}  # skill_name -> count of failures

    for log_dir in log_paths:
        if not log_dir.exists():
            continue
        for log_file in log_dir.glob("*.log"):
            try:
                content = log_file.read_text()[-50000:]  # Last 50k chars
                # Look for failure patterns
                for line in content.split("\n"):
                    line_lower = line.lower()
                    if "fail" in line_lower or "error" in line_lower:
                        # Try to extract skill name
                        for skill in ["fixture-graph", "fixture-table", "code-review", "anvil",
                                      "extractor", "distill", "arxiv", "fetcher"]:
                            if skill in line_lower:
                                skill_failures[skill] = skill_failures.get(skill, 0) + 1
                                if skill_failures[skill] <= 3:  # Don't flood with same skill
                                    gaps.append({
                                        "type": "skill_failure",
                                        "content": line[:200],
                                        "skill": skill,
                                        "reason": f"/{skill} failed - may need deeper understanding",
                                    })
            except Exception:
                pass

    # 2. Check learned items for patterns of failure
    for scope_dir in (Path.home() / ".learn").glob("*"):
        learned_file = scope_dir / "learned.json"
        if learned_file.exists():
            try:
                data = json.loads(learned_file.read_text())
                for item in data.get("items", []):
                    if not item.get("success"):
                        gaps.append({
                            "type": "learn_failure",
                            "content": item.get("source", "")[:100],
                            "reason": item.get("error", "Learning failed")[:100],
                        })
            except Exception:
                pass

    # 3. Try ArangoDB for episodic memory
    try:
        from dotenv import load_dotenv, find_dotenv
        load_dotenv(find_dotenv(usecwd=True))

        import os
        arango_url = os.getenv("ARANGO_URL", "http://127.0.0.1:8529")
        arango_db = os.getenv("ARANGO_DB", "memory")

        from arango import ArangoClient
        client = ArangoClient(hosts=arango_url)
        db = client.db(arango_db, username=os.getenv("ARANGO_USER", "root"),
                       password=os.getenv("ARANGO_PASS", ""))

        # 3a. Find UNRESOLVED SESSIONS (high priority)
        if db.has_collection("unresolved_sessions"):
            query = """
            FOR doc IN unresolved_sessions
                FILTER doc.status == "pending"
                SORT doc.archived_at DESC
                LIMIT 10
                RETURN doc
            """
            for doc in db.aql.execute(query):
                resolution = doc.get("resolution", {})
                gaps.append({
                    "type": "unresolved_session",
                    "content": doc.get("summary", "")[:200],
                    "reason": resolution.get("reason", "Session not resolved"),
                    "session_id": doc.get("session_id"),
                    "priority": "high",
                })
                # Also add specific unresolved items
                for item in resolution.get("unresolved_items", [])[:3]:
                    gaps.append({
                        "type": item.get("type", "unresolved"),
                        "content": item.get("content", "")[:200],
                        "reason": f"From session: {doc.get('session_id', 'unknown')[:30]}",
                        "priority": "high",
                    })

        # 3b. Find errors and questions from conversations
        query = """
        FOR doc IN agent_conversations
            FILTER doc.category IN ["error", "question"]
            SORT doc.timestamp DESC
            LIMIT 20
            RETURN {body: doc.body, category: doc.category}
        """
        for doc in db.aql.execute(query):
            body = doc.get("body", "")[:300]
            gaps.append({
                "type": doc.get("category", "unknown"),
                "content": body,
                "reason": "From episodic memory",
            })

    except ImportError:
        console.print("[dim]Note: python-arango not installed - skipping episodic memory[/dim]")
    except Exception as e:
        console.print(f"[dim]Episodic memory unavailable: {e}[/dim]")

    # 4. Dedupe and prioritize
    seen = set()
    unique_gaps = []
    for gap in gaps:
        key = gap["content"][:50]
        if key not in seen:
            seen.add(key)
            unique_gaps.append(gap)

    return unique_gaps


def main(
    source: Optional[str] = typer.Argument(None, help="URL or file path to learn from"),
    scope: str = typer.Option(..., "--scope", "-s", help="Memory scope (e.g., 'horus_lore', 'project_kb')"),
    context: str = typer.Option("general", "--context", "-c", help="Domain context for better extraction"),
    force: bool = typer.Option(False, "--force", "-f", help="Re-learn even if already learned"),
    dry_run: bool = typer.Option(False, "--dry-run", "-n", help="Preview without learning"),
    list_items: bool = typer.Option(False, "--list", "-l", help="List learned content"),
    request: bool = typer.Option(False, "--request", "-r", help="Request content (e.g., audiobook) if not available"),
    from_gaps: bool = typer.Option(False, "--from-gaps", "-g", help="Reflect on past errors/questions to find what to learn"),
):
    """Learn from ANY content type. Routes to appropriate backend skill."""
    learner = Learner(scope)

    # Reflection mode - find knowledge gaps from episodic memory
    if from_gaps:
        console.print("[bold cyan]Reflecting on past conversations...[/bold cyan]")
        gaps = find_knowledge_gaps()

        if not gaps:
            console.print("[yellow]No knowledge gaps found in episodic memory[/yellow]")
            return

        console.print(f"\n[bold]Found {len(gaps)} potential knowledge gaps:[/bold]\n")

        from rich.table import Table
        table = Table(title="Knowledge Gaps (from reflection)")
        table.add_column("Type", style="cyan")
        table.add_column("Content", style="white", max_width=60)
        table.add_column("Reason", style="dim")

        for gap in gaps[:20]:  # Show top 20
            table.add_row(
                gap["type"],
                gap["content"][:60] + "..." if len(gap["content"]) > 60 else gap["content"],
                gap["reason"],
            )

        console.print(table)
        console.print("\n[dim]Use these to guide what to learn next.[/dim]")
        console.print("[dim]Example: ./run.sh '<search query from gap>' --scope <scope>[/dim]")
        return

    # List mode
    if list_items:
        items = learner.list_items()
        if not items:
            console.print(f"[yellow]Nothing learned for scope: {scope}[/yellow]")
            return

        table = Table(title=f"Learned ({scope})")
        table.add_column("Type", style="cyan")
        table.add_column("Title", style="white")
        table.add_column("Date", style="green")
        table.add_column("Q&A", style="yellow")

        for item in items:
            table.add_row(
                item.get("source_type", "?"),
                item.get("title", "?")[:40],
                item.get("learned_at", "?")[:10],
                str(item.get("qa_count", 0)),
            )
        console.print(table)
        return

    # Require source
    if not source:
        console.print("[red]Error: SOURCE required[/red]")
        console.print("Usage: ./run.sh <url-or-file> --scope <scope>")
        raise typer.Exit(1)

    # Request mode - for content not yet available (e.g., audiobooks)
    if request:
        requests_file = learner.data_dir / "requests.json"
        requests = json.loads(requests_file.read_text()) if requests_file.exists() else []
        requests.append({
            "source": source,
            "context": context,
            "scope": scope,
            "requested_at": datetime.now(timezone.utc).isoformat(),
        })
        requests_file.write_text(json.dumps(requests, indent=2))
        console.print(f"[yellow]REQUESTED[/yellow] {source}")
        console.print(f"[dim]Saved to {requests_file}[/dim]")
        return

    # Dry run
    if dry_run:
        source_type = detect_source_type(source)
        console.print(f"[yellow]DRY RUN[/yellow] Would learn {source_type.value}: {source}")
        return

    # Learn
    success, message = learner.learn(source, context, force)
    if success:
        console.print(f"[green]OK[/green] {message[:200]}")
    else:
        console.print(f"[red]FAIL[/red] {message[:200]}")
        raise typer.Exit(1)


if __name__ == "__main__":
    typer.run(main)
