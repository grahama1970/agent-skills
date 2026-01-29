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
    try:
        proc = subprocess.run(["gh", "auth", "status"], capture_output=True, text=True)
        return proc.returncode == 0
    except Exception:
        return False


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
