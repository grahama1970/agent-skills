"""GitHub Copilot provider for code-review skill.

Contains:
- GitHub CLI authentication checking
- Copilot-specific functionality
"""
from __future__ import annotations

import shutil
import subprocess
from typing import Optional

# Handle both import modes
try:
    from ..config import get_timeout
except ImportError:
    from config import get_timeout


def check_gh_auth() -> dict:
    """Check GitHub CLI authentication status.

    Uses `gh auth token` for reliable auth check (returns token if authenticated).
    Uses `gh api user` to get username (reliable JSON output).

    Returns dict with:
        authenticated: bool
        user: Optional[str]
        error: Optional[str]
    """
    result = {
        "authenticated": False,
        "user": None,
        "error": None,
    }

    # Check if gh CLI is installed
    if not shutil.which("gh"):
        result["error"] = "gh CLI not found. Install: https://cli.github.com/"
        return result

    # Check auth by trying to get token (most reliable check)
    try:
        token_result = subprocess.run(
            ["gh", "auth", "token"],
            capture_output=True,
            text=True,
            timeout=get_timeout(),
        )
        if token_result.returncode != 0:
            result["error"] = "Not logged in. Run: gh auth login"
            return result

        # Get username via API (reliable JSON)
        user_result = subprocess.run(
            ["gh", "api", "user", "--jq", ".login"],
            capture_output=True,
            text=True,
            timeout=get_timeout(),
        )
        if user_result.returncode == 0:
            result["user"] = user_result.stdout.strip()

        result["authenticated"] = True

    except Exception as e:
        result["error"] = str(e)

    return result
