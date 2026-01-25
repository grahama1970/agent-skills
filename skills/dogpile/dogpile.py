#!/usr/bin/env python3
"""Dogpile: Comprehensive deep search aggregator.

Orchestrates searches across:
- Brave Search (Web)
- Perplexity (Deep Research)
- GitHub (Repos & Issues)
- ArXiv (Papers)
- YouTube (Videos)
"""
import json
import subprocess
import sys
import shutil
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed
import urllib.request

try:
    import typer
    from rich.console import Console
    from rich.markdown import Markdown
    from rich.panel import Panel
except ImportError:
    print("Missing requirements. Run: pip install typer rich", file=sys.stderr)
    sys.exit(1)

app = typer.Typer(help="Dogpile - Deep research aggregator")
console = Console()

SKILLS_DIR = Path(__file__).resolve().parents[1]

def run_command(cmd: List[str], cwd: Optional[Path] = None) -> str:
    """Run a command and return stdout."""
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=True,
            cwd=cwd
        )
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        return f"Error: {e.stderr}"
    except Exception as e:
        return f"Error: {e}"

def log_status(msg: str):
    """Log status to stderr."""
    # Use a distinct prefix for easier parsing by other agents
    sys.stderr.write(f"[DOGPILE-STATUS] {msg}\n")
    sys.stderr.flush()

def search_wayback(query: str) -> Dict[str, Any]:
    """Check Wayback Machine for snapshots if query is a URL."""
    # Simple URL heuristic
    if not (query.startswith("http://") or query.startswith("https://")):
        return {}

    api_url = f"http://archive.org/wayback/available?url={query}"
    try:
        with urllib.request.urlopen(api_url, timeout=10) as resp:
            data = json.loads(resp.read().decode())
            # Format: {"archived_snapshots": {"closest": {"available": true, "url": "...", ...}}}
            snapshots = data.get("archived_snapshots", {})
            closest = snapshots.get("closest", {})
            if closest.get("available"):
                return {
                    "available": True,
                    "url": closest.get("url"),
                    "timestamp": closest.get("timestamp")
                }
    except Exception as e:
        return {"error": str(e)}
    
    return {}

def search_brave(query: str) -> Dict[str, Any]:
    """Search Brave Web."""
    log_status(f"Starting Brave Search for '{query}'...")
    script = SKILLS_DIR / "brave-search" / "brave_search.py"
    cmd = [sys.executable, str(script), "web", query, "--count", "5", "--json"]
    try:
        output = run_command(cmd)
        log_status("Brave Search finished.")
        if output.startswith("Error:"):
            return {"error": output}
        return json.loads(output)
    except json.JSONDecodeError:
        return {"error": "Invalid JSON output from Brave", "raw": output}

def search_perplexity(query: str) -> Dict[str, Any]:
    """Search Perplexity."""
    log_status(f"Starting Perplexity Research for '{query}'...")
    script = SKILLS_DIR / "perplexity" / "perplexity.py"
    cmd = [sys.executable, str(script), "research", query, "--model", "sonar-reasoning", "--json"]
    try:
        output = run_command(cmd)
        log_status("Perplexity finished.")
        if output.startswith("Error:"):
            return {"error": output}
        return json.loads(output)
    except json.JSONDecodeError:
        return {"error": "Invalid JSON output from Perplexity", "raw": output}


def search_github(query: str) -> Dict[str, Any]:
    """Search GitHub Repos and Issues."""
    log_status(f"Starting GitHub Search for '{query}'...")
    if not shutil.which("gh"):
        return {"error": "GitHub CLI (gh) not installed"}
    
    repos_cmd = ["gh", "search", "repos", query, "--limit", "5", "--json", "fullName,html_url,description,stargazersCount"]
    issues_cmd = ["gh", "search", "issues", query, "--limit", "5", "--json", "title,html_url,state,repository"]
    
    repos_out = run_command(repos_cmd)
    issues_out = run_command(issues_cmd)
    log_status("GitHub Search finished.")
    
    results = {}
    try:
        if not repos_out.startswith("Error:"):
            results["repos"] = json.loads(repos_out)
        else:
            results["repos_error"] = repos_out
    except json.JSONDecodeError:
        results["repos_error"] = "Invalid JSON"

    try:
        if not issues_out.startswith("Error:"):
            results["issues"] = json.loads(issues_out)
        else:
            results["issues_error"] = issues_out
    except json.JSONDecodeError:
        results["issues_error"] = "Invalid JSON"
        
    return results

def search_arxiv(query: str) -> Dict[str, Any]:
    """Search ArXiv (Stage 1: Abstracts)."""
    log_status(f"Starting ArXiv Search (Stage 1: Abstracts) for '{query}'...")
    arxiv_dir = SKILLS_DIR / "arxiv"
    cmd = ["bash", "run.sh", "search", "-q", query, "-n", "10", "--json"]
    try:
        output = run_command(cmd, cwd=arxiv_dir)
        log_status("ArXiv Search (Stage 1) finished.")
        if output.startswith("Error:"):
            return {"error": output}
        return json.loads(output)
    except Exception as e:
        return {"error": str(e)}

def search_arxiv_details(paper_id: str) -> Dict[str, Any]:
    """Search ArXiv (Stage 2: Paper Details)."""
    log_status(f"Fetching ArXiv Paper Details for {paper_id}...")
    arxiv_dir = SKILLS_DIR / "arxiv"
    cmd = ["bash", "run.sh", "get", "-i", paper_id]
    try:
        output = run_command(cmd, cwd=arxiv_dir)
        log_status(f"ArXiv Details for {paper_id} finished.")
        if output.startswith("Error:"):
            return {"error": output}
        return json.loads(output)
    except Exception as e:
        return {"error": str(e)}

def search_youtube(query: str) -> List[Dict[str, str]]:
    """Search YouTube (Stage 1: Metadata)."""

    log_status(f"Starting YouTube Search for '{query}'...")
    if not shutil.which("yt-dlp"):
         return [{"title": "Error: yt-dlp not installed", "url": "", "id": "", "description": ""}]

    # yt-dlp search using JSON for robust parsing
    # Use --dump-json and NO --flat-playlist to get descriptions
    cmd = [
        "yt-dlp",
        "--dump-json",
        "--no-warnings",
        f"ytsearch5:{query}"
    ]
    output = run_command(cmd)
    log_status("YouTube Search finished.")
    
    if output.startswith("Error"):
         return [{"title": f"Error searching YouTube: {output}", "url": "", "id": "", "description": ""}]
    
    results = []
    # yt-dlp outputs one JSON object per line
    for line in output.splitlines():
        try:
            data = json.loads(line)
            desc = data.get("description") or "No description available."
            # Clean up newlines for display
            desc = desc.replace("\n", " ").strip()
            if len(desc) > 200:
                desc = desc[:197] + "..."
                
            results.append({
                "title": data.get("title", "Unknown Title"),
                "id": data.get("id", ""),
                "url": data.get("webpage_url") or data.get("url", ""),
                "description": desc
            })
        except json.JSONDecodeError:
            continue
            
    return results

def search_youtube_transcript(video_id: str) -> Dict[str, Any]:
    """Search YouTube (Stage 2: Transcript)."""
    log_status(f"Fetching YouTube Transcript for {video_id}...")
    skill_dir = SKILLS_DIR / "youtube-transcripts"
    cmd = [sys.executable, str(skill_dir / "youtube_transcript.py"), "get", "-i", video_id]
    try:
        output = run_command(cmd)
        log_status(f"YouTube Transcript for {video_id} finished.")
        if output.startswith("Error:"):
            return {"error": output}
        return json.loads(output)
    except Exception as e:
        return {"error": str(e)}

def search_codex_knowledge(query: str) -> str:
    """Use Codex as a direct source of technical knowledge."""
    log_status(f"Querying Codex Knowledge for '{query}'...")
    prompt = (
        f"Provide a high-reasoning technical overview and internal knowledge "
        f"about this topic: '{query}'. Focus on architectural patterns, "
        f"common pitfalls, and state-of-the-art approaches."
    )
    return search_codex(prompt)



def search_codex(prompt: str, schema: Optional[Path] = None) -> str:
    """Use high-reasoning Codex for analysis."""
    log_status("Consulting Codex for high-reasoning analysis...")
    script = SKILLS_DIR / "codex" / "run.sh"
    
    if schema:
        cmd = ["bash", str(script), "extract", prompt, "--schema", str(schema)]
    else:
        cmd = ["bash", str(script), "reason", prompt]
        
    output = run_command(cmd)
    log_status("Codex analysis finished.")
    return output

def analyze_query(query: str, interactive: bool) -> Tuple[str, bool]:

    """
    Analyze query for ambiguity and code-related intent.
    Returns: (query, is_code_related)
    Exits if ambiguous and interactive.
    """
    if not interactive:
        return query, True

    prompt = (
        f"Analyze this research query: '{query}'\n"
        "Assess if it is ambiguous and if it relates to software/coding."
    )
    
    schema_path = SKILLS_DIR / "codex" / "dogpile_schema.json"
    result_text = search_codex(prompt, schema=schema_path)
    
    if result_text.startswith("Error:"):
        log_status(f"Codex analysis failed: {result_text}")
        return query, True # Fail open

    try:
        # Codex CLI output-schema might contain some wrap text if we didn't use --json
        # However, our run_codex wrapper returns the output.
        # Let's try to extract JSON from the output in case there's noise.
        start = result_text.find("{")
        end = result_text.rfind("}")
        if start != -1 and end != -1:
            data = json.loads(result_text[start:end+1])
        else:
            data = json.loads(result_text)
        
        # Check Ambiguity
        if data.get("is_ambiguous"):
            clarifications = data.get("clarifications", [])
            if clarifications:
                output = {
                    "status": "ambiguous",
                    "query": query,
                    "clarifications": clarifications,
                    "message": "The query is ambiguous. Please ask the user these clarifying questions."
                }
                # Print JSON to stdout for agentic handoff
                print(json.dumps(output, indent=2))
                raise typer.Exit(code=0)
        
        return query, data.get("is_code_related", True)

    except json.JSONDecodeError as e:
        log_status(f"JSON decode failed for Codex output: {e}")
    except typer.Exit:
        raise
    except Exception as e:
        log_status(f"Unexpected error in query analysis: {e}")

    return query, True



def search_github_code(repo: str, query: str) -> List[Dict[str, Any]]:
    """Search for code within a specific repository."""
    if not shutil.which("gh"):
        return []
    
    # gh search code --repo owner/repo "query"
    cmd = ["gh", "search", "code", "--repo", repo, query, "--limit", "3", "--json", "path,repository,url"]
    output = run_command(cmd)
    
    try:
        if output.startswith("Error:"):
            # Code search might fail if not authenticated or other issues, just return empty
            return []
        return json.loads(output)
    except Exception:
        return []

def extract_target_repo(github_res: Dict[str, Any]) -> Optional[str]:
    """Heuristic to find the most relevant repository from search results."""
    # 1. Try top GitHub Repo result
    repos = github_res.get("repos", [])
    if repos and isinstance(repos, list) and len(repos) > 0:
        return repos[0].get("fullName")
    return None

@app.command()
def search(
    query: str = typer.Argument(..., help="Search query"),
    interactive: bool = typer.Option(True, "--interactive/--no-interactive", help="Enable ambiguity/intent check"),
):
    """Aggregate search results from multiple sources."""
    
    # 1. Analyze Query (Ambiguity + Intent)
    query, is_code_related = analyze_query(query, interactive)

    console.print(f"[bold blue]Dogpiling on:[/bold blue] {query} (Code Related: {is_code_related})...")

    # Stage 1: Broad Search
    with ThreadPoolExecutor(max_workers=7) as executor:
        future_brave = executor.submit(search_brave, query)
        future_perplexity = executor.submit(search_perplexity, query)
        future_github = executor.submit(search_github, query)
        future_arxiv = executor.submit(search_arxiv, query)
        future_youtube = executor.submit(search_youtube, query)
        future_wayback = executor.submit(search_wayback, query)
        future_codex_src = executor.submit(search_codex_knowledge, query)

        # Collect results
        brave_res = future_brave.result()
        perp_res = future_perplexity.result()
        github_res = future_github.result()
        arxiv_res = future_arxiv.result()
        youtube_res = future_youtube.result()
        wayback_res = future_wayback.result()
        codex_src_res = future_codex_src.result()

    # Stage 2: Deep Dive
    # 2.1 GitHub Code Search
    target_repo = extract_target_repo(github_res)
    deep_code_res = []
    if is_code_related and target_repo:
        console.print(f"[bold magenta]Deep Dive:[/bold magenta] Analyzing target repo '{target_repo}'...")
        log_status(f"Starting GitHub Deep Code Search in {target_repo}...")
        with ThreadPoolExecutor(max_workers=2) as executor:
            future_code = executor.submit(search_github_code, target_repo, query)
            deep_code_res = future_code.result()
        log_status(f"GitHub Deep Code Search in {target_repo} finished.")


    # 2.2 ArXiv Two-Stage (Paper Details)
    arxiv_details = []
    if isinstance(arxiv_res, dict) and "items" in arxiv_res:
        valid_papers = arxiv_res["items"][:2] # Limit to top 2 for speed
        if valid_papers:
            log_status(f"ArXiv Stage 2: Fetching details for {len(valid_papers)} papers...")
            with ThreadPoolExecutor(max_workers=2) as executor:
                futures = {executor.submit(search_arxiv_details, p["id"]): p for p in valid_papers}
                for f in as_completed(futures):
                    res = f.result()
                    if "items" in res and res["items"]:
                        arxiv_details.append(res["items"][0])

    # 2.3 YouTube Two-Stage (Transcripts)
    youtube_transcripts = []
    if youtube_res:
        valid_videos = [v for v in youtube_res if v.get("id")][:2]
        if valid_videos:
            log_status(f"YouTube Stage 2: Fetching transcripts for {len(valid_videos)} videos...")
            with ThreadPoolExecutor(max_workers=2) as executor:
                futures = {executor.submit(search_youtube_transcript, v["id"]): v for v in valid_videos}
                for f in as_completed(futures):
                    res = f.result()
                    if "full_text" in res:
                        res["title"] = futures[f]["title"]
                        res["url"] = futures[f]["url"]
                        youtube_transcripts.append(res)


    # --- GLUE THE REPORT ---
    md_lines = [f"# Dogpile Report: {query}", ""]
    
    # 0. Wayback (Top if available)
    if wayback_res.get("available"):
        md_lines.append(f"> 🏛️ **Wayback Machine**: [Snapshot available]({wayback_res['url']}) (Timestamp: {wayback_res.get('timestamp')})")
        md_lines.append("")
    elif "error" in wayback_res:
         md_lines.append(f"> 🏛️ Wayback Error: {wayback_res['error']}")
         md_lines.append("")

    # 1. Codex Knowledge (Starting Point)
    md_lines.append("## 🤖 Codex Technical Overview")
    if not codex_src_res.startswith("Error:"):
        md_lines.append(codex_src_res)
    else:
        md_lines.append(f"> Error: {codex_src_res}")
    md_lines.append("")

    # 2. Perplexity (Summary)
    md_lines.append("## 🧠 AI Research (Perplexity)")
    if "error" in perp_res:
         md_lines.append(f"> Error: {perp_res['error']}")
    else:
        md_lines.append(perp_res.get("answer", "No answer."))
        if perp_res.get("citations"):
            md_lines.append("\n**Citations:**")
            for cite in perp_res.get("citations", []):
                md_lines.append(f"- {cite}")
    md_lines.append("")

    # 3. GitHub & Code Deep Dive
    md_lines.append("## OCTOCAT GitHub")
    if "error" in github_res:
        md_lines.append(f"> Error: {github_res['error']}")
    else:
        md_lines.append("### Repositories")
        repos = github_res.get("repos", [])
        if not repos:
            md_lines.append("No repositories found.")
        elif isinstance(repos, list):
            for i, repo in enumerate(repos):
                desc = repo.get("description", "No description") or "No description"
                star = f"⭐ {repo.get('stargazersCount', 0)}"
                prefix = "🎯 **TARGET**" if repo.get("fullName") == target_repo else "-"
                
                md_lines.append(f"{prefix} **[{repo.get('fullName')}]({repo.get('html_url')})** ({star})")
                md_lines.append(f"  {desc}")
        
        if deep_code_res:
            md_lines.append(f"\n### 🔍 Code Matches in {target_repo}")
            for item in deep_code_res:
                md_lines.append(f"- [`{item.get('path')}`]({item.get('url')})")

        md_lines.append("\n### Issues/Discussions")
        issues = github_res.get("issues", [])
        if not issues:
             md_lines.append("No issues found.")
        elif isinstance(issues, list):
            for issue in issues:
                repo_name = issue.get("repository", {}).get("nameWithOwner", "unknown")
                md_lines.append(f"- **{repo_name}**: [{issue.get('title')}]({issue.get('html_url')}) ({issue.get('state')})")
    md_lines.append("")

    # 4. Brave (Web)
    md_lines.append("## 🌐 Web Results (Brave)")
    if "error" in brave_res:
         md_lines.append(f"> Error: {brave_res['error']}")
    else:
        for item in brave_res.get("results", [])[:5]:
            md_lines.append(f"- **[{item.get('title', 'No Title')}]({item.get('url', '#')})**")
            md_lines.append(f"  {item.get('description', '')}")
    md_lines.append("")

    # 5. ArXiv
    md_lines.append("## 📄 Academic Papers (ArXiv)")
    if arxiv_details:
        md_lines.append("### Deep Dive: Paper Details")
        for paper in arxiv_details:
            md_lines.append(f"#### [{paper.get('title')}]({paper.get('abs_url')})")
            md_lines.append(f"**Authors:** {', '.join(paper.get('authors', []))}")
            abstract = paper.get("abstract", "")
            if len(abstract) > 500:
                abstract = abstract[:500] + "..."
            md_lines.append(f"**Summary:** {abstract}")
            md_lines.append("")
        
        md_lines.append("### Other Relevant Papers")
    
    if isinstance(arxiv_res, dict) and "items" in arxiv_res:
        for p in arxiv_res["items"][len(arxiv_details):len(arxiv_details)+5]:
            md_lines.append(f"- **[{p.get('title')}]({p.get('abs_url')})** ({p.get('published')})")
    elif isinstance(arxiv_res, str):
        md_lines.append(arxiv_res)
    md_lines.append("")

    # 6. YouTube
    md_lines.append("## 📺 Videos (YouTube)")
    if youtube_transcripts:
        md_lines.append("### Video Insights (Transcripts)")
        for trans in youtube_transcripts:
            md_lines.append(f"#### [{trans.get('title')}]({trans.get('url')})")
            text = trans.get("full_text", "")
            if len(text) > 800:
                text = text[:800] + "..."
            md_lines.append(f"> {text}")
            md_lines.append("")
            
        md_lines.append("### More Videos")

    if not youtube_res:
        md_lines.append("No videos found or error.")
    else:
        for i, video in enumerate(youtube_res[len(youtube_transcripts):len(youtube_transcripts)+5]):
             if "Error" in video.get("title", ""):
                 md_lines.append(f"> {video['title']}")
             else:
                 md_lines.append(f"- **[{video['title']}]({video['url']})**")
                 if video.get("description"):
                     md_lines.append(f"  _{video.get('description')}_")
    md_lines.append("")

    # Synthesis (Codex High Reasoning)
    log_status("Starting Codex Synthesis...")
    console.print("\n[bold cyan]Synthesizing report via Codex (gpt-5.2 High Reasoning)...[/bold cyan]")

    synthesis_prompt = (
        f"Synthesize the following research results for the query '{query}' into a concise, "
        f"high-reasoning conclusion. Highlight unique insights from any source (GitHub, ArXiv, Web).\n\n"
        f"RESULTS:\n" + "\n".join(md_lines)
    )
    synthesis = search_codex(synthesis_prompt)
    if not synthesis.startswith("Error:"):
        md_lines.append("## 🔬 Codex Synthesis (gpt-5.2 High Reasoning)")
        md_lines.append(synthesis)
        md_lines.append("")
        log_status("Codex Synthesis finished.")
    else:
        log_status("Codex Synthesis failed.")

    
    # Print the report
    console.print(Markdown("\n".join(md_lines)))


@app.command()
def version():
    """Show version."""
    console.print("Dogpile v0.2.0")

if __name__ == "__main__":
    app()
