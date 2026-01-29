"""Repository search and analysis functions.

This module contains:
- Repository search (search_repos)
- Issue search (search_issues)
- Repository metadata fetching
- Repository language breakdown
- Repository file tree listing
- File content fetching
- Deep repository analysis
"""
import base64
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List, Optional

from .config import DEFAULT_REPO_LIMIT, DEFAULT_ISSUE_LIMIT, DEFAULT_FILE_MAX_SIZE
from .utils import run_command, parse_json_output


def search_repos(
    query: str,
    limit: int = DEFAULT_REPO_LIMIT,
    language: Optional[str] = None
) -> Dict[str, Any]:
    """Search GitHub repositories.

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

    repos = parse_json_output(output)
    if repos is None:
        return {"error": "Invalid JSON response", "repos": []}

    return {"repos": repos, "count": len(repos)}


def search_issues(
    query: str,
    limit: int = DEFAULT_ISSUE_LIMIT,
    state: Optional[str] = None,
    repo: Optional[str] = None
) -> Dict[str, Any]:
    """Search GitHub issues and discussions.

    Args:
        query: Search query
        limit: Max results
        state: Filter by state (open, closed)
        repo: Filter by repository (owner/repo)

    Returns:
        Dict with issues list and metadata
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

    issues = parse_json_output(output)
    if issues is None:
        return {"error": "Invalid JSON response", "issues": []}

    return {"issues": issues, "count": len(issues)}


def fetch_repo_metadata(repo: str) -> Dict[str, Any]:
    """Fetch comprehensive repository metadata.

    Args:
        repo: Repository (owner/repo)

    Returns:
        Dict with repository metadata
    """
    cmd = [
        "gh", "repo", "view", repo, "--json",
        "name,owner,description,url,stargazerCount,forkCount,primaryLanguage,"
        "repositoryTopics,updatedAt,createdAt,isArchived,licenseInfo,defaultBranchRef"
    ]

    output = run_command(cmd)

    if output.startswith("Error:"):
        return {"error": output}

    result = parse_json_output(output)
    if result is None:
        return {"error": "Invalid JSON response"}

    return result


def fetch_repo_languages(repo: str) -> Dict[str, int]:
    """Fetch repository language breakdown.

    Args:
        repo: Repository (owner/repo)

    Returns:
        Dict of {language: bytes}
    """
    cmd = ["gh", "api", f"repos/{repo}/languages"]
    output = run_command(cmd)

    result = parse_json_output(output)
    return result if result else {}


def fetch_repo_tree(repo: str, path: str = "") -> List[Dict[str, Any]]:
    """Fetch repository file tree.

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

    items = parse_json_output(output)
    if not items:
        return []
    # Handle single file response (returns dict instead of list)
    if isinstance(items, dict):
        items = [items]
    try:
        return [
            {
                "name": i["name"],
                "type": i["type"],
                "path": i["path"],
                "size": i.get("size", 0)
            }
            for i in items
        ]
    except KeyError:
        return []


def fetch_file_content(
    repo: str,
    file_path: str,
    max_size: int = DEFAULT_FILE_MAX_SIZE
) -> Dict[str, Any]:
    """Fetch full file content from a repository.

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


def deep_repo_analysis(repo: str) -> Dict[str, Any]:
    """Comprehensive repository analysis.

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
    from .readme_analyzer import fetch_repo_readme

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
