"""GitHub Search skill - Deep multi-strategy search for repositories and code.

This package provides modular components for GitHub search:
- config: Constants and configuration
- utils: Common utilities
- repo_search: Repository search functions
- code_search: Code search functions
- readme_analyzer: README analysis and skill integrations
- github_search: CLI entry point
"""

from .config import (
    SKILLS_DIR,
    TREESITTER_SKILL,
    TAXONOMY_SKILL,
    DEFAULT_REPO_LIMIT,
    DEFAULT_CODE_LIMIT,
    DEFAULT_ISSUE_LIMIT,
    get_console,
)

from .utils import (
    run_command,
    check_gh_cli,
    parse_json_output,
    extract_search_terms,
    detect_language_from_path,
)

from .repo_search import (
    search_repos,
    search_issues,
    fetch_repo_metadata,
    fetch_repo_languages,
    fetch_repo_tree,
    fetch_file_content,
    deep_repo_analysis,
)

from .code_search import (
    search_code_basic,
    search_code_symbols,
    search_code_by_path,
    search_code_by_filename,
    multi_strategy_code_search,
)

from .readme_analyzer import (
    fetch_repo_readme,
    parse_with_treesitter,
    classify_with_taxonomy,
    enhance_file_with_treesitter,
    classify_repo,
    search_and_analyze,
)

__all__ = [
    # Config
    "SKILLS_DIR",
    "TREESITTER_SKILL",
    "TAXONOMY_SKILL",
    "DEFAULT_REPO_LIMIT",
    "DEFAULT_CODE_LIMIT",
    "DEFAULT_ISSUE_LIMIT",
    "get_console",
    # Utils
    "run_command",
    "check_gh_cli",
    "parse_json_output",
    "extract_search_terms",
    "detect_language_from_path",
    # Repo search
    "search_repos",
    "search_issues",
    "fetch_repo_metadata",
    "fetch_repo_languages",
    "fetch_repo_tree",
    "fetch_file_content",
    "deep_repo_analysis",
    # Code search
    "search_code_basic",
    "search_code_symbols",
    "search_code_by_path",
    "search_code_by_filename",
    "multi_strategy_code_search",
    # README analyzer
    "fetch_repo_readme",
    "parse_with_treesitter",
    "classify_with_taxonomy",
    "enhance_file_with_treesitter",
    "classify_repo",
    "search_and_analyze",
]
