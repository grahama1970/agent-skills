# Code Review Request: GitHub Search Skill Modularization

## Context
This is a refactoring of a 1051-line monolith (`github_search_monolith.py`) into modular components for better debuggability and maintainability.

## Files to Review

### 1. config.py (70 lines)
Constants, paths, and configuration for the skill.

### 2. utils.py (157 lines)
Common utilities: command execution, JSON parsing, search term extraction.

### 3. repo_search.py (249 lines)
Repository search functions: search_repos, search_issues, fetch metadata, deep analysis.

### 4. code_search.py (257 lines)
Code search functions: basic, symbol, path-filtered, multi-strategy search.

### 5. readme_analyzer.py (256 lines)
README analysis, treesitter integration, taxonomy classification, search pipeline.

### 6. github_search.py (325 lines)
Thin CLI entry point with typer commands.

## Review Focus
1. **Circular imports**: Verify no circular import issues between modules
2. **Interface cleanliness**: Are the module boundaries clean and logical?
3. **Error handling**: Consistent error handling patterns
4. **Type hints**: Proper type annotations
5. **Code duplication**: Any duplicated code that should be consolidated
6. **Best practices**: Python best practices and PEP8 compliance

## Code

### config.py
```python
"""Configuration and constants for GitHub Search skill.

This module contains:
- Skill integration paths
- Default configuration values
- Console instance for rich output
"""
from pathlib import Path

try:
    from rich.console import Console
except ImportError:
    Console = None

# Skill directory paths
SKILLS_DIR = Path(__file__).resolve().parents[1]
TREESITTER_SKILL = SKILLS_DIR / "treesitter"
TAXONOMY_SKILL = SKILLS_DIR / "taxonomy"

# Default limits
DEFAULT_REPO_LIMIT = 5
DEFAULT_CODE_LIMIT = 5
DEFAULT_ISSUE_LIMIT = 5
DEFAULT_FILE_MAX_SIZE = 10000

# Command timeout (seconds)
DEFAULT_TIMEOUT = 60

# Default search paths for code search
DEFAULT_SEARCH_PATHS = ["src/", "lib/", "core/", "pkg/", "internal/"]

# Language extension mappings
EXTENSION_TO_LANGUAGE = {
    "py": "python",
    "js": "javascript",
    "ts": "typescript",
    "go": "go",
    "rs": "rust",
    "java": "java",
    "rb": "ruby",
    "c": "c",
    "cpp": "cpp",
    "cc": "cpp",
}

LANGUAGE_TO_SUFFIX = {
    "python": ".py",
    "javascript": ".js",
    "typescript": ".ts",
    "go": ".go",
    "rust": ".rs",
    "java": ".java",
    "ruby": ".rb",
    "c": ".c",
    "cpp": ".cpp",
}

# Console instance (lazy initialization)
_console = None


def get_console() -> "Console":
    """Get or create the Rich console instance."""
    global _console
    if _console is None:
        if Console is not None:
            _console = Console()
        else:
            raise ImportError("Rich is not installed. Run: pip install rich")
    return _console
```

### utils.py
```python
"""Common utilities for GitHub Search skill.

This module contains:
- Command execution helpers
- GitHub CLI checks
- JSON parsing utilities
- Search term extraction
"""
import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

from .config import DEFAULT_TIMEOUT, DEFAULT_SEARCH_PATHS


def run_command(
    cmd: List[str],
    cwd: Optional[Path] = None,
    timeout: int = DEFAULT_TIMEOUT
) -> str:
    """Run a command and return stdout.

    Args:
        cmd: Command and arguments to execute
        cwd: Working directory for the command
        timeout: Timeout in seconds

    Returns:
        Command stdout on success, or "Error: ..." message on failure
    """
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


def check_gh_cli() -> bool:
    """Check if gh CLI is installed and authenticated.

    Returns:
        True if gh is installed and authenticated, False otherwise
    """
    if not shutil.which("gh"):
        return False
    # Check auth status
    result = run_command(["gh", "auth", "status"])
    return not result.startswith("Error:")


def parse_json_output(output: str) -> Optional[Any]:
    """Parse JSON output from a command.

    Args:
        output: Command output string

    Returns:
        Parsed JSON object, or None if parsing fails
    """
    if output.startswith("Error:"):
        return None
    try:
        return json.loads(output)
    except json.JSONDecodeError:
        return None


def extract_json_from_text(text: str) -> Optional[Dict[str, Any]]:
    """Extract JSON object from text that may contain non-JSON content.

    Args:
        text: Text potentially containing a JSON object

    Returns:
        Extracted JSON object, or None if not found
    """
    start = text.find('{')
    end = text.rfind('}')
    if start != -1 and end != -1:
        try:
            return json.loads(text[start:end + 1])
        except json.JSONDecodeError:
            return None
    return None


def extract_search_terms(query: str) -> Dict[str, List[str]]:
    """Extract potential symbols, keywords, and paths from a search query.

    Analyzes a search query to identify:
    - symbols: CamelCase, PascalCase, snake_case identifiers
    - keywords: Regular search terms
    - paths: Default code paths to search
    - filenames: Patterns that look like filenames

    Args:
        query: Search query string

    Returns:
        Dict with symbols, keywords, paths, filenames lists
    """
    result = {
        "symbols": [],
        "keywords": [],
        "paths": DEFAULT_SEARCH_PATHS.copy(),
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


def detect_language_from_path(path: str) -> Optional[str]:
    """Detect programming language from file path extension.

    Args:
        path: File path

    Returns:
        Language name, or None if not detected
    """
    from .config import EXTENSION_TO_LANGUAGE

    if '.' not in path:
        return None
    ext = path.split('.')[-1]
    return EXTENSION_TO_LANGUAGE.get(ext)
```

### repo_search.py
```python
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
import json
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

    try:
        items = json.loads(output)
        return [
            {
                "name": i["name"],
                "type": i["type"],
                "path": i["path"],
                "size": i.get("size", 0)
            }
            for i in items
        ]
    except (json.JSONDecodeError, KeyError):
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
```

### code_search.py
```python
"""Code search functions for GitHub Search skill.

This module contains:
- Basic code search
- Symbol search (function/class definitions)
- Path-filtered search
- Filename search
- Multi-strategy deep code search
"""
import json
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List, Optional

from .config import DEFAULT_CODE_LIMIT
from .utils import run_command, parse_json_output, extract_search_terms
from .repo_search import fetch_file_content


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
        List of code search results
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

        try:
            if not output.startswith("Error:"):
                matches = json.loads(output)
                for m in matches:
                    m["searched_path"] = path
                results.extend(matches)
        except json.JSONDecodeError:
            continue

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

        try:
            if not output.startswith("Error:"):
                matches = json.loads(output)
                for m in matches:
                    m["searched_filename"] = filename
                results.extend(matches)
        except json.JSONDecodeError:
            continue

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
    from .readme_analyzer import enhance_file_with_treesitter

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
```

### readme_analyzer.py
```python
"""README analysis and skill integrations.

This module contains:
- README fetching
- Treesitter integration for code parsing
- Taxonomy integration for classification
- Repository classification
- Full search and analyze pipeline
"""
import base64
import json
import os
import tempfile
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List, Optional

from .config import (
    TREESITTER_SKILL,
    TAXONOMY_SKILL,
    LANGUAGE_TO_SUFFIX,
)
from .utils import run_command, extract_json_from_text, detect_language_from_path


def fetch_repo_readme(repo: str) -> Dict[str, Any]:
    """Fetch repository README content.

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


# ... (rest of readme_analyzer.py)
```

### github_search.py (CLI)
```python
#!/usr/bin/env python3
"""GitHub Search: Deep multi-strategy search for repositories and code.

This is the thin CLI entry point that delegates to modular components.
"""
import json
import sys

try:
    import typer
except ImportError:
    print("Missing requirements. Run: pip install typer rich", file=sys.stderr)
    sys.exit(1)

from .config import get_console
from .utils import check_gh_cli
from .repo_search import (
    search_repos,
    search_issues,
    fetch_file_content,
    deep_repo_analysis,
)
from .code_search import (
    search_code_basic,
    search_code_symbols,
    search_code_by_path,
    multi_strategy_code_search,
)
from .readme_analyzer import search_and_analyze

app = typer.Typer(help="GitHub Search - Deep multi-strategy search")

# ... (CLI commands)
```

## Expected Output
A unified diff with any suggested improvements.
