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


def parse_with_treesitter(content: str, language: str) -> Dict[str, Any]:
    """Parse code content with treesitter to extract symbols.

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

    # Write content to temp file
    suffix = LANGUAGE_TO_SUFFIX.get(language.lower(), ".txt")

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
    """Classify text with taxonomy to extract bridge tags.

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

    result = extract_json_from_text(output)
    if result:
        return result

    try:
        return json.loads(output)
    except json.JSONDecodeError:
        return {"error": "Invalid JSON from taxonomy", "bridge_tags": []}


def enhance_file_with_treesitter(
    file_result: Dict[str, Any],
    language: Optional[str] = None
) -> Dict[str, Any]:
    """Enhance a fetched file result with treesitter symbol extraction.

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
        language = detect_language_from_path(path)

    if language:
        symbols = parse_with_treesitter(file_result["content"], language)
        file_result["symbols"] = symbols.get("symbols", [])
        file_result["language"] = language

    return file_result


def classify_repo(repo_analysis: Dict[str, Any]) -> Dict[str, Any]:
    """Classify a repository using taxonomy based on README and metadata.

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


def search_and_analyze(
    query: str,
    top_repos: int = 3,
    deep_search: bool = True,
    use_treesitter: bool = False,
    use_taxonomy: bool = False
) -> Dict[str, Any]:
    """Full search pipeline: find repos, analyze, and search code.

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
    from .repo_search import search_repos, search_issues, deep_repo_analysis
    from .code_search import multi_strategy_code_search

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
