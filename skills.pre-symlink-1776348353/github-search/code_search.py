"""Code search functions for GitHub Search skill.

This module contains:
- Basic code search
- Symbol search (function/class definitions)
- Path-filtered search
- Filename search
- Multi-strategy deep code search
"""
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List, Optional

from config import DEFAULT_CODE_LIMIT
from utils import run_command, parse_json_output, extract_search_terms
from repo_search import fetch_file_content


def search_code_basic(
    query: str,
    repo: Optional[str] = None,
    language: Optional[str] = None,
    limit: int = DEFAULT_CODE_LIMIT
) -> List[Dict[str, Any]]:
    """Basic code search with text matching.

    Args:
        query: Search query
        repo: Specific repository (owner/repo)
        language: Filter by language
        limit: Max results

    Returns:
        List of code search results (includes textMatches when available)
    """
    cmd = [
        "gh", "search", "code", query,
        "--limit", str(limit),
        "--json", "path,repository,url,textMatches"
    ]
    if repo:
        cmd.extend(["--repo", repo])
    if language:
        cmd.extend(["--language", language])

    output = run_command(cmd)

    result = parse_json_output(output)
    return result if result else []


def search_code_symbols(
    repo: str,
    symbols: List[str],
    language: Optional[str] = None
) -> List[Dict[str, Any]]:
    """Search for symbol definitions using the symbol: qualifier.

    Uses tree-sitter parsing to find actual function/class definitions,
    not just text matches.

    Reference: https://docs.github.com/en/search-github/github-code-search

    Args:
        repo: Repository to search (owner/repo)
        symbols: List of symbol names to find
        language: Filter by language

    Returns:
        List of symbol search results
    """
    results = []

    for symbol in symbols[:5]:  # Limit to avoid rate limits
        query = f"symbol:{symbol}"
        cmd = [
            "gh", "search", "code", "--repo", repo, query,
            "--limit", "3",
            "--json", "path,repository,url,textMatches"
        ]
        if language:
            cmd.extend(["--language", language])

        output = run_command(cmd)
        matches = parse_json_output(output)
        if matches is not None:
            for m in matches:
                m["symbol"] = symbol
                m["search_type"] = "definition"
            results.extend(matches)

    return results


def search_code_by_path(
    repo: str,
    query: str,
    paths: List[str],
    language: Optional[str] = None
) -> List[Dict[str, Any]]:
    """Search code in specific directories using the path: qualifier.

    Args:
        repo: Repository to search
        query: Search query
        paths: List of paths to search in (e.g., ["src/", "lib/"])
        language: Filter by language

    Returns:
        List of path-filtered search results
    """
    results = []

    for path in paths[:4]:  # Limit paths
        full_query = f"{query} path:{path}"
        cmd = [
            "gh", "search", "code", "--repo", repo, full_query,
            "--limit", "3",
            "--json", "path,repository,url,textMatches"
        ]
        if language:
            cmd.extend(["--language", language])

        output = run_command(cmd)
        matches = parse_json_output(output)
        if matches is not None:
            for m in matches:
                m["searched_path"] = path
            results.extend(matches)

    return results


def search_code_by_filename(
    repo: str,
    filenames: List[str],
    language: Optional[str] = None
) -> List[Dict[str, Any]]:
    """Search for specific files using the filename: qualifier.

    Args:
        repo: Repository to search
        filenames: List of filenames to find (e.g., ["config.py", "settings.json"])
        language: Filter by language

    Returns:
        List of filename search results
    """
    results = []

    for filename in filenames[:5]:
        cmd = [
            "gh", "search", "code", "--repo", repo, f"filename:{filename}",
            "--limit", "3",
            "--json", "path,repository,url"
        ]
        if language:
            cmd.extend(["--language", language])

        output = run_command(cmd)
        matches = parse_json_output(output)
        if matches is not None:
            for m in matches:
                m["searched_filename"] = filename
            results.extend(matches)

    return results


def multi_strategy_code_search(
    repo: str,
    query: str,
    language: Optional[str] = None,
    fetch_files: bool = True,
    use_treesitter: bool = False
) -> Dict[str, Any]:
    """Multi-strategy deep code search within a repository.

    Strategies:
    1. Basic text search
    2. Symbol search (function/class definitions)
    3. Path-filtered search (src/, lib/, etc.)
    4. Filename search
    5. Full file content fetch for top matches
    6. Optional treesitter parsing for deeper symbol extraction

    Args:
        repo: Repository to search
        query: Search query
        language: Filter by language
        fetch_files: Whether to fetch full file contents
        use_treesitter: Parse fetched files with treesitter for symbols

    Returns:
        Dict with results from all strategies:
        - basic_matches, symbol_matches, path_matches, filename_matches, file_contents
    """
    from readme_analyzer import enhance_file_with_treesitter

    result = {
        "repo": repo,
        "language": language,
        "basic_matches": [],
        "symbol_matches": [],
        "path_matches": [],
        "filename_matches": [],
        "file_contents": []
    }

    # Extract search terms
    terms = extract_search_terms(query)

    # Run searches in parallel
    with ThreadPoolExecutor(max_workers=4) as executor:
        future_basic = executor.submit(search_code_basic, query, repo, language, 5)
        future_symbols = executor.submit(
            search_code_symbols, repo, terms["symbols"], language
        ) if terms["symbols"] else None
        future_paths = executor.submit(
            search_code_by_path, repo,
            " ".join(terms["keywords"]) if terms["keywords"] else query,
            terms["paths"], language
        )
        future_filenames = executor.submit(
            search_code_by_filename, repo, terms["filenames"], language
        ) if terms["filenames"] else None

        result["basic_matches"] = future_basic.result()
        if future_symbols:
            result["symbol_matches"] = future_symbols.result()
        result["path_matches"] = future_paths.result()
        if future_filenames:
            result["filename_matches"] = future_filenames.result()

    # Fetch full content of top matches
    if fetch_files:
        all_paths = set()
        for match in result["basic_matches"][:2]:
            if match.get("path"):
                all_paths.add(match["path"])
        for match in result["symbol_matches"][:2]:
            if match.get("path"):
                all_paths.add(match["path"])
        for match in result["path_matches"][:1]:
            if match.get("path"):
                all_paths.add(match["path"])
        for match in result["filename_matches"][:2]:
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
