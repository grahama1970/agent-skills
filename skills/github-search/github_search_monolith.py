#!/usr/bin/env python3
"""GitHub Search: Deep multi-strategy search for repositories and code.

Features:
- Multi-strategy code search (basic, symbol, path-filtered)
- Repository analysis with README and metadata
- Full file content fetching
- Issue and PR search
- Agent-driven relevance evaluation

Reference: https://docs.github.com/en/search-github/github-code-search/understanding-github-code-search-syntax
"""
import json
import subprocess
import sys
import shutil
import base64
import re
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed

try:
    import typer
    from rich.console import Console
    from rich.markdown import Markdown
    from rich.table import Table
except ImportError:
    print("Missing requirements. Run: pip install typer rich", file=sys.stderr)
    sys.exit(1)

app = typer.Typer(help="GitHub Search - Deep multi-strategy search")
console = Console()

SKILLS_DIR = Path(__file__).resolve().parents[1]


def run_command(cmd: List[str], cwd: Optional[Path] = None, timeout: int = 60) -> str:
    """Run a command and return stdout."""
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=True,
            cwd=cwd,
            timeout=timeout
        )
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        return f"Error: {e.stderr}"
    except subprocess.TimeoutExpired:
        return "Error: Command timed out"
    except Exception as e:
        return f"Error: {e}"


# =============================================================================
# Skill Integration Paths
# =============================================================================

TREESITTER_SKILL = SKILLS_DIR / "treesitter"
TAXONOMY_SKILL = SKILLS_DIR / "taxonomy"


def check_gh_cli() -> bool:
    """Check if gh CLI is installed and authenticated."""
    if not shutil.which("gh"):
        return False
    # Check auth status
    result = run_command(["gh", "auth", "status"])
    return not result.startswith("Error:")


# =============================================================================
# Core Search Functions
# =============================================================================

def search_repos(query: str, limit: int = 5, language: str = None) -> Dict[str, Any]:
    """
    Search GitHub repositories.

    Args:
        query: Search query
        limit: Max results (default 5)
        language: Filter by programming language

    Returns:
        Dict with repos list and metadata
    """
    cmd = [
        "gh", "search", "repos", query,
        "--limit", str(limit),
        "--json", "fullName,description,stargazersCount,url,language,updatedAt,forksCount"
    ]
    if language:
        cmd.extend(["--language", language])

    output = run_command(cmd)

    if output.startswith("Error:"):
        return {"error": output, "repos": []}

    try:
        repos = json.loads(output)
        return {"repos": repos, "count": len(repos)}
    except json.JSONDecodeError:
        return {"error": "Invalid JSON response", "repos": []}


def search_issues(query: str, limit: int = 5, state: str = None, repo: str = None) -> Dict[str, Any]:
    """
    Search GitHub issues and discussions.

    Args:
        query: Search query
        limit: Max results
        state: Filter by state (open, closed)
        repo: Filter by repository (owner/repo)
    """
    cmd = [
        "gh", "search", "issues", query,
        "--limit", str(limit),
        "--json", "title,url,state,repository,createdAt,author,labels"
    ]
    if state:
        cmd.extend(["--state", state])
    if repo:
        cmd.extend(["--repo", repo])

    output = run_command(cmd)

    if output.startswith("Error:"):
        return {"error": output, "issues": []}

    try:
        issues = json.loads(output)
        return {"issues": issues, "count": len(issues)}
    except json.JSONDecodeError:
        return {"error": "Invalid JSON response", "issues": []}


def search_code_basic(query: str, repo: str = None, language: str = None, limit: int = 5) -> List[Dict[str, Any]]:
    """
    Basic code search with text matching.

    Args:
        query: Search query
        repo: Specific repository (owner/repo)
        language: Filter by language
        limit: Max results
    """
    cmd = ["gh", "search", "code", query, "--limit", str(limit), "--json", "path,repository,url,textMatches"]
    if repo:
        cmd.extend(["--repo", repo])
    if language:
        cmd.extend(["--language", language])

    output = run_command(cmd)

    if output.startswith("Error:"):
        return []

    try:
        return json.loads(output)
    except json.JSONDecodeError:
        return []


def search_code_symbols(repo: str, symbols: List[str], language: str = None) -> List[Dict[str, Any]]:
    """
    Search for symbol definitions using the symbol: qualifier.

    Uses tree-sitter parsing to find actual function/class definitions,
    not just text matches.

    Reference: https://docs.github.com/en/search-github/github-code-search/understanding-github-code-search-syntax

    Args:
        repo: Repository to search (owner/repo)
        symbols: List of symbol names to find
        language: Filter by language
    """
    results = []

    for symbol in symbols[:5]:  # Limit to avoid rate limits
        query = f"symbol:{symbol}"
        cmd = ["gh", "search", "code", "--repo", repo, query, "--limit", "3", "--json", "path,repository,url,textMatches"]
        if language:
            cmd.extend(["--language", language])

        output = run_command(cmd)

        try:
            if not output.startswith("Error:"):
                matches = json.loads(output)
                for m in matches:
                    m["symbol"] = symbol
                    m["search_type"] = "definition"
                results.extend(matches)
        except json.JSONDecodeError:
            continue

    return results


def search_code_by_path(repo: str, query: str, paths: List[str], language: str = None) -> List[Dict[str, Any]]:
    """
    Search code in specific directories using the path: qualifier.

    Args:
        repo: Repository to search
        query: Search query
        paths: List of paths to search in (e.g., ["src/", "lib/"])
        language: Filter by language
    """
    results = []

    for path in paths[:4]:  # Limit paths
        full_query = f"{query} path:{path}"
        cmd = ["gh", "search", "code", "--repo", repo, full_query, "--limit", "3", "--json", "path,repository,url,textMatches"]
        if language:
            cmd.extend(["--language", language])

        output = run_command(cmd)

        try:
            if not output.startswith("Error:"):
                matches = json.loads(output)
                for m in matches:
                    m["searched_path"] = path
                results.extend(matches)
        except json.JSONDecodeError:
            continue

    return results


def search_code_by_filename(repo: str, filenames: List[str], language: str = None) -> List[Dict[str, Any]]:
    """
    Search for specific files using the filename: qualifier.

    Args:
        repo: Repository to search
        filenames: List of filenames to find (e.g., ["config.py", "settings.json"])
        language: Filter by language
    """
    results = []

    for filename in filenames[:5]:
        cmd = ["gh", "search", "code", "--repo", repo, f"filename:{filename}", "--limit", "3", "--json", "path,repository,url"]
        if language:
            cmd.extend(["--language", language])

        output = run_command(cmd)

        try:
            if not output.startswith("Error:"):
                matches = json.loads(output)
                for m in matches:
                    m["searched_filename"] = filename
                results.extend(matches)
        except json.JSONDecodeError:
            continue

    return results


# =============================================================================
# Repository Analysis Functions
# =============================================================================

def fetch_repo_metadata(repo: str) -> Dict[str, Any]:
    """
    Fetch comprehensive repository metadata.

    Args:
        repo: Repository (owner/repo)
    """
    cmd = [
        "gh", "repo", "view", repo, "--json",
        "name,owner,description,url,stargazerCount,forkCount,primaryLanguage,"
        "repositoryTopics,updatedAt,createdAt,isArchived,licenseInfo,defaultBranchRef"
    ]

    output = run_command(cmd)

    if output.startswith("Error:"):
        return {"error": output}

    try:
        return json.loads(output)
    except json.JSONDecodeError:
        return {"error": "Invalid JSON response"}


def fetch_repo_readme(repo: str) -> Dict[str, Any]:
    """
    Fetch repository README content.

    Args:
        repo: Repository (owner/repo)

    Returns:
        Dict with readme content and metadata
    """
    cmd = ["gh", "api", f"repos/{repo}/readme", "--jq", ".content,.name,.size"]
    output = run_command(cmd)

    if output.startswith("Error:"):
        return {"error": output, "content": ""}

    try:
        lines = output.strip().split('\n')
        if len(lines) >= 1:
            content_b64 = lines[0]
            content = base64.b64decode(content_b64).decode('utf-8', errors='ignore')
            return {
                "content": content,
                "name": lines[1] if len(lines) > 1 else "README.md",
                "size": int(lines[2]) if len(lines) > 2 else len(content)
            }
    except Exception as e:
        return {"error": str(e), "content": ""}

    return {"error": "Failed to parse", "content": ""}


def fetch_repo_languages(repo: str) -> Dict[str, int]:
    """
    Fetch repository language breakdown.

    Args:
        repo: Repository (owner/repo)

    Returns:
        Dict of {language: bytes}
    """
    cmd = ["gh", "api", f"repos/{repo}/languages"]
    output = run_command(cmd)

    if output.startswith("Error:"):
        return {}

    try:
        return json.loads(output)
    except json.JSONDecodeError:
        return {}


def fetch_repo_tree(repo: str, path: str = "") -> List[Dict[str, Any]]:
    """
    Fetch repository file tree.

    Args:
        repo: Repository (owner/repo)
        path: Subdirectory path (empty for root)

    Returns:
        List of {name, type, path, size} entries
    """
    api_path = f"repos/{repo}/contents/{path}" if path else f"repos/{repo}/contents"
    cmd = ["gh", "api", api_path]
    output = run_command(cmd)

    if output.startswith("Error:"):
        return []

    try:
        items = json.loads(output)
        return [{"name": i["name"], "type": i["type"], "path": i["path"], "size": i.get("size", 0)} for i in items]
    except (json.JSONDecodeError, KeyError):
        return []


def fetch_file_content(repo: str, file_path: str, max_size: int = 10000) -> Dict[str, Any]:
    """
    Fetch full file content from a repository.

    Args:
        repo: Repository (owner/repo)
        file_path: Path to file within repo
        max_size: Max content size to return (truncates if larger)

    Returns:
        Dict with content, size, truncated flag
    """
    cmd = ["gh", "api", f"repos/{repo}/contents/{file_path}", "--jq", ".content,.size,.sha"]
    output = run_command(cmd)

    if output.startswith("Error:"):
        return {"error": output, "path": file_path}

    try:
        lines = output.strip().split('\n')
        if len(lines) >= 2:
            content_b64 = lines[0]
            size = int(lines[1]) if len(lines) > 1 else 0

            content = base64.b64decode(content_b64).decode('utf-8', errors='ignore')
            truncated = len(content) > max_size

            return {
                "path": file_path,
                "content": content[:max_size] if truncated else content,
                "size": size,
                "truncated": truncated
            }
    except Exception as e:
        return {"error": str(e), "path": file_path}

    return {"error": "Failed to parse", "path": file_path}


# =============================================================================
# Skill Integrations (treesitter, taxonomy)
# =============================================================================

def parse_with_treesitter(content: str, language: str) -> Dict[str, Any]:
    """
    Parse code content with treesitter to extract symbols.

    Uses the /treesitter skill to get function/class definitions with
    line numbers and source code.

    Args:
        content: Code content to parse
        language: Programming language (python, javascript, etc.)

    Returns:
        Dict with symbols list or error
    """
    if not TREESITTER_SKILL.exists():
        return {"error": "treesitter skill not found", "symbols": []}

    import tempfile
    import os

    # Write content to temp file
    suffix = {
        "python": ".py", "javascript": ".js", "typescript": ".ts",
        "go": ".go", "rust": ".rs", "java": ".java", "ruby": ".rb",
        "c": ".c", "cpp": ".cpp"
    }.get(language.lower(), ".txt")

    try:
        with tempfile.NamedTemporaryFile(mode='w', suffix=suffix, delete=False) as f:
            f.write(content)
            temp_path = f.name

        cmd = ["bash", "run.sh", "symbols", temp_path, "--content", "--json"]
        output = run_command(cmd, cwd=TREESITTER_SKILL, timeout=30)

        os.unlink(temp_path)

        if output.startswith("Error:"):
            return {"error": output, "symbols": []}

        return json.loads(output)

    except Exception as e:
        return {"error": str(e), "symbols": []}


def classify_with_taxonomy(text: str, collection: str = "operational") -> Dict[str, Any]:
    """
    Classify text with taxonomy to extract bridge tags.

    Uses the /taxonomy skill to get:
    - Bridge tags (Precision, Resilience, Fragility, etc.)
    - Collection-specific tags
    - worth_remembering assessment

    Args:
        text: Text to classify (README, code, etc.)
        collection: Taxonomy collection (operational, lore, sparta)

    Returns:
        Dict with bridge_tags, collection_tags, worth_remembering
    """
    if not TAXONOMY_SKILL.exists():
        return {"error": "taxonomy skill not found", "bridge_tags": []}

    cmd = ["bash", "run.sh", "--text", text[:5000], "--collection", collection, "--json"]
    output = run_command(cmd, cwd=TAXONOMY_SKILL, timeout=30)

    if output.startswith("Error:"):
        return {"error": output, "bridge_tags": []}

    try:
        # Find JSON in output
        start = output.find('{')
        end = output.rfind('}')
        if start != -1 and end != -1:
            return json.loads(output[start:end+1])
        return json.loads(output)
    except json.JSONDecodeError:
        return {"error": "Invalid JSON from taxonomy", "bridge_tags": []}


def enhance_file_with_treesitter(file_result: Dict[str, Any], language: str = None) -> Dict[str, Any]:
    """
    Enhance a fetched file result with treesitter symbol extraction.

    Args:
        file_result: Result from fetch_file_content
        language: Override language detection

    Returns:
        Enhanced file result with symbols
    """
    if file_result.get("error") or not file_result.get("content"):
        return file_result

    # Detect language from path if not provided
    if not language:
        path = file_result.get("path", "")
        ext = path.split('.')[-1] if '.' in path else ""
        language = {
            "py": "python", "js": "javascript", "ts": "typescript",
            "go": "go", "rs": "rust", "java": "java", "rb": "ruby",
            "c": "c", "cpp": "cpp", "cc": "cpp"
        }.get(ext, "")

    if language:
        symbols = parse_with_treesitter(file_result["content"], language)
        file_result["symbols"] = symbols.get("symbols", [])
        file_result["language"] = language

    return file_result


def classify_repo(repo_analysis: Dict[str, Any]) -> Dict[str, Any]:
    """
    Classify a repository using taxonomy based on README and metadata.

    Args:
        repo_analysis: Result from deep_repo_analysis

    Returns:
        Taxonomy classification result
    """
    # Build text from README and description
    text_parts = []

    readme = repo_analysis.get("readme", {})
    if readme.get("content"):
        text_parts.append(readme["content"][:3000])

    meta = repo_analysis.get("metadata", {})
    if meta.get("description"):
        text_parts.append(meta["description"])

    topics = meta.get("repositoryTopics", [])
    if topics:
        topic_names = [t.get("name", "") for t in topics]
        text_parts.append(f"Topics: {', '.join(topic_names)}")

    if not text_parts:
        return {"error": "No content to classify", "bridge_tags": []}

    full_text = "\n\n".join(text_parts)
    return classify_with_taxonomy(full_text, "operational")


# =============================================================================
# High-Level Search Functions
# =============================================================================

def extract_search_terms(query: str) -> Dict[str, List[str]]:
    """
    Extract potential symbols, keywords, and paths from a search query.

    Returns:
        Dict with symbols, keywords, paths, filenames
    """
    result = {
        "symbols": [],
        "keywords": [],
        "paths": ["src/", "lib/", "core/", "pkg/", "internal/"],
        "filenames": []
    }

    words = query.split()
    for word in words:
        # CamelCase or PascalCase -> likely a class/type name
        if re.match(r'^[A-Z][a-zA-Z0-9]*$', word):
            result["symbols"].append(word)
        # snake_case with underscores -> likely a function name
        elif re.match(r'^[a-z][a-z0-9_]+$', word) and '_' in word:
            result["symbols"].append(word)
        # camelCase -> likely a function/method name
        elif re.match(r'^[a-z][a-zA-Z0-9]+$', word) and any(c.isupper() for c in word):
            result["symbols"].append(word)
        # Filename pattern
        elif '.' in word and not word.startswith('http'):
            result["filenames"].append(word)
        else:
            result["keywords"].append(word)

    return result


def deep_repo_analysis(repo: str) -> Dict[str, Any]:
    """
    Comprehensive repository analysis.

    Fetches:
    - Metadata (stars, language, topics)
    - README content
    - Language breakdown
    - File tree

    Args:
        repo: Repository (owner/repo)

    Returns:
        Dict with all analysis results
    """
    result = {
        "repo": repo,
        "metadata": {},
        "readme": {},
        "languages": {},
        "tree": []
    }

    # Fetch all in parallel
    with ThreadPoolExecutor(max_workers=4) as executor:
        future_meta = executor.submit(fetch_repo_metadata, repo)
        future_readme = executor.submit(fetch_repo_readme, repo)
        future_langs = executor.submit(fetch_repo_languages, repo)
        future_tree = executor.submit(fetch_repo_tree, repo)

        result["metadata"] = future_meta.result()
        result["readme"] = future_readme.result()
        result["languages"] = future_langs.result()
        result["tree"] = future_tree.result()

    return result


def multi_strategy_code_search(
    repo: str,
    query: str,
    language: str = None,
    fetch_files: bool = True,
    use_treesitter: bool = False
) -> Dict[str, Any]:
    """
    Multi-strategy deep code search within a repository.

    Strategies:
    1. Basic text search
    2. Symbol search (function/class definitions)
    3. Path-filtered search (src/, lib/, etc.)
    4. Full file content fetch for top matches
    5. Optional treesitter parsing for deeper symbol extraction

    Args:
        repo: Repository to search
        query: Search query
        language: Filter by language
        fetch_files: Whether to fetch full file contents
        use_treesitter: Parse fetched files with treesitter for symbols

    Returns:
        Dict with results from all strategies
    """
    result = {
        "repo": repo,
        "language": language,
        "basic_matches": [],
        "symbol_matches": [],
        "path_matches": [],
        "file_contents": []
    }

    # Extract search terms
    terms = extract_search_terms(query)

    # Run searches in parallel
    with ThreadPoolExecutor(max_workers=3) as executor:
        future_basic = executor.submit(search_code_basic, query, repo, language, 5)
        future_symbols = executor.submit(
            search_code_symbols, repo, terms["symbols"], language
        ) if terms["symbols"] else None
        future_paths = executor.submit(
            search_code_by_path, repo,
            " ".join(terms["keywords"]) if terms["keywords"] else query,
            terms["paths"], language
        )

        result["basic_matches"] = future_basic.result()
        if future_symbols:
            result["symbol_matches"] = future_symbols.result()
        result["path_matches"] = future_paths.result()

    # Fetch full content of top matches
    if fetch_files:
        all_paths = set()
        for match in result["basic_matches"][:2]:
            if match.get("path"):
                all_paths.add(match["path"])
        for match in result["symbol_matches"][:2]:
            if match.get("path"):
                all_paths.add(match["path"])

        for path in list(all_paths)[:3]:
            content = fetch_file_content(repo, path)
            if not content.get("error"):
                # Optionally enhance with treesitter parsing
                if use_treesitter:
                    content = enhance_file_with_treesitter(content, language)
                result["file_contents"].append(content)

    return result


def search_and_analyze(
    query: str,
    top_repos: int = 3,
    deep_search: bool = True,
    use_treesitter: bool = False,
    use_taxonomy: bool = False
) -> Dict[str, Any]:
    """
    Full search pipeline: find repos, analyze, and search code.

    This is the main entry point for comprehensive GitHub research.

    Args:
        query: Search query
        top_repos: Number of top repos to analyze
        deep_search: Whether to do deep code search in top repo
        use_treesitter: Parse fetched files with treesitter
        use_taxonomy: Classify repos with taxonomy

    Returns:
        Dict with repos, analysis, and code search results
    """
    result = {
        "query": query,
        "repos": [],
        "issues": [],
        "top_repo_analysis": None,
        "code_search": None,
        "taxonomy": None
    }

    # Stage 1: Search repos and issues
    with ThreadPoolExecutor(max_workers=2) as executor:
        future_repos = executor.submit(search_repos, query, top_repos + 2)
        future_issues = executor.submit(search_issues, query, 5)

        repos_result = future_repos.result()
        issues_result = future_issues.result()

        result["repos"] = repos_result.get("repos", [])
        result["issues"] = issues_result.get("issues", [])

    if not result["repos"]:
        return result

    # Stage 2: Analyze top repos
    top_repo = result["repos"][0]["fullName"]
    result["top_repo_analysis"] = deep_repo_analysis(top_repo)

    # Stage 3: Deep code search in top repo
    if deep_search:
        language = None
        if result["top_repo_analysis"]["metadata"].get("primaryLanguage"):
            language = result["top_repo_analysis"]["metadata"]["primaryLanguage"].get("name")

        result["code_search"] = multi_strategy_code_search(
            top_repo, query, language,
            fetch_files=True,
            use_treesitter=use_treesitter
        )

    # Stage 4: Taxonomy classification
    if use_taxonomy and result["top_repo_analysis"]:
        result["taxonomy"] = classify_repo(result["top_repo_analysis"])

    return result


# =============================================================================
# CLI Commands
# =============================================================================

@app.command()
def search(
    query: str = typer.Argument(..., help="Search query"),
    limit: int = typer.Option(5, "--limit", "-n", help="Max repositories to return"),
    language: str = typer.Option(None, "--language", "-l", help="Filter by language"),
    deep: bool = typer.Option(False, "--deep", "-d", help="Deep analysis of top repo"),
    treesitter: bool = typer.Option(False, "--treesitter", "-t", help="Parse files with treesitter"),
    taxonomy: bool = typer.Option(False, "--taxonomy", help="Classify repos with taxonomy"),
    json_output: bool = typer.Option(False, "--json", "-j", help="Output as JSON")
):
    """Search GitHub repositories and optionally analyze the top result."""
    if not check_gh_cli():
        console.print("[red]Error: gh CLI not installed or not authenticated[/red]")
        console.print("Run: gh auth login")
        raise typer.Exit(1)

    if deep:
        result = search_and_analyze(
            query, limit, deep_search=True,
            use_treesitter=treesitter,
            use_taxonomy=taxonomy
        )
    else:
        result = search_repos(query, limit, language)

    if json_output:
        print(json.dumps(result, indent=2, default=str))
        return

    # Display results
    if deep:
        console.print(f"\n[bold blue]GitHub Deep Search:[/bold blue] {query}\n")

        # Repos
        console.print("[bold]Repositories:[/bold]")
        for repo in result.get("repos", [])[:5]:
            stars = repo.get("stargazersCount", 0)
            # Handle both formats: "language" (string from search) and "primaryLanguage" (object from view)
            lang = repo.get("language") or repo.get("primaryLanguage", {})
            lang_name = lang.get("name", lang) if isinstance(lang, dict) else (lang or "Unknown")
            console.print(f"  - [{repo['fullName']}]({repo['url']}) ({stars} stars, {lang_name})")
            if repo.get("description"):
                console.print(f"    {repo['description'][:80]}...")

        # Top repo analysis
        if result.get("top_repo_analysis"):
            analysis = result["top_repo_analysis"]
            console.print(f"\n[bold]Top Repo Analysis: {analysis['repo']}[/bold]")

            readme = analysis.get("readme", {})
            if readme.get("content"):
                console.print(f"  README: {len(readme['content'])} chars")

            langs = analysis.get("languages", {})
            if langs:
                total = sum(langs.values())
                top = sorted(langs.items(), key=lambda x: x[1], reverse=True)[:3]
                lang_str = ", ".join([f"{l[0]}: {l[1]*100/total:.1f}%" for l in top])
                console.print(f"  Languages: {lang_str}")

        # Code search
        if result.get("code_search"):
            cs = result["code_search"]
            console.print(f"\n[bold]Code Search Results:[/bold]")
            console.print(f"  Basic matches: {len(cs.get('basic_matches', []))}")
            console.print(f"  Symbol matches: {len(cs.get('symbol_matches', []))}")
            console.print(f"  Path matches: {len(cs.get('path_matches', []))}")
            console.print(f"  Files fetched: {len(cs.get('file_contents', []))}")
    else:
        console.print(f"\n[bold blue]GitHub Repos:[/bold blue] {query}\n")
        for repo in result.get("repos", []):
            stars = repo.get("stargazersCount", 0)
            console.print(f"  - {repo['fullName']} ({stars} stars)")


@app.command()
def repo(
    repository: str = typer.Argument(..., help="Repository (owner/repo)"),
    json_output: bool = typer.Option(False, "--json", "-j", help="Output as JSON")
):
    """Analyze a specific repository in depth."""
    if not check_gh_cli():
        console.print("[red]Error: gh CLI not installed or not authenticated[/red]")
        raise typer.Exit(1)

    result = deep_repo_analysis(repository)

    if json_output:
        print(json.dumps(result, indent=2, default=str))
        return

    console.print(f"\n[bold blue]Repository Analysis:[/bold blue] {repository}\n")

    meta = result.get("metadata", {})
    if meta and not meta.get("error"):
        console.print(f"[bold]Description:[/bold] {meta.get('description', 'N/A')}")
        console.print(f"[bold]Stars:[/bold] {meta.get('stargazerCount', 0)}")
        console.print(f"[bold]Forks:[/bold] {meta.get('forkCount', 0)}")

        lang = meta.get("primaryLanguage", {})
        console.print(f"[bold]Language:[/bold] {lang.get('name', 'Unknown') if lang else 'Unknown'}")

        topics = meta.get("repositoryTopics", [])
        if topics:
            topic_names = [t.get("name", "") for t in topics]
            console.print(f"[bold]Topics:[/bold] {', '.join(topic_names)}")

    langs = result.get("languages", {})
    if langs:
        total = sum(langs.values())
        console.print("\n[bold]Language Breakdown:[/bold]")
        for lang, bytes_count in sorted(langs.items(), key=lambda x: x[1], reverse=True)[:5]:
            pct = bytes_count * 100 / total
            console.print(f"  {lang}: {pct:.1f}%")

    tree = result.get("tree", [])
    if tree:
        console.print("\n[bold]File Structure:[/bold]")
        for item in tree[:15]:
            icon = "[dir]" if item["type"] == "dir" else "[file]"
            console.print(f"  {icon} {item['name']}")


@app.command()
def code(
    query: str = typer.Argument(..., help="Search query"),
    repository: str = typer.Option(None, "--repo", "-r", help="Specific repository"),
    symbol: str = typer.Option(None, "--symbol", "-s", help="Search for symbol definition"),
    path: str = typer.Option(None, "--path", "-p", help="Search in specific path"),
    language: str = typer.Option(None, "--language", "-l", help="Filter by language"),
    limit: int = typer.Option(5, "--limit", "-n", help="Max results"),
    json_output: bool = typer.Option(False, "--json", "-j", help="Output as JSON")
):
    """Search code with advanced qualifiers (symbol:, path:, language:)."""
    if not check_gh_cli():
        console.print("[red]Error: gh CLI not installed or not authenticated[/red]")
        raise typer.Exit(1)

    results = []

    if symbol and repository:
        # Symbol search
        results = search_code_symbols(repository, [symbol], language)
    elif path and repository:
        # Path-filtered search
        results = search_code_by_path(repository, query, [path], language)
    elif repository:
        # Multi-strategy search in repo
        search_result = multi_strategy_code_search(repository, query, language, fetch_files=False)
        results = search_result.get("basic_matches", []) + search_result.get("symbol_matches", [])
    else:
        # Global code search
        results = search_code_basic(query, None, language, limit)

    if json_output:
        print(json.dumps(results, indent=2, default=str))
        return

    console.print(f"\n[bold blue]Code Search:[/bold blue] {query}\n")

    if not results:
        console.print("No results found.")
        return

    for item in results[:limit]:
        repo_name = item.get("repository", {}).get("fullName", "unknown")
        path = item.get("path", "unknown")
        url = item.get("url", "#")

        console.print(f"[bold]{repo_name}[/bold] - {path}")
        console.print(f"  {url}")

        # Show text matches
        for tm in item.get("textMatches", [])[:2]:
            fragment = tm.get("fragment", "")[:100]
            if fragment:
                console.print(f"  > {fragment}...")
        console.print()


@app.command()
def issues(
    query: str = typer.Argument(..., help="Search query"),
    repository: str = typer.Option(None, "--repo", "-r", help="Specific repository"),
    state: str = typer.Option(None, "--state", "-s", help="Filter by state (open, closed)"),
    limit: int = typer.Option(5, "--limit", "-n", help="Max results"),
    json_output: bool = typer.Option(False, "--json", "-j", help="Output as JSON")
):
    """Search GitHub issues and discussions."""
    if not check_gh_cli():
        console.print("[red]Error: gh CLI not installed or not authenticated[/red]")
        raise typer.Exit(1)

    result = search_issues(query, limit, state, repository)

    if json_output:
        print(json.dumps(result, indent=2, default=str))
        return

    console.print(f"\n[bold blue]Issues Search:[/bold blue] {query}\n")

    for issue in result.get("issues", []):
        repo_name = issue.get("repository", {}).get("nameWithOwner", "unknown")
        title = issue.get("title", "No title")
        state = issue.get("state", "unknown")
        url = issue.get("url", "#")

        state_color = "green" if state == "OPEN" else "red"
        console.print(f"[{state_color}][{state}][/{state_color}] {repo_name}")
        console.print(f"  {title}")
        console.print(f"  {url}\n")


@app.command(name="file")
def get_file(
    repository: str = typer.Argument(..., help="Repository (owner/repo)"),
    path: str = typer.Argument(..., help="File path"),
    json_output: bool = typer.Option(False, "--json", "-j", help="Output as JSON")
):
    """Fetch full file content from a repository."""
    if not check_gh_cli():
        console.print("[red]Error: gh CLI not installed or not authenticated[/red]")
        raise typer.Exit(1)

    result = fetch_file_content(repository, path)

    if json_output:
        print(json.dumps(result, indent=2, default=str))
        return

    if result.get("error"):
        console.print(f"[red]Error: {result['error']}[/red]")
        return

    console.print(f"\n[bold blue]File:[/bold blue] {repository}/{path}\n")
    console.print(f"Size: {result.get('size', 0)} bytes")
    if result.get("truncated"):
        console.print("[yellow]Content truncated[/yellow]")
    console.print("\n" + result.get("content", ""))


@app.command()
def check():
    """Check if gh CLI is installed and authenticated."""
    if check_gh_cli():
        console.print("[green]gh CLI is installed and authenticated[/green]")

        # Show current user
        output = run_command(["gh", "api", "user", "--jq", ".login"])
        if not output.startswith("Error:"):
            console.print(f"Logged in as: {output}")
    else:
        console.print("[red]gh CLI is not installed or not authenticated[/red]")
        console.print("Install: https://cli.github.com/")
        console.print("Auth: gh auth login")
        raise typer.Exit(1)


if __name__ == "__main__":
    app()
