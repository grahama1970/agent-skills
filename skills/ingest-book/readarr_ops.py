import typer
import sys
import os
import subprocess
import time
import requests
from rich.console import Console
from rich.table import Table
import json
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

app = typer.Typer(help="Manage Readarr library and operations.")
console = Console()

READARR_BIN = os.environ.get("READARR_BIN", os.path.expanduser("~/workspace/experiments/Readarr/Readarr"))
READARR_DATA = os.environ.get("READARR_DATA", os.path.expanduser("~/workspace/experiments/Readarr/data"))
BASE_URL = os.environ.get("READARR_BASE_URL", "http://localhost:8787/api/v1")
BOOKS_ROOT = os.environ.get("READARR_BOOKS_ROOT", os.path.expanduser("~/workspace/experiments/Readarr/books"))
SKILLS_DIR = Path(__file__).resolve().parent.parent


def make_session() -> requests.Session:
    session = requests.Session()
    retry = Retry(
        total=3,
        backoff_factor=0.8,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods={"GET", "POST"},
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session


def _validate_nzb_base_url(raw: str) -> Optional[str]:
    try:
        u = urlparse(raw.strip())
        if u.scheme != "https":
            return None
        host = (u.netloc or "").lower()
        if not (host.endswith("nzbgeek.info")):
            return None
        return f"https://{host}"
    except Exception:
        return None

def log_status(msg: str, provider: str = "readarr", status: Optional[str] = None):
    try:
        sys.stderr.write(f"[READARR-STATUS] {msg[:300]}\n")
        sys.stderr.flush()
    except Exception:
        pass
    state_file = Path("dogpile_state.json")
    state = {}
    if state_file.exists():
        try:
            state = json.loads(state_file.read_text())
        except Exception:
            state = {}
    state.setdefault("providers", {})[provider] = status or "RUNNING"
    state["last_msg"] = msg[:300]
    state["last_updated"] = time.strftime("%Y-%m-%d %H:%M:%S")
    try:
        tmp = state_file.with_suffix(".tmp")
        tmp.write_text(json.dumps(state))
        os.replace(tmp, state_file)
    except Exception:
        pass

def get_api_key():
    return os.environ.get("READARR_API_KEY", "")

@app.command()
def health():
    """Check if Readarr is running and responsive."""
    log_status("Health check started", status="RUNNING")
    try:
        session = make_session()
        session.get(f"{BASE_URL}/health", timeout=3)
        console.print("[green]Readarr is running and healthy.[/green]")
        log_status("Health check ok", status="DONE")
        return True
    except requests.exceptions.Timeout:
        console.print("[red]Readarr health check timed out.[/red]")
        log_status("Health check timeout", status="ERROR")
        return False
    except requests.exceptions.ConnectionError:
        console.print("[red]Readarr is NOT running.[/red]")
        log_status("Health check connection error", status="ERROR")
        return False
    except Exception as e:
        console.print(f"[red]Error checking health: {e}")
        log_status(f"Health check error: {e}", status="ERROR")
        return False

@app.command()
def ensure_running():
    """Start Readarr if it is not running."""
    if health():
        return

    if not os.path.exists(READARR_BIN):
        console.print(f"[bold red]Readarr binary not found at {READARR_BIN}[/bold red]")
        log_status("Readarr binary missing", status="ERROR")
        sys.exit(1)

    console.print("[yellow]Starting Readarr...[/yellow]")
    log_status("Starting Readarr process", status="RUNNING")
    subprocess.Popen([READARR_BIN, "-nobrowser", "-data", READARR_DATA], 
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    
    # Wait for startup
    for i in range(10):
        time.sleep(2)
        if health():
            log_status("Readarr started", status="DONE")
            return
        console.print(f"Waiting for Readarr... ({i+1}/10)")
    
    console.print("[red]Failed to start Readarr.[/red]")
    log_status("Failed to start Readarr", status="ERROR")
    sys.exit(1)

@app.command()
def search(term: str = typer.Argument(..., help="Search term")):
    """Search for books/authors in Readarr."""
    ensure_running()
    log_status(f"Search started: {term[:80]}", status="RUNNING")

    params = {"term": term}
    headers = {"X-Api-Key": get_api_key()}
    session = make_session()

    try:
        resp = session.get(f"{BASE_URL}/book/lookup", params=params, headers=headers, timeout=10)

        if resp.status_code == 401:
            console.print("[red]Authentication failed. Set READARR_API_KEY.[/red]")
            log_status("Search failed: 401", status="ERROR")
            return

        if resp.status_code in (429, 503, 500, 502, 504):
            console.print(f"[red]Service error ({resp.status_code}). Please retry later.[/red]")
            log_status(f"Search service error: {resp.status_code}", status="ERROR")
            return

        try:
            results = resp.json()
        except ValueError:
            console.print(f"[red]API returned non-JSON response (Status: {resp.status_code})[/red]")
            log_status("Search parse error: non-JSON", status="ERROR")
            return

        if isinstance(results, dict) and "message" in results:
            console.print(f"[red]API Error: {results['message']}")
            log_status("Search API error message", status="ERROR")
            return

        if not results:
            console.print("[yellow]No results found.[/yellow]")
            log_status("Search done: 0 results", status="DONE")
            return

        table = Table(title=f"Search Results: {term}")
        table.add_column("Title", style="cyan")
        table.add_column("Author", style="green")
        table.add_column("Year", style="magenta")

        for book in results[:10]:  # Limit to top 10
            title = book.get("title", "Unknown")
            author = "Unknown"
            if "author" in book:
                author = book["author"].get("authorName", "Unknown")
            year = str(book.get("year", ""))
            table.add_row(title, author, year)
        console.print(table)
        log_status(f"Search done: displayed {min(10, len(results))}", status="DONE")

    except Exception as e:
        console.print(f"[red]API Error: {e}")
        log_status(f"Search exception: {e}", status="ERROR")

@app.command(name="list-profiles")
def list_profiles():
    """List quality and metadata profiles from Readarr."""
    ensure_running()
    log_status("Listing profiles", status="RUNNING")
    headers = {"X-Api-Key": get_api_key()}
    session = make_session()

    try:
        # Quality Profiles
        resp_q = session.get(f"{BASE_URL}/qualityprofile", headers=headers, timeout=10)
        q_profiles = resp_q.json() if resp_q.status_code == 200 else []

        # Metadata Profiles
        resp_m = session.get(f"{BASE_URL}/metadataprofile", headers=headers, timeout=10)
        m_profiles = resp_m.json() if resp_m.status_code == 200 else []

        # Root Folders
        resp_r = session.get(f"{BASE_URL}/rootfolder", headers=headers, timeout=10)
        root_folders = resp_r.json() if resp_r.status_code == 200 else []

        table = Table(title="Readarr Profiles & Folders")
        table.add_column("Type", style="bold magenta")
        table.add_column("ID", style="cyan")
        table.add_column("Name / Path", style="green")

        for p in q_profiles:
            table.add_row("Quality", str(p.get("id")), p.get("name", "Unknown"))
        for p in m_profiles:
            table.add_row("Metadata", str(p.get("id")), p.get("name", "Unknown"))
        for f in root_folders:
            table.add_row("Root Folder", str(f.get("id")), f.get("path", "Unknown"))

        console.print(table)
        log_status("Profiles listed", status="DONE")

    except Exception as e:
        console.print(f"[red]Error fetching profiles: {e}")
        log_status("Profile fetch failed", status="ERROR")

@app.command()
def add(
    term: str = typer.Argument(..., help="Book to add"),
    quality_profile_id: int = typer.Option(1, "--quality", "-q", help="Quality profile ID"),
    metadata_profile_id: int = typer.Option(1, "--metadata", "-m", help="Metadata profile ID"),
):
    """Search and add the first matching book."""
    ensure_running()
    log_status(f"Add started: {term[:80]}", status="RUNNING")

    params = {"term": term}
    headers = {"X-Api-Key": get_api_key()}
    session = make_session()

    try:
        # Search
        resp = session.get(f"{BASE_URL}/book/lookup", params=params, headers=headers, timeout=10)
        
        if resp.status_code == 401:
            console.print("[red]Authentication failed. Set READARR_API_KEY.[/red]")
            log_status("Add failed: 401", status="ERROR")
            return

        if resp.status_code in (429, 503, 500, 502, 504):
            console.print(f"[red]Service error ({resp.status_code}). Please retry later.[/red]")
            log_status(f"Add service error: {resp.status_code}", status="ERROR")
            return

        try:
            results = resp.json()
        except ValueError:
            console.print(f"[red]API returned non-JSON response (Status: {resp.status_code})[/red]")
            log_status("Add parse error: non-JSON", status="ERROR")
            return

        if isinstance(results, dict) and "message" in results:
            console.print(f"[red]API Error: {results['message']}")
            log_status("Add API error message", status="ERROR")
            return

        if not results:
            console.print("[yellow]No books found.[/yellow]")
            log_status("Add done: no books", status="DONE")
            return

        # Add first result
        book = results[0]
        title = book.get("title", "Unknown")
        console.print(f"[cyan]Found: {title}[/cyan]")

        post_data = {
            "title": title,
            "authorId": book.get("authorId"),
            "foreignBookId": book.get("foreignBookId"),
            "monitored": True,
            "rootFolderPath": BOOKS_ROOT,
            "qualityProfileId": quality_profile_id,
            "metadataProfileId": metadata_profile_id,
            "addOptions": {"searchForNewBook": True}
        }

        add_resp = session.post(f"{BASE_URL}/book", json=post_data, headers=headers, timeout=15)
        if add_resp.status_code in (200, 201):
            console.print(f"[bold green]Successfully added '{title}' to Readarr.[/bold green]")
            log_status("Add done: success", status="DONE")
        else:
            console.print(f"[red]Failed to add book: {add_resp.text[:200]}")
            log_status(f"Add failed: {add_resp.status_code}", status="ERROR")

    except Exception as e:
        console.print(f"[red]API Error: {e}")
        log_status(f"Add exception: {e}", status="ERROR")

@app.command(name="nzb-search")
def nzb_search(
    term: str = typer.Argument(..., help="Search term"),
    json_output: bool = typer.Option(False, "--json", help="Output raw JSON")
):
    """Directly search Usenet via NZBGeek (Newznab API)."""
    log_status(f"NZB search started: {term[:80]}", status="RUNNING")
    api_key = os.environ.get("NZBD_GEEK_API_KEY") or os.environ.get("NZBGEEK_API_KEY")
    base_url_env = os.environ.get("NZBD_GEEK_BASE_URL") or os.environ.get("NZBGEEK_BASE_URL") or "https://api.nzbgeek.info/"
    base_url = _validate_nzb_base_url(base_url_env)

    if not api_key:
        msg = "NZB API key missing"
        if json_output:
            print(json.dumps({"error": "NZBD_GEEK_API_KEY not found"}))
        else:
            console.print("[red]Error: NZBD_GEEK_API_KEY not found in environment.[/red]")
        log_status(msg, status="ERROR")
        return

    if not base_url:
        err = "Invalid NZB base URL (must be https and nzbgeek.info)"
        if json_output:
            print(json.dumps({"error": err}))
        else:
            console.print(f"[red]{err}[/red]")
        log_status("NZB base URL rejected", status="ERROR")
        return

    params = {"t": "search", "q": term, "apikey": api_key, "o": "json"}

    if not json_output:
        console.print(f"[cyan]Searching NZBGeek for: {term}[/cyan]")

    try:
        url = f"{base_url.rstrip('/')}/api"
        session = make_session()
        resp = session.get(url, params=params, timeout=15)

        if resp.status_code != 200:
            if json_output:
                print(json.dumps({"error": f"API Status {resp.status_code}", "body": resp.text[:200]}))
            else:
                console.print(f"[red]API Error (Status: {resp.status_code}): {resp.text[:200]}[/red]")
            log_status(f"NZB API error: {resp.status_code}", status="ERROR")
            return

        try:
            data = resp.json()
        except ValueError:
            if json_output:
                print(json.dumps({"error": "Invalid JSON response"}))
            else:
                console.print(f"[red]API returned invalid JSON: {resp.text[:100]}[/red]")
            log_status("NZB parse error: invalid JSON", status="ERROR")
            return

        items = []
        if "channel" in data and "item" in data["channel"]:
            items = data["channel"]["item"]
            if isinstance(items, dict):
                items = [items]
        elif "item" in data:
            items = data["item"]

        if json_output:
            print(json.dumps(items))
            log_status(f"NZB search done: {len(items)} items", status="DONE")
            return

        if not items:
            console.print("[yellow]No results found.[/yellow]")
            log_status("NZB search done: 0 items", status="DONE")
            return

        table = Table(title=f"NZBGeek Results: {term}")
        table.add_column("Title", style="cyan")
        table.add_column("Category", style="magenta")
        table.add_column("Size", style="green")
        table.add_column("PubDate", style="dim")

        for item in items[:15]:
            title = item.get("title", "Unknown")
            category = item.get("category", "Unknown")
            size = item.get("size", "0")
            try:
                size_int = int(size)
                size_str = f"{size_int / (1024*1024):.1f} MB"
            except Exception:
                size_str = size
            pubdate = item.get("pubDate", "")[:16]
            table.add_row(title, str(category), size_str, pubdate)

        console.print(table)
        log_status(f"NZB search done: displayed {min(15, len(items))}", status="DONE")

    except Exception as e:
        if json_output:
            print(json.dumps({"error": str(e)}))
        else:
            console.print(f"[red]Search failed: {e}")
        log_status(f"NZB search failed: {e}", status="ERROR")


@app.command(name="advanced-search")
def advanced_search(
    title: str = typer.Option(None, "--title", "-t", help="Book title"),
    author: str = typer.Option(None, "--author", "-a", help="Author name"),
    isbn: str = typer.Option(None, "--isbn", "-i", help="ISBN-13 or ISBN-10"),
    json_output: bool = typer.Option(False, "--json", help="Output raw JSON")
):
    """
    Advanced search using NZBGeek (GeekSeek) syntax.
    Bypasses Readarr API due to upstream metadata issues.
    """
    ensure_running()
    
    parts = []
    if author:
        parts.append(f"author:{author}")
    if title:
        parts.append(f"title:{title}") # GeekSeek supports this or just text
    if isbn:
        parts.append(f"isbn:{isbn}") # GeekSeek syntax if supported, or just the number
        
    if not parts:
        if json_output:
            print(json.dumps({"error": "Provide at least title, author, or isbn"}))
        else:
            console.print("[red]Provide at least title, author, or isbn.[/red]")
        return
        
    query = " ".join(parts)
    
    if not json_output:
        console.print(f"[cyan]Executing GeekSeek Search: {query}[/cyan]")
        
    # Delegate to nzb_search
    nzb_search(term=query, json_output=json_output)



@app.command()
def retrieve(term: str = typer.Argument(..., help="Search term to retrieve and extract")):
    """
    Retrieve a book's file path and extract its content via /extractor.
    """
    ensure_running()
    
    log_status(f"Retrieve started: {term[:80]}", status="RUNNING")
    headers = {"X-Api-Key": get_api_key()}
    session = make_session()

    try:
        # 1. Search for the book
        console.print(f"[cyan]Searching library for: {term}[/cyan]")
        resp = session.get(f"{BASE_URL}/book", headers=headers, timeout=10)
        
        if resp.status_code != 200:
             console.print(f"[red]API Error (Status: {resp.status_code})[/red]")
             log_status(f"Retrieve list error: {resp.status_code}", status="ERROR")
             return

        try:
             books = resp.json()
        except ValueError:
             console.print(f"[red]API returned non-JSON response[/red]")
             log_status("Retrieve parse error: non-JSON", status="ERROR")
             return

        # Filter manually since /book doesn't always support search params well for this
        # We need a book that is downloaded (has bookFile)
        
        target_book = None
        for book in books:
            if term.lower() in book.get("title", "").lower():
                if "bookFile" in book and book["bookFile"].get("path"):
                    target_book = book
                    break
        
        if not target_book:
            console.print("[yellow]Book not found in library or not downloaded (no file).[/yellow]")
            log_status("Retrieve done: no file", status="DONE")
            return

        file_path = target_book["bookFile"]["path"]
        console.print(f"[green]Found file:[/green] {file_path}")
        
        # 2. Call Extractor Skill
        extractor_script = SKILLS_DIR / "extractor" / "run.sh"
        
        if not extractor_script.exists():
             # Fallback to .agent/skills location if not flat
             extractor_script = SKILLS_DIR.parent.parent / ".agent" / "skills" / "extractor" / "run.sh"
        
        if not extractor_script.exists():
             console.print(f"[red]Extractor skill not found at {extractor_script}[/red]")
             return
             
        console.print(f"[cyan]Invoking Extractor on {file_path}...[/cyan]")
        
        cmd = ["bash", str(extractor_script), file_path]
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode == 0:
            console.print("[green]Extraction Successful![/green]")
            console.print(result.stdout[:500] + "..." if len(result.stdout) > 500 else result.stdout)
            log_status("Retrieve done: extracted", status="DONE")
        else:
            console.print("[red]Extraction Failed:[/red]")
            console.print(result.stderr)
            log_status("Extraction failed", status="ERROR")

    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        log_status(f"Retrieve exception: {e}", status="ERROR")

if __name__ == "__main__":
    app()
